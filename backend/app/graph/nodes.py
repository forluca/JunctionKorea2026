"""LangGraph 노드 구현.

ingest → classify → (parse ∥ extract) → orchestrate → act
"""

import json
from datetime import datetime
from uuid import uuid4

from app import config
from app.db import get_db
from app.graph.schemas import CATEGORIES, CATEGORY_NAMES, EXTRACTION_SCHEMAS
from app.graph.state import DocState
from app.services import upstage
from app.tools.registry import dispatch


async def ingest(state: DocState) -> dict:
    """원본 파일을 Supabase Storage에 저장하고 documents 레코드를 만든다."""
    db = get_db()
    storage_path = f"{uuid4().hex}_{state['file_name']}"
    db.storage.from_(config.STORAGE_BUCKET).upload(
        storage_path,
        state["file_bytes"],
        {"content-type": state["mime_type"]},
    )
    row = {
        "trip_id": state.get("trip_id"),
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
    get_db().table("documents").update({"doc_type": doc_type}).eq(
        "id", state["document_id"]
    ).execute()
    return {"doc_type": doc_type}


async def parse(state: DocState) -> dict:
    """Upstage Parse — HTML/text 구조화 (extract와 병렬, 결과는 뷰어/Q&A용으로 저장)."""
    parsed = await upstage.parse_document(
        state["file_bytes"], state["file_name"], state["mime_type"]
    )
    get_db().table("documents").update(
        {"parsed_html": parsed["html"], "parsed_text": parsed["text"]}
    ).eq("id", state["document_id"]).execute()
    return {"parsed_html": parsed["html"], "parsed_text": parsed["text"]}


async def extract(state: DocState) -> dict:
    """Upstage Extract — 문서 유형별 스키마로 핵심 필드 추출 (parse와 병렬)."""
    doc_type = state.get("doc_type", "other")
    schema = EXTRACTION_SCHEMAS.get(doc_type, EXTRACTION_SCHEMAS["other"])
    extracted = await upstage.extract_information(
        state["file_bytes"], state["mime_type"], f"{doc_type}_fields", schema
    )
    get_db().table("documents").update({"extracted": extracted}).eq(
        "id", state["document_id"]
    ).execute()
    return {"extracted": extracted}


_ORCH_SCHEMA = {
    "type": "object",
    "properties": {
        "item": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "일정 아이템 제목, 예: '힐튼 오사카 체크인'"},
                "trip_title": {"type": "string", "description": "새 여행 생성 시 쓸 여행 이름, 예: '오사카 여행'"},
                "starts_at": {"type": "string", "description": "ISO 8601, 예: 2026-09-01T15:00"},
                "ends_at": {"type": "string", "description": "ISO 8601, 없으면 빈 문자열"},
                "location": {"type": "string"},
                "summary": {"type": "string", "description": "한 줄 요약"},
            },
            "required": ["title"],
        },
        "judgments": {
            "type": "object",
            "properties": {
                "confirmed": {"type": "string", "enum": ["yes", "no", "unknown"]},
                "onsite_exchange_required": {"type": "string", "enum": ["yes", "no", "unknown"]},
                "cancellation_deadline_open": {"type": "string", "enum": ["yes", "no", "unknown"]},
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["confirmed", "onsite_exchange_required", "cancellation_deadline_open", "warnings"],
        },
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tool": {
                        "type": "string",
                        "enum": ["add_to_itinerary", "register_calendar", "set_reminder", "record_expense"],
                    },
                    "args": {"type": "object"},
                },
                "required": ["tool"],
            },
        },
    },
    "required": ["item", "judgments", "actions"],
}

_ORCH_SYSTEM = """너는 여행 문서 처리 에이전트의 orchestrator다.
분류된 문서 유형과 추출된 필드를 보고 다음을 수행한다:
1. 일정 아이템으로 정규화 (제목, 시작/종료 시각 ISO 8601, 장소, 한 줄 요약)
2. 조건 판단: 예약 확정 여부 / 현장 교환 필요 여부 / 취소기한이 아직 남았는지 (오늘 날짜 기준)
3. 실행할 액션 목록 결정. 규칙:
   - add_to_itinerary는 항상 포함
   - 시작 시각이 있으면 register_calendar 포함
   - 취소기한이 남아 있으면 그 하루 전으로 set_reminder 포함 (args: remind_at, message)
   - total_price가 있으면 record_expense 포함 (args: amount, currency, category, memo)
4. 사용자가 주의해야 할 사항을 warnings에 한국어로 정리 (현장 교환 필요, 재입장 불가, 신분증 지참 등)
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
        "judgments": result.get("judgments", {}),
        "planned_actions": planned,
    }


async def act(state: DocState) -> dict:
    """계획된 액션을 tool registry로 dispatch."""
    results = []
    item_id = None
    for action in state.get("planned_actions", []):
        res = dispatch(action.get("tool", ""), action.get("args", {}), dict(state))
        results.append(res)
        if res.get("tool") == "add_to_itinerary" and res.get("item_id"):
            item_id = res["item_id"]
            get_db().table("documents").update({"item_id": item_id}).eq(
                "id", state["document_id"]
            ).execute()
    return {"action_results": results, "item_id": item_id}
