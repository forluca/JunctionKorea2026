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
    """추출·정규화된 필드로 items 행을 만들고 충돌을 검사한다."""
    if not state.get("trip_id"):
        return {"status": "error", "detail": "trip_id missing"}
    row, conflicts = build_item_row(state)
    res = get_db().table("items").insert(row).execute()
    item_id = res.data[0]["id"]
    return {"status": "done", "item_id": item_id, "conflicts": conflicts}


def _iso_or_none(value: Any) -> str | None:
    dt = _parse_dt(value)
    return dt.isoformat() if dt else None


@tool("add_itinerary_bulk")
def add_itinerary_bulk(args: dict, state: dict) -> dict:
    """여행 계획 문서에서 정규화된 일정 목록을 일괄 등록한다 (건별 충돌 검사 포함)."""
    trip_id = state.get("trip_id")
    if not trip_id:
        return {"status": "error", "detail": "trip_id missing"}
    items = state.get("itinerary_items") or []
    if not items:
        return {"status": "error", "detail": "itinerary_items empty"}

    db = get_db()
    item_ids: list[str] = []
    all_conflicts: list[dict] = []
    for it in items:
        starts_at = _iso_or_none(it.get("starts_at"))
        ends_at = _iso_or_none(it.get("ends_at"))
        conflicts = check_conflicts(trip_id, starts_at, ends_at)
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
    """TODO(담당자): 캘린더 등록 (예: Google Calendar API).

    args 예시: {"title": ..., "starts_at": ISO8601, "ends_at": ISO8601, "location": ...}
    """
    return {"status": "stub", "detail": "calendar registration not implemented yet", "args": args}


@tool("set_reminder")
def set_reminder(args: dict, state: dict) -> dict:
    """TODO(담당자): 알림 예약 (예: 취소기한 D-1, 입장 1시간 전).

    args 예시: {"remind_at": ISO8601, "message": ...}
    """
    return {"status": "stub", "detail": "reminder not implemented yet", "args": args}


@tool("record_expense")
def record_expense(args: dict, state: dict) -> dict:
    """TODO(담당자): 여행 비용 기록.

    args 예시: {"amount": number, "currency": ..., "category": ..., "memo": ...}
    """
    return {"status": "stub", "detail": "expense recording not implemented yet", "args": args}
