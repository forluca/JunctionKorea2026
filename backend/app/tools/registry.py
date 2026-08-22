"""Action tool 레지스트리.

orchestrator가 계획한 액션을 이름으로 dispatch한다.
새 툴 추가 방법: 아래처럼 데코레이터로 등록만 하면 된다.

    @tool("my_tool")
    def my_tool(args: dict, state: dict) -> dict:
        ...
        return {"status": "done", ...}

- args: orchestrator LLM이 채운 파라미터
- state: 그래프 전체 상태(문서 id, trip_id, 추출 필드 등 컨텍스트)
- 반환값은 action_results에 그대로 기록된다.

add_to_itinerary는 실제 구현(핵심 경로), 나머지는 스텁 — 담당자가 채워주세요.
"""

from datetime import datetime, timedelta
from typing import Any, Callable

from app.db import get_db

TOOL_REGISTRY: dict[str, Callable[[dict, dict], dict]] = {}


def tool(name: str):
    def deco(fn: Callable[[dict, dict], dict]):
        TOOL_REGISTRY[name] = fn
        return fn

    return deco


def dispatch(name: str, args: dict, state: dict) -> dict:
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return {"tool": name, "status": "error", "detail": f"unknown tool: {name}"}
    try:
        result = fn(args or {}, state)
        return {"tool": name, **result}
    except Exception as e:  # 데모: 한 툴 실패가 파이프라인을 죽이지 않게
        return {"tool": name, "status": "error", "detail": str(e)}


# ─────────────────────────── helpers ───────────────────────────

def _parse_dt(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    v = value.strip().replace(" ", "T", 1) if " " in value.strip() else value.strip()
    v = v.replace("Z", "+00:00")
    dt = None
    for fmt in (None, "%Y-%m-%d"):
        try:
            dt = datetime.fromisoformat(v) if fmt is None else datetime.strptime(v, fmt)
            break
        except ValueError:
            continue
    # DB(timestamptz, aware)와 LLM 출력(naive)이 섞여도 비교되게 naive로 통일
    if dt is not None and dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt


def check_conflicts(trip_id: str, starts_at: str | None, ends_at: str | None,
                    exclude_item_id: str | None = None) -> list[dict]:
    """같은 여행 내 시간대가 겹치는 기존 일정을 찾는다."""
    new_start = _parse_dt(starts_at)
    if new_start is None:
        return []
    new_end = _parse_dt(ends_at) or (new_start + timedelta(hours=2))

    rows = (
        get_db().table("items").select("id,title,starts_at,ends_at")
        .eq("trip_id", trip_id).execute().data or []
    )
    conflicts = []
    for row in rows:
        if exclude_item_id and row["id"] == exclude_item_id:
            continue
        s = _parse_dt(row.get("starts_at"))
        if s is None:
            continue
        e = _parse_dt(row.get("ends_at")) or (s + timedelta(hours=2))
        if s < new_end and e > new_start:
            conflicts.append({"id": row["id"], "title": row.get("title")})
    return conflicts


# ─────────────────────── 실제 구현: 일정 추가 ───────────────────────

def build_item_row(state: dict) -> tuple[dict, list[dict]]:
    """추출·정규화된 필드로 insert될 items 행과 충돌 목록을 만든다 (DB에 쓰지 않음)."""
    fields = state.get("item_fields") or {}
    extracted = state.get("extracted") or {}
    trip_id = state.get("trip_id")

    starts_at = fields.get("starts_at") or None
    ends_at = fields.get("ends_at") or None
    conflicts = check_conflicts(trip_id, starts_at, ends_at) if trip_id else []
    # 가격 정규화: -1(미표기 sentinel) → NULL / 0+통화 없음 → 미표기로 간주해 NULL
    # / 0+통화 있음 → 진짜 무료(0 유지) / 양수 → 그대로
    price = extracted.get("total_price")
    if not isinstance(price, (int, float)) or price < 0:
        price = None
    elif price == 0 and not extracted.get("currency"):
        price = None
    row = {
        "trip_id": trip_id,
        "document_id": state.get("document_id"),
        "type": state.get("doc_type", "other"),
        "title": fields.get("title") or "제목 없음",
        "starts_at": _iso_or_none(starts_at),
        "ends_at": _iso_or_none(ends_at),
        "location": fields.get("location") or None,
        "price": price,
        "currency": (extracted.get("currency") or None) if price is not None else None,
        "booking_ref": extracted.get("booking_reference") or None,
        "qr_code": ", ".join(state.get("qr_codes") or []) or None,
        "qr_images": state.get("qr_images") or None,
        "cancellation_deadline": _iso_or_none(extracted.get("cancellation_deadline")),
        "notes": state.get("notes") or None,  # 알아둬야 할 사항 문장 배열 (jsonb)
        "has_conflict": bool(conflicts),
        "conflict_msg": (
            "시간이 겹치는 일정: " + ", ".join(c["title"] or c["id"] for c in conflicts)
            if conflicts else None
        ),
    }
    return row, conflicts


@tool("add_to_itinerary")
def add_to_itinerary(args: dict, state: dict) -> dict:
    """추출·정규화된 필드로 items 행을 만들고 충돌을 검사한다.

    충돌 정책: 기존 일정과 시간이 겹치면 저장하지 않고 거부(rejected)한다.
    이후 액션(캘린더 등록 등)도 act 노드에서 함께 중단된다.
    """
    trip_id = state.get("trip_id")
    if not trip_id:
        return {"status": "error", "detail": "trip_id missing"}
    row, conflicts = build_item_row(state)

    # 중복 검사: 같은 여행에 같은 예약번호가 이미 있으면 같은 문서를 다시 올린 것
    if row.get("booking_ref"):
        dup = (get_db().table("items").select("id,title")
               .eq("trip_id", trip_id).eq("booking_ref", row["booking_ref"])
               .execute().data or [])
        if dup:
            return {"status": "rejected", "reason": "duplicate",
                    "conflicts": dup, "detail": "문서가 중복되었습니다."}

    # 시간 겹침(overlap)은 저장하되 has_conflict/conflict_msg로 표시만 한다
    res = get_db().table("items").insert(row).execute()
    item_id = res.data[0]["id"]
    return {"status": "done", "item_id": item_id, "conflicts": conflicts}


def _iso_or_none(value: Any) -> str | None:
    dt = _parse_dt(value)
    return dt.isoformat() if dt else None


@tool("add_itinerary_bulk")
def add_itinerary_bulk(args: dict, state: dict) -> dict:
    """여행 계획 문서에서 정규화된 일정 목록을 일괄 등록한다.

    충돌 검사는 **일괄 등록 전에 이미 존재하던 일정**하고만 수행한다 —
    계획서 내부의 인접 일정끼리는 (종료시각 +2h 추정 규칙 때문에) 서로
    겹침 판정이 나기 쉬운데, 계획서는 내부적으로 일관된 문서이므로 제외.
    """
    trip_id = state.get("trip_id")
    if not trip_id:
        return {"status": "error", "detail": "trip_id missing"}
    items = state.get("itinerary_items") or []
    if not items:
        return {"status": "error", "detail": "itinerary_items empty"}

    db = get_db()
    # 일괄 등록 전 기존 일정 스냅샷 (배치 내부끼리는 충돌 검사 제외)
    existing = (db.table("items").select("id,title,starts_at,ends_at")
                .eq("trip_id", trip_id).execute().data or [])

    def conflicts_with_existing(starts_at, ends_at) -> list[dict]:
        s = _parse_dt(starts_at)
        if s is None:
            return []
        e = _parse_dt(ends_at) or (s + timedelta(hours=2))
        out = []
        for row in existing:
            es = _parse_dt(row.get("starts_at"))
            if es is None:
                continue
            ee = _parse_dt(row.get("ends_at")) or (es + timedelta(hours=2))
            if es < e and ee > s:
                out.append({"id": row["id"], "title": row.get("title")})
        return out

    item_ids: list[str] = []
    all_conflicts: list[dict] = []
    for it in items:
        starts_at = _iso_or_none(it.get("starts_at"))
        ends_at = _iso_or_none(it.get("ends_at"))
        conflicts = conflicts_with_existing(starts_at, ends_at)
        row = {
            "trip_id": trip_id,
            "document_id": state.get("document_id"),
            "type": it.get("category") or "other",
            "title": it.get("title") or "제목 없음",
            "starts_at": starts_at,
            "ends_at": ends_at,
            "location": it.get("location") or None,
            "notes": [it["summary"]] if it.get("summary") else None,
            "has_conflict": bool(conflicts),
            "conflict_msg": (
                "시간이 겹치는 일정: " + ", ".join(c["title"] or c["id"] for c in conflicts)
                if conflicts else None
            ),
        }
        res = db.table("items").insert(row).execute()
        item_ids.append(res.data[0]["id"])
        all_conflicts.extend(conflicts)
    return {"status": "done", "item_ids": item_ids, "count": len(item_ids),
            "conflicts": all_conflicts}


# ──────────────────────── 스텁: 담당자 구현 ────────────────────────

@tool("register_calendar")
def register_calendar(args: dict, state: dict) -> dict:
    """Google Calendar에 일정 등록 (backend/calendar_tool.py 사용).

    사전 준비: backend/에 credentials.json 배치 후 `python calendar_tool.py`를
    한 번 실행해 브라우저 OAuth 인증 → token.json 생성. 그 전에는 error로 스킵됨.
    """
    fields = state.get("item_fields") or {}
    extracted = state.get("extracted") or {}
    title = args.get("title") or fields.get("title") or "여행 일정"
    start = _parse_dt(args.get("starts_at") or fields.get("starts_at"))
    cancellation_deadline = (
        args.get("cancellation_deadline")
        or extracted.get("cancellation_deadline")
        or fields.get("cancellation_deadline")
    )
    if start is None and not cancellation_deadline:
        return {
            "status": "skipped",
            "detail": "시작 시각과 취소 기한이 없어 캘린더 등록 생략",
        }
    end = (
        _parse_dt(args.get("ends_at") or fields.get("ends_at"))
        or (start + timedelta(hours=2) if start else None)
    )
    notes = state.get("notes") or []
    description = (
        "\n".join(str(note) for note in notes if note)
        if isinstance(notes, list)
        else str(notes)
    ) or None

    try:
        import calendar_tool  # backend/calendar_tool.py (팀원 구현)

        service = calendar_tool.get_calendar_service()
        result = {"status": "done"}
        if start and end:
            event = calendar_tool.create_event(
                title=title,
                start_time=start.strftime("%Y-%m-%dT%H:%M:%S"),
                end_time=end.strftime("%Y-%m-%dT%H:%M:%S"),
                description=description,
                location=args.get("location") or fields.get("location"),
                service=service,
            )
            result["event_link"] = event.get("htmlLink")

        if cancellation_deadline:
            cancellation_event = calendar_tool.create_cancellation_deadline_reminder(
                {
                    "title": title,
                    "cancellation_deadline": cancellation_deadline,
                    "cancellation_message": description,
                },
                service=service,
            )
            result["cancellation_event_link"] = cancellation_event.get("htmlLink")

        return result
    except FileNotFoundError:
        return {"status": "error",
                "detail": "credentials.json 없음 — backend/에 Google OAuth 키를 두고 "
                          "`python calendar_tool.py`로 최초 인증(token.json 생성)이 필요합니다."}


@tool("record_expense")
def record_expense(args: dict, state: dict) -> dict:
    """TODO(담당자): 여행 비용 기록.

    args 예시: {"amount": number, "currency": ..., "category": ..., "memo": ...}
    """
    return {"status": "stub", "detail": "expense recording not implemented yet", "args": args}
