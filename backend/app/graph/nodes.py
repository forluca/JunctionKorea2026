"""LangGraph 노드 구현.

ingest → classify → (parse ∥ extract) → orchestrate → act
"""

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from app import config
from app.db import get_db
from app.graph.schemas import CATEGORIES, CATEGORY_NAMES, EXTRACTION_SCHEMAS
from app.graph.state import DocState
from app.services import upstage
from app.services.barcode import decode_barcodes
from app.services.studio_agent import run_document_agent
from app.tools.registry import dispatch


async def ingest(state: DocState) -> dict:
    """원본 파일을 Supabase Storage에 저장하고 documents 레코드를 만든다."""
    if state.get("dry_run"):
        return {"document_id": "(dry-run)", "storage_path": "(dry-run: 저장 안 함)"}
    db = get_db()
    # Storage 키는 ASCII만 허용 — uuid + 확장자로 만들고 원본 파일명은 DB에 보존
    suffix = Path(state["file_name"]).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix or ""):
        suffix = ""
    storage_path = f"{uuid4().hex}{suffix}"
    db.storage.from_(config.STORAGE_BUCKET).upload(
        storage_path,
        state["file_bytes"],
        {"content-type": state["mime_type"]},
    )
    row = {
        "file_name": state["file_name"],
        "mime_type": state["mime_type"],
        "storage_path": storage_path,
    }
    res = db.table("documents").insert(row).execute()
    return {"document_id": res.data[0]["id"], "storage_path": storage_path}


async def classify(state: DocState) -> dict:
    """Upstage Classify — 문서 유형 판별."""
    label = await upstage.classify_document(
        state["file_bytes"], state["mime_type"], CATEGORIES
    )
    doc_type = label if label in CATEGORY_NAMES else "other"
    if not state.get("dry_run"):
        get_db().table("documents").update({"doc_type": doc_type}).eq(
            "id", state["document_id"]
        ).execute()
    return {"doc_type": doc_type}


async def parse(state: DocState) -> dict:
    """Upstage Parse — HTML/text 구조화 (trip 분기에서 사용, QR 디코딩은 decode_codes 노드)."""
    parsed = await upstage.parse_document(
        state["file_bytes"], state["file_name"], state["mime_type"]
    )
    if not state.get("dry_run"):
        get_db().table("documents").update(
            {"parsed_html": parsed["html"], "parsed_text": parsed["text"]}
        ).eq("id", state["document_id"]).execute()
    return {"parsed_html": parsed["html"], "parsed_text": parsed["text"]}


async def decode_codes(state: DocState) -> dict:
    """원본 문서에서 QR/바코드 디코딩 + 크롭 이미지 Storage 저장 (studio_agent와 병렬)."""
    decoded = decode_barcodes(state["file_bytes"], state["mime_type"], None)
    qr_codes = [d["value"] for d in decoded]
    qr_images: list[dict] = []
    if not state.get("dry_run"):
        db = get_db()
        for i, d in enumerate(decoded):
            path = f"codes/{uuid4().hex}_{i}.png"
            db.storage.from_(config.STORAGE_BUCKET).upload(
                path, d["png"], {"content-type": "image/png"}
            )
            qr_images.append({"value": d["value"], "format": d["format"],
                              "image_path": path})
    else:
        qr_images = [{"value": d["value"], "format": d["format"],
                      "image_path": "(dry-run: 저장 안 함)"} for d in decoded]
    return {"qr_codes": qr_codes, "qr_images": qr_images}


def _items_from_schedule(extracted: dict, base: date) -> list[dict]:
    """Extract 스텝의 schedule_items로 일정을 결정적으로 생성 (최종 스텝 폴백용).

    "Day N" 상대 라벨은 base + (N-1)일로, 절대 날짜는 그대로 사용한다.
    """
    out = []
    for it in extracted.get("schedule_items") or []:
        label = str(it.get("date") or "").strip()
        m = re.search(r"day\s*(\d+)", label, re.I)
        if m:
            d = base + timedelta(days=int(m.group(1)) - 1)
        else:
            d = _parse_date(label)
        st = str(it.get("start_time") or "").strip()[:5]
        et = str(it.get("end_time") or "").strip()[:5]
        starts = f"{d.isoformat()}T{st or '09:00'}:00" if d else ""
        ends = f"{d.isoformat()}T{et}:00" if (d and re.fullmatch(r"\d{2}:\d{2}", et)) else ""
        out.append({
            "title": it.get("title"),
            "starts_at": starts,
            "ends_at": ends,
            "location": it.get("location") or "",
            "category": it.get("category") or "other",
            "summary": it.get("notes") or "",
        })
    return out


def _parse_date(value) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _shift_iso(value, delta: timedelta) -> str | None:
    """ISO 일시 문자열을 delta만큼 이동 (파싱 불가면 원본 유지)."""
    if not value or not isinstance(value, str):
        return value
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (dt + delta).isoformat()
    except ValueError:
        return value


async def studio_agent(state: DocState) -> dict:
    """Upstage Studio Agent — classify→parse→extract→orchestrate를 잡 하나로 수행.

    include=["all"]로 중간 스텝(parse/classify/extract)까지 수확하고,
    최종 Instruct 스텝의 출력(키가 흔들릴 수 있음)은 방어적으로 정규화한다.
    """
    res = await run_document_agent(
        state["file_bytes"], state["file_name"], state["mime_type"]
    )
    raw_doc_type = (res.get("doc_type") or "").strip()
    extracted = res.get("extracted") or {}
    final = res.get("final") or {}

    # ── itinerary 분기 (에이전트가 여행 계획 문서로 분류한 경우) ──
    # 출력 형태: {title, start_date, end_date, warnings, items[{title, starts_at, ...}]}
    if raw_doc_type == "itinerary" or isinstance(final.get("items"), list):
        items = final.get("items") or []
        want = _parse_date(state.get("trip_start_date"))
        warnings = [str(w) for w in (final.get("warnings") or []) if w]

        if items:
            # 최종 스텝이 일정 배열을 냈으면 그대로 쓰되, startDate 기준으로 날짜 시프트
            shift = None
            have = _parse_date(final.get("start_date"))
            if want and have and want != have:
                shift = want - have
            norm_items = []
            for it in items:
                starts, ends = it.get("starts_at"), it.get("ends_at")
                if shift:
                    starts = _shift_iso(starts, shift)
                    ends = _shift_iso(ends, shift)
                norm_items.append({
                    "title": it.get("title"),
                    "starts_at": starts or "",
                    "ends_at": ends or "",
                    "location": it.get("location") or "",
                    "category": it.get("category") or "other",
                    "summary": it.get("notes") or it.get("summary") or "",
                })
            if shift:
                # 사용자가 시작일을 지정해 재배치했으므로 '임시 배치' 경고는 사실이 아님
                warnings = [w for w in warnings if "임시" not in w]
                warnings.insert(0, f"여행 시작일 {want.isoformat()} 기준으로 일정을 배치했습니다.")
        else:
            # 폴백: 최종 스텝이 JSON 일정 배열을 안 냈으면(산문 출력 등)
            # Extract 스텝의 schedule_items로 코드가 결정적으로 날짜를 배치
            base = want or (date.today() + timedelta(days=7))
            norm_items = _items_from_schedule(extracted, base)
            if want:
                warnings.insert(0, f"여행 시작일 {want.isoformat()} 기준으로 일정을 배치했습니다.")
            else:
                warnings.insert(0, "여행 시작일을 알 수 없어 임시 날짜(오늘+7일 기준)로 배치했습니다.")
        trip_title = final.get("title") or extracted.get("trip_title") or "여행 계획"
        if not state.get("dry_run"):
            get_db().table("documents").update({
                "doc_type": "itinerary",
                "parsed_html": res.get("parsed_html") or "",
                "parsed_text": res.get("parsed_text") or "",
                "extracted": extracted,
            }).eq("id", state["document_id"]).execute()
        return {
            "doc_type": "itinerary",
            "parsed_html": res.get("parsed_html") or "",
            "parsed_text": res.get("parsed_text") or "",
            "extracted": extracted,
            "item_fields": {"trip_title": trip_title, "title": trip_title},
            "itinerary_items": norm_items,
            "notes": warnings,
            # 계획 문서는 저장만 하고 캘린더/비용 액션은 하지 않음
            "planned_actions": [{"tool": "add_itinerary_bulk", "args": {}}],
        }

    # ── 바우처 분기 ──
    doc_type = raw_doc_type if raw_doc_type in CATEGORY_NAMES else "other"

    # ── 최종 스텝 정규화 (키 흔들림 방어: normalized_item/itinerary_item/item, type/tool) ──
    item = (final.get("normalized_item") or final.get("itinerary_item")
            or final.get("item") or {})
    item_fields = {
        "title": item.get("title") or f"{doc_type} 일정",
        "trip_title": final.get("trip_title") or item.get("trip_title") or "",
        "starts_at": item.get("starts_at") or "",
        "ends_at": item.get("ends_at") or "",
        "location": item.get("location") or "",
        "summary": item.get("summary") or "",
    }
    notes = [str(n) for n in (final.get("notes") or []) if n]

    planned: list[dict] = []
    for a in final.get("actions") or []:
        if not isinstance(a, dict):
            continue
        tool_name = a.get("tool") or a.get("type") or a.get("name")
        if tool_name in ("add_to_itinerary", "register_calendar", "record_expense"):
            planned.append({"tool": tool_name, "args": a.get("args") or {}})
    # 액션 규칙을 코드로 강제 (LLM이 빠뜨려도 보장):
    # ① add_to_itinerary 항상 ② 시작 시각 있으면 register_calendar ③ 가격>0이면 record_expense
    have = {p["tool"] for p in planned}
    if "add_to_itinerary" not in have:
        planned.insert(0, {"tool": "add_to_itinerary", "args": {}})
    if item_fields.get("starts_at") and "register_calendar" not in have:
        planned.append({"tool": "register_calendar", "args": {}})
    price = extracted.get("total_price")
    if isinstance(price, (int, float)) and price > 0 and "record_expense" not in have:
        planned.append({"tool": "record_expense", "args": {
            "amount": price, "currency": extracted.get("currency") or "",
            "category": doc_type, "memo": item_fields.get("title") or "",
        }})
    planned.sort(key=lambda p: 0 if p["tool"] == "add_to_itinerary" else 1)

    if not state.get("dry_run"):
        get_db().table("documents").update({
            "doc_type": doc_type,
            "parsed_html": res.get("parsed_html") or "",
            "parsed_text": res.get("parsed_text") or "",
            "extracted": extracted,
        }).eq("id", state["document_id"]).execute()

    return {
        "doc_type": doc_type,
        "parsed_html": res.get("parsed_html") or "",
        "parsed_text": res.get("parsed_text") or "",
        "extracted": extracted,
        "item_fields": item_fields,
        "notes": notes,
        "planned_actions": planned,
    }


async def extract(state: DocState) -> dict:
    """Upstage Extract — 문서 유형별 스키마로 핵심 필드 추출 (parse와 병렬)."""
    doc_type = state.get("doc_type", "other")
    schema = EXTRACTION_SCHEMAS.get(doc_type, EXTRACTION_SCHEMAS["other"])
    extracted = await upstage.extract_information(
        state["file_bytes"], state["mime_type"], f"{doc_type}_fields", schema
    )
    if not state.get("dry_run"):
        get_db().table("documents").update({"extracted": extracted}).eq(
            "id", state["document_id"]
        ).execute()
    return {"extracted": extracted}


# ─────────────────── trip(여행 계획 문서) 플로우 노드 ───────────────────

async def extract_itinerary(state: DocState) -> dict:
    """trip 분기 전용 Extract — 여행 계획 문서에서 일정 배열 추출 (classify 생략)."""
    extracted = await upstage.extract_information(
        state["file_bytes"], state["mime_type"], "itinerary_fields",
        EXTRACTION_SCHEMAS["itinerary"],
    )
    get_db().table("documents").update(
        {"doc_type": "itinerary", "extracted": extracted}
    ).eq("id", state["document_id"]).execute()
    return {"doc_type": "itinerary", "extracted": extracted}


_ORCH_SCHEMA = {
    "type": "object",
    "properties": {
        "item": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "일정 아이템 제목, 예: '힐튼 오사카 체크인'"},
                "trip_title": {"type": "string", "description": "새 여행 생성 시 쓸 여행 이름. 반드시 이 문서에 실제로 등장하는 도시/지역명으로 '<도시명> 여행' 형식으로 만들 것. 문서에서 도시를 알 수 없으면 빈 문자열"},
                "starts_at": {"type": "string", "description": "ISO 8601, 예: 2026-09-01T15:00"},
                "ends_at": {"type": "string", "description": "ISO 8601, 없으면 빈 문자열"},
                "location": {"type": "string"},
                "summary": {"type": "string", "description": "한 줄 요약"},
            },
            "required": ["title"],
        },
        "notes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "사용자가 알아둬야 할 사항을 한국어 문장으로 — 예약 확정 여부, 현장 교환 필요 여부, 취소기한, 잔글씨 주의사항(재입장 불가, 신분증 지참 등)",
        },
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tool": {
                        "type": "string",
                        "enum": ["add_to_itinerary", "register_calendar", "record_expense"],
                    },
                    "args": {"type": "object"},
                },
                "required": ["tool"],
            },
        },
    },
    "required": ["item", "notes", "actions"],
}

_ORCH_SYSTEM = """너는 여행 문서 처리 에이전트의 orchestrator다.
분류된 문서 유형과 추출된 필드를 보고 다음을 수행한다:
1. 일정 아이템으로 정규화 (제목, 시작/종료 시각 ISO 8601, 장소, 한 줄 요약)
   - 제목은 반드시 이 문서에 실제로 등장하는 이름으로 만든다. 유형별 형식:
     hotel → "<문서의 호텔명> 체크인" / transportation → "<편명> <출발지>→<도착지>" /
     tour → 문서의 명소·공연·투어 이름 그대로. "체크인"은 hotel에만 쓴다.
   - 왕복 교통편이면 **가는 편만** 일정으로 만든다 (starts_at/ends_at = 가는 편 출발/도착).
     오는 편은 summary에 언급하고 notes에 "오는 편(날짜)은 별도 일정으로 등록 필요"를 추가한다.
2. notes 작성: 사용자가 알아둬야 할 사항을 한국어 문장 배열로 정리한다. 반드시 포함할 것:
   - 예약 확정 상태 (예: "예약이 확정되었습니다" / "예약이 아직 확정되지 않았습니다")
   - 현장 교환이 필요하면 그 사실 (예: "현장에서 실물 티켓으로 교환해야 합니다")
   - 취소기한이 있으면 오늘 기준으로 (예: "6월 15일까지 무료 취소 가능합니다")
   - 문서 잔글씨의 주의사항 (재입장 불가, 신분증 지참, 도시세 별도 등)
   문서에서 확인되는 사실만 쓰고, 해당 없는 항목은 생략한다.
3. 실행할 액션 목록 결정. 규칙:
   - add_to_itinerary는 항상 포함
   - 시작 시각이 있으면 register_calendar 포함 (캘린더 등록 시 알림도 함께 설정됨)
   - total_price가 있으면 record_expense 포함 (args: amount, currency, category, memo)
중요: 문서에 없는 정보(도시명, 날짜, 금액 등)를 절대 지어내지 마라. 알 수 없으면 빈 문자열로 둬라.
반드시 주어진 JSON 스키마 형식으로만 답하라."""


async def orchestrate(state: DocState) -> dict:
    """Solar LLM으로 조건 판단 + 액션 플랜 생성."""
    today = datetime.now().strftime("%Y-%m-%d (%A)")
    parsed_excerpt = (state.get("parsed_text") or "")[:3000]
    user_prompt = {
        "today": today,
        "target_type": state.get("target_type"),
        "doc_type": state.get("doc_type"),
        "extracted": state.get("extracted"),
        "user_note": state.get("user_text") or "",
        "document_text_excerpt": parsed_excerpt,
    }
    result = await upstage.solar_chat(
        messages=[
            {"role": "system", "content": _ORCH_SYSTEM},
            {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
        ],
        json_schema=_ORCH_SCHEMA,
    )
    item_fields = result.get("item", {})
    planned = result.get("actions", [])
    # 핵심 경로 보장: LLM이 빠뜨려도 일정 추가는 항상 실행
    if not any(a.get("tool") == "add_to_itinerary" for a in planned):
        planned.insert(0, {"tool": "add_to_itinerary", "args": {}})
    # add_to_itinerary가 다른 액션보다 먼저 오도록 정렬
    planned.sort(key=lambda a: 0 if a.get("tool") == "add_to_itinerary" else 1)
    return {
        "item_fields": item_fields,
        "notes": result.get("notes", []),
        "planned_actions": planned,
    }


_ITIN_ORCH_SCHEMA = {
    "type": "object",
    "properties": {
        "trip": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "여행 이름, 예: '로마·바르셀로나 여행'"},
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["title"],
        },
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "starts_at": {"type": "string", "description": "ISO 8601, 예: 2026-09-02T10:00. 시각 없으면 날짜만"},
                    "ends_at": {"type": "string", "description": "ISO 8601, 없으면 빈 문자열"},
                    "location": {"type": "string"},
                    "category": {"type": "string", "description": "hotel/flight/train/attraction/food/transport/other"},
                    "summary": {"type": "string", "description": "한 줄 메모"},
                },
                "required": ["title", "starts_at"],
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["trip", "items", "warnings"],
}

_ITIN_ORCH_SYSTEM = """너는 여행 계획 문서를 일정 데이터로 변환하는 orchestrator다.
추출된 여행 계획(schedule_items)을 받아 다음을 수행한다:
1. 모든 일정의 날짜/시각을 절대 ISO 8601로 정규화한다 (예: 2026-09-02T16:00).
   - "Day 2" 같은 상대 표기는 여행 시작일 기준으로 계산한다. 시작일 우선순위:
     ① 입력의 trip_start_date ② 문서에 적힌 절대 날짜 ③ 둘 다 없으면 오늘로부터 7일 뒤를
     Day 1로 가정하고 warnings에 "여행 시작일을 알 수 없어 임시 날짜로 배치했습니다"를 추가한다.
   - 연도가 없으면 여행 시작일의 연도를 쓴다. 시각이 없으면 그 날 09:00으로 둔다.
   - ends_at은 문서에 명시된 경우에만 채우고, 없으면 빈 문자열로 둔다.
2. 여행 제목(trip.title)과 시작/종료일을 정한다. 제목은 문서에 실제로 등장하는
   목적지/제목을 사용하고, 문서에 없는 지명을 지어내지 마라.
3. 시간이 물리적으로 불가능한 배치(겹침, 이동시간 무시)가 보이면 warnings에 한국어로 적는다.
4. 일정을 하나도 빠뜨리지 마라 — schedule_items의 모든 항목을 items에 포함한다.
반드시 주어진 JSON 스키마 형식으로만 답하라."""


async def orchestrate_itinerary(state: DocState) -> dict:
    """여행 계획 문서 분기 — 일정 배열 정규화 + 일괄 등록 액션 계획."""
    today = datetime.now().strftime("%Y-%m-%d (%A)")
    user_prompt = {
        "today": today,
        "trip_start_date": state.get("trip_start_date") or "",
        "extracted_itinerary": state.get("extracted"),
        "user_note": state.get("user_text") or "",
        "document_text_excerpt": (state.get("parsed_text") or "")[:6000],
    }
    result = await upstage.solar_chat(
        messages=[
            {"role": "system", "content": _ITIN_ORCH_SYSTEM},
            {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
        ],
        json_schema=_ITIN_ORCH_SCHEMA,
    )
    trip = result.get("trip", {})
    return {
        # 라우트가 여행 제목을 갱신할 때 쓰는 필드 (booking 분기와 인터페이스 통일)
        "item_fields": {"trip_title": trip.get("title"), "title": trip.get("title", "여행 계획")},
        "itinerary_items": result.get("items", []),
        "notes": result.get("warnings", []),
        "planned_actions": [{"tool": "add_itinerary_bulk", "args": {}}],
    }


async def act(state: DocState) -> dict:
    """계획된 액션을 tool registry로 dispatch. dry_run이면 실행 없이 미리보기만."""
    if state.get("dry_run"):
        from app.tools.registry import build_item_row

        results = []
        for action in state.get("planned_actions", []):
            entry = {"tool": action.get("tool"), "status": "dry_run",
                     "args": action.get("args", {})}
            if action.get("tool") == "add_to_itinerary":
                row, conflicts = build_item_row(dict(state))
                entry["would_insert"] = row
                entry["conflicts"] = conflicts
            if action.get("tool") == "add_itinerary_bulk":
                entry["would_insert_items"] = state.get("itinerary_items") or []
                entry["count"] = len(state.get("itinerary_items") or [])
            results.append(entry)
        return {"action_results": results, "item_id": None, "item_ids": []}

    results = []
    item_id = None
    item_ids: list[str] = []
    for action in state.get("planned_actions", []):
        res = dispatch(action.get("tool", ""), action.get("args", {}), dict(state))
        results.append(res)
        if res.get("tool") == "add_to_itinerary":
            if res.get("item_id"):
                item_id = res["item_id"]
                get_db().table("documents").update({"item_id": item_id}).eq(
                    "id", state["document_id"]
                ).execute()
            elif res.get("status") in ("rejected", "error"):
                # 일정이 저장되지 않았으면 캘린더 등록 등 이후 액션도 중단
                results.append({"tool": "pipeline", "status": "halted",
                                "detail": "일정이 저장되지 않아 이후 액션을 중단했습니다."})
                break
        if res.get("tool") == "add_itinerary_bulk" and res.get("item_ids"):
            item_ids = res["item_ids"]
    return {"action_results": results, "item_id": item_id, "item_ids": item_ids}
