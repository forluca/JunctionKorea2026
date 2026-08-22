"""LangGraph 노드 구현.

ingest → classify → (parse ∥ extract) → orchestrate → act
"""

import json
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app import config
from app.db import get_db
from app.graph.schemas import CATEGORIES, CATEGORY_NAMES, EXTRACTION_SCHEMAS
from app.graph.state import DocState
from app.services import upstage
from app.services.barcode import decode_barcodes
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
    if not state.get("dry_run"):
        get_db().table("documents").update({"doc_type": doc_type}).eq(
            "id", state["document_id"]
        ).execute()
    return {"doc_type": doc_type}


async def parse(state: DocState) -> dict:
    """Upstage Parse — HTML/text 구조화 + figure 크롭에서 QR/바코드 디코딩 (extract와 병렬).

    디코딩된 코드의 원본 크롭 이미지는 Storage에 저장하고, items에는
    {value, format, image_path} 목록(qr_images)으로 연결한다.
    """
    parsed = await upstage.parse_document(
        state["file_bytes"], state["file_name"], state["mime_type"]
    )
    decoded = decode_barcodes(parsed["elements"])
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
        db.table("documents").update(
            {"parsed_html": parsed["html"], "parsed_text": parsed["text"]}
        ).eq("id", state["document_id"]).execute()
    else:
        qr_images = [{"value": d["value"], "format": d["format"],
                      "image_path": "(dry-run: 저장 안 함)"} for d in decoded]
    return {
        "parsed_html": parsed["html"],
        "parsed_text": parsed["text"],
        "qr_codes": qr_codes,
        "qr_images": qr_images,
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


async def trip_flow_placeholder(state: DocState) -> dict:
    """trip(전체 여행 계획 문서) 플로우 — 아직 미구현. ingest(파일 저장)까지만 수행됨.

    TODO: 플로우 확정 시 아래 미배선 노드들을 build.py에 연결할 것:
    extract_itinerary(일정 배열 추출) → orchestrate_itinerary(날짜 정규화) → act(add_itinerary_bulk)
    """
    return {
        "planned_actions": [],
        "action_results": [{"tool": "trip_flow", "status": "not_implemented"}],
        "notes": ["여행 계획 문서(trip) 처리 플로우는 아직 구현되지 않았습니다."],
    }


# ── 아래 노드는 trip 플로우용으로 작성해둔 미배선 상태 (build.py에 연결 안 됨) ──

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
                        "enum": ["add_to_itinerary", "register_calendar", "set_reminder", "record_expense"],
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
   - 제목은 문서 유형에 맞게: hotel → "○○호텔 체크인", transportation → "KE937 인천→비엔나",
     tour → 그냥 명소/공연 이름 (예: "사그라다 파밀리아 입장"). "체크인"은 hotel에만 쓴다.
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
   - 시작 시각이 있으면 register_calendar 포함
   - 취소기한이 남아 있으면 그 하루 전으로 set_reminder 포함 (args: remind_at, message)
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
1. 모든 일정의 날짜/시각을 절대 ISO 8601로 정규화한다.
   - "Day 2" 같은 상대 표기는 start_date 기준으로 계산한다.
   - 연도가 없으면 여행 시작일의 연도를 쓴다. 시각이 없으면 날짜만(T 없이) 쓴다.
2. 여행 제목과 시작/종료일을 정한다 (없으면 일정들로부터 추론).
3. 시간이 물리적으로 불가능한 배치(겹침, 이동시간 무시)가 보이면 warnings에 한국어로 적는다.
반드시 주어진 JSON 스키마 형식으로만 답하라."""


async def orchestrate_itinerary(state: DocState) -> dict:
    """여행 계획 문서 분기 — 일정 배열 정규화 + 일괄 등록 액션 계획."""
    today = datetime.now().strftime("%Y-%m-%d (%A)")
    user_prompt = {
        "today": today,
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
            results.append(entry)
        return {"action_results": results, "item_id": None, "item_ids": []}

    results = []
    item_id = None
    item_ids: list[str] = []
    for action in state.get("planned_actions", []):
        res = dispatch(action.get("tool", ""), action.get("args", {}), dict(state))
        results.append(res)
        if res.get("tool") == "add_to_itinerary" and res.get("item_id"):
            item_id = res["item_id"]
            get_db().table("documents").update({"item_id": item_id}).eq(
                "id", state["document_id"]
            ).execute()
        if res.get("tool") == "add_itinerary_bulk" and res.get("item_ids"):
            item_ids = res["item_ids"]
    return {"action_results": results, "item_id": item_id, "item_ids": item_ids}
