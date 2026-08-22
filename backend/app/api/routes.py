"""README의 API 계약에 맞춘 라우트.

- POST /api/documents/parse        문서 업로드 → 에이전트 그래프 실행 → 여행/일정 생성
- GET  /api/trips                  여행 목록
- GET  /api/trips/{trip_id}/items  여행 일정 타임라인
- GET  /api/items/{item_id}        일정 상세
"""

import mimetypes
from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.db import ensure_bucket, get_db
from app.graph.build import GRAPH

router = APIRouter()

_ALLOWED_MIME = {"application/pdf", "image/jpeg", "image/png"}


@router.post("/documents/parse")
async def parse_document(
    document: UploadFile = File(...),
    targetType: str = Form("schedule"),
    tripId: str | None = Form(None),
    text: str | None = Form(None),
):
    file_bytes = await document.read()
    if not file_bytes:
        raise HTTPException(400, "빈 파일입니다.")
    mime = document.content_type or mimetypes.guess_type(document.filename or "")[0]
    if mime not in _ALLOWED_MIME:
        raise HTTPException(415, f"지원하지 않는 형식: {mime} (PDF/JPG/PNG만 가능)")

    db = get_db()
    ensure_bucket()

    # targetType=trip 이거나 tripId가 없으면 새 여행 생성 (제목/기간은 처리 후 채움)
    created_trip = None
    if targetType == "trip" or not tripId:
        created_trip = (
            db.table("trips").insert({"title": "새 여행", "status": "active"}).execute().data[0]
        )
        trip_id = created_trip["id"]
    else:
        trip_id = tripId

    state = {
        "file_bytes": file_bytes,
        "file_name": document.filename or "document",
        "mime_type": mime,
        "target_type": targetType,
        "trip_id": trip_id,
        "user_text": text,
    }
    result = await GRAPH.ainvoke(state)

    # 여행 제목(새 여행일 때)과 기간을 일정 기준으로 갱신
    item_fields = result.get("item_fields") or {}
    if created_trip is not None and item_fields.get("trip_title"):
        db.table("trips").update({"title": item_fields["trip_title"]}).eq("id", trip_id).execute()
    _update_trip_range(trip_id)

    item = None
    if result.get("item_id"):
        item = db.table("items").select("*").eq("id", result["item_id"]).single().execute().data
    trip = db.table("trips").select("*").eq("id", trip_id).single().execute().data

    judgments = result.get("judgments") or {}
    conflicts = next(
        (r.get("conflicts") for r in result.get("action_results", [])
         if r.get("tool") == "add_to_itinerary"),
        [],
    )
    return {
        "documentId": result.get("document_id"),
        "docType": result.get("doc_type"),
        "trip": _trip_out(trip),
        "item": _item_out(item) if item else None,
        "extracted": result.get("extracted"),
        "judgments": judgments,
        "warnings": judgments.get("warnings", []),
        "conflicts": conflicts or [],
        "actions": result.get("action_results", []),
    }


@router.get("/trips")
async def list_trips():
    db = get_db()
    trips = db.table("trips").select("*").order("created_at", desc=True).execute().data or []
    items = db.table("items").select("trip_id,has_conflict").execute().data or []
    conflict_count: dict[str, int] = {}
    for it in items:
        if it.get("has_conflict"):
            conflict_count[it["trip_id"]] = conflict_count.get(it["trip_id"], 0) + 1
    return [
        {**_trip_out(t), "conflictCount": conflict_count.get(t["id"], 0)} for t in trips
    ]


@router.get("/trips/{trip_id}/items")
async def list_trip_items(trip_id: str):
    rows = (
        get_db().table("items").select("*").eq("trip_id", trip_id)
        .order("starts_at", desc=False).execute().data or []
    )
    return [
        {
            "id": r["id"],
            "type": r.get("type"),
            "time": _hhmm(r.get("starts_at")),
            "title": r.get("title"),
            "desc": r.get("location") or r.get("notes") or "",
            "price": r.get("price"),
            "hasConflict": bool(r.get("has_conflict")),
            "conflictMsg": r.get("conflict_msg") or "",
        }
        for r in rows
    ]


@router.get("/items/{item_id}")
async def get_item(item_id: str):
    res = get_db().table("items").select("*").eq("id", item_id).execute()
    if not res.data:
        raise HTTPException(404, "item not found")
    r = res.data[0]
    return {
        "id": r["id"],
        "title": r.get("title"),
        "timeStr": _time_range(r.get("starts_at"), r.get("ends_at")),
        "price": r.get("price"),
        "hasConflict": bool(r.get("has_conflict")),
        "conflictDetail": r.get("conflict_msg") or "",
        "qrCodeStr": r.get("qr_code") or r.get("booking_ref") or "",
    }


# ─────────────────────────── helpers ───────────────────────────

def _trip_out(t: dict | None) -> dict | None:
    if not t:
        return None
    return {
        "id": t["id"],
        "title": t.get("title"),
        "startDate": t.get("start_date"),
        "endDate": t.get("end_date"),
        "status": t.get("status", "active"),
    }


def _item_out(r: dict) -> dict:
    return {
        "id": r["id"],
        "type": r.get("type"),
        "title": r.get("title"),
        "startsAt": r.get("starts_at"),
        "endsAt": r.get("ends_at"),
        "location": r.get("location"),
        "price": r.get("price"),
        "hasConflict": bool(r.get("has_conflict")),
        "conflictMsg": r.get("conflict_msg") or "",
        "qrCodeStr": r.get("qr_code") or r.get("booking_ref") or "",
    }


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _hhmm(value: str | None) -> str:
    dt = _dt(value)
    return dt.strftime("%H:%M") if dt else ""


def _time_range(start: str | None, end: str | None) -> str:
    s, e = _dt(start), _dt(end)
    if not s:
        return ""
    if e and e.date() == s.date():
        return f"{s.strftime('%Y-%m-%d %H:%M')} ~ {e.strftime('%H:%M')}"
    if e:
        return f"{s.strftime('%Y-%m-%d %H:%M')} ~ {e.strftime('%Y-%m-%d %H:%M')}"
    return s.strftime("%Y-%m-%d %H:%M")


def _update_trip_range(trip_id: str) -> None:
    db = get_db()
    rows = db.table("items").select("starts_at,ends_at").eq("trip_id", trip_id).execute().data or []
    dates = [d for r in rows for d in (_dt(r.get("starts_at")), _dt(r.get("ends_at"))) if d]
    if not dates:
        return
    db.table("trips").update(
        {"start_date": min(dates).date().isoformat(), "end_date": max(dates).date().isoformat()}
    ).eq("id", trip_id).execute()
