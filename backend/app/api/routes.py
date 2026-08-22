"""README의 API 계약에 맞춘 라우트.

- POST /api/documents/parse        문서 업로드 → 에이전트 그래프 실행 → 여행/일정 생성
- GET  /api/trips                  여행 목록
- GET  /api/trips/{trip_id}/items  여행 일정 타임라인
- GET  /api/items/{item_id}        일정 상세
"""

import mimetypes
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app import config
from app.db import ensure_bucket, get_db
from app.graph.build import GRAPH

router = APIRouter()

# Upstage 문서 API 공통 지원 형식 (50MB, 동기 100페이지 제한)
_ALLOWED_MIME = {
    "application/pdf",
    "image/jpeg", "image/png", "image/bmp", "image/tiff",
    "image/heic", "image/heif",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # docx
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # pptx
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # xlsx
}
# 브라우저/OS가 mime을 못 주는 경우(HEIC, HWP 등)를 위한 확장자 fallback
_ALLOWED_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff",
                ".heic", ".heif", ".docx", ".pptx", ".xlsx", ".hwp", ".hwpx"}

# 여행 기간 계산에서 도착 시각을 제외할 교통편 유형들 (schedule 유형 + itinerary category)
_TRANSPORT_TYPES = {"transportation", "transport", "flight", "train", "bus", "ferry"}


@router.post("/documents/parse")
async def parse_document(
    document: UploadFile = File(...),
    targetType: str = Form("schedule"),
    tripId: str | None = Form(None),
    text: str | None = Form(None),
    startDate: str | None = Form(None),
    dryRun: str = Form(""),
):
    file_bytes = await document.read()
    if not file_bytes:
        raise HTTPException(400, "빈 파일입니다.")
    mime = document.content_type or mimetypes.guess_type(document.filename or "")[0]
    ext = Path(document.filename or "").suffix.lower()
    if mime not in _ALLOWED_MIME and ext not in _ALLOWED_EXT:
        raise HTTPException(
            415, f"지원하지 않는 형식: {mime or ext} "
                 "(PDF/이미지(JPG·PNG·HEIC 등)/DOCX/PPTX/XLSX/HWP 가능)")
    if mime is None or mime == "application/octet-stream":
        mime = mimetypes.guess_type(document.filename or "")[0] or "application/pdf"

    dry = dryRun.strip().lower() in ("1", "true", "yes", "on")
    db = get_db()

    created_trip = None
    if dry:
        # dry run: 여행 생성 없이 미리보기만. tripId가 있으면 충돌 검사에 사용
        trip_id = tripId or None
    elif targetType == "trip" or not tripId:
        # targetType=trip 이거나 tripId가 없으면 새 여행 생성 (제목/기간은 처리 후 채움)
        ensure_bucket()
        created_trip = (
            db.table("trips").insert({"title": "새 여행", "status": "active"}).execute().data[0]
        )
        trip_id = created_trip["id"]
    else:
        # tripId가 실제 존재하는 여행인지 검증 (FK 에러 대신 명확한 404)
        exists = db.table("trips").select("id").eq("id", tripId).execute().data
        if not exists:
            raise HTTPException(
                404,
                f"tripId '{tripId}'에 해당하는 여행이 없습니다. "
                "GET /api/trips로 존재하는 여행 id를 확인하거나, tripId를 비워 새 여행을 생성하세요.",
            )
        ensure_bucket()
        trip_id = tripId

    state = {
        "file_bytes": file_bytes,
        "file_name": document.filename or "document",
        "mime_type": mime,
        "target_type": targetType,
        "trip_id": trip_id,
        "user_text": text,
        "trip_start_date": (startDate or "").strip() or None,
        "dry_run": dry,
    }
    result = await GRAPH.ainvoke(state)

    if dry:
        item_fields = result.get("item_fields") or {}
        would_insert = next(
            (r.get("would_insert") for r in result.get("action_results", [])
             if r.get("tool") == "add_to_itinerary"),
            None,
        )
        conflicts = next(
            (r.get("conflicts") for r in result.get("action_results", [])
             if r.get("tool") == "add_to_itinerary"),
            [],
        )
        return {
            "dryRun": True,
            "docType": result.get("doc_type"),
            "wouldCreate": {
                "trip": (None if tripId else {"title": item_fields.get("trip_title")
                                              or item_fields.get("title") or "새 여행"}),
                "item": would_insert,
            },
            "extracted": result.get("extracted"),
            "notes": result.get("notes", []),
            "conflicts": conflicts or [],
            "actions": result.get("action_results", []),
        }

    # 충돌/중복으로 거부된 경우: 409 + 프론트용 에러 메시지
    add_res = next(
        (r for r in result.get("action_results", [])
         if r.get("tool") == "add_to_itinerary" and r.get("status") == "rejected"),
        None,
    )
    if add_res:
        return JSONResponse(
            {
                "error": "rejected",
                "reason": add_res.get("reason", "overlap"),  # duplicate | overlap
                "message": add_res.get("detail", "일정을 추가할 수 없습니다."),
                "conflicts": add_res.get("conflicts", []),
                "documentId": result.get("document_id"),
                "docType": result.get("doc_type"),
                "notes": result.get("notes", []),
            },
            status_code=409,
        )

    # 여행 제목(새 여행일 때)과 기간을 일정 기준으로 갱신
    # trip_title이 없으면(Studio Agent 출력엔 없음) 일정 제목으로 fallback
    item_fields = result.get("item_fields") or {}
    new_title = item_fields.get("trip_title") or item_fields.get("title")
    if created_trip is not None and new_title:
        db.table("trips").update({"title": new_title}).eq("id", trip_id).execute()
    _update_trip_range(trip_id)

    item = None
    if result.get("item_id"):
        item = db.table("items").select("*").eq("id", result["item_id"]).single().execute().data
    # itinerary(여행 계획 문서) 분기 — 일괄 생성된 일정 전체
    items = []
    if result.get("item_ids"):
        items = (
            db.table("items").select("*").in_("id", result["item_ids"])
            .order("starts_at", desc=False).execute().data or []
        )
    trip = db.table("trips").select("*").eq("id", trip_id).single().execute().data

    conflicts = next(
        (r.get("conflicts") for r in result.get("action_results", [])
         if r.get("tool") in ("add_to_itinerary", "add_itinerary_bulk")),
        [],
    )
    return {
        "documentId": result.get("document_id"),
        "docType": result.get("doc_type"),
        "trip": _trip_out(trip),
        "item": _item_out(item) if item else None,
        "items": [_item_out(i) for i in items],
        "extracted": result.get("extracted"),
        "notes": result.get("notes", []),
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
        {**_trip_out(t), "conflict_count": conflict_count.get(t["id"], 0)} for t in trips
    ]


@router.get("/trips/{trip_id}/items")
async def list_trip_items(trip_id: str):
    rows = (
        get_db().table("items").select("*").eq("trip_id", trip_id)
        .order("starts_at", desc=False).execute().data or []
    )
    # 모든 DB 컬럼(camelCase) + 타임라인용 computed 필드(time, desc)
    return [
        {
            **_item_out(r),
            "time": _hhmm(r.get("starts_at")),
            "desc": r.get("location") or "",
        }
        for r in rows
    ]


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    """문서 상세 — 모든 컬럼 + 원본 파일 서명 URL(24시간) + 파싱 결과.

    프론트 '원본 문서 보기': originalUrl을 <iframe>/<embed>·새 탭으로 열거나,
    parsedHtml을 직접 렌더링하면 됨 (HWP 등 뷰어 없는 형식도 표시 가능).
    """
    res = get_db().table("documents").select("*").eq("id", doc_id).execute()
    if not res.data:
        raise HTTPException(404, "document not found")
    d = res.data[0]
    original_url = None
    if d.get("storage_path"):
        try:
            signed = get_db().storage.from_(config.STORAGE_BUCKET).create_signed_url(
                d["storage_path"], 86400
            )
            original_url = (signed.get("signedURL") or signed.get("signed_url")
                            or signed.get("signedUrl"))
        except Exception:
            original_url = None
    return {**d, "original_url": original_url}


@router.get("/items/{item_id}")
async def get_item(item_id: str):
    res = get_db().table("items").select("*").eq("id", item_id).execute()
    if not res.data:
        raise HTTPException(404, "item not found")
    r = res.data[0]
    # 연결된 원본 문서의 서명 URL (24시간) — "원본 문서 보기"용
    document_url = None
    document_file_name = None
    if r.get("document_id"):
        doc = (get_db().table("documents").select("storage_path,file_name")
               .eq("id", r["document_id"]).execute().data or [])
        if doc and doc[0].get("storage_path"):
            document_file_name = doc[0].get("file_name")
            try:
                signed = get_db().storage.from_(config.STORAGE_BUCKET).create_signed_url(
                    doc[0]["storage_path"], 86400
                )
                document_url = (signed.get("signedURL") or signed.get("signed_url")
                                or signed.get("signedUrl"))
            except Exception:
                document_url = None

    # 모든 DB 컬럼(필드명 그대로) + 상세용 computed 필드
    # (qr_images는 raw 경로 대신 서명 URL 버전으로 덮어씀)
    return {
        **_item_out(r),
        "time_str": _time_range(r.get("starts_at"), r.get("ends_at")),
        "qr_images": _signed_qr_images(r.get("qr_images")),
        "document_url": document_url,
        "document_file_name": document_file_name,
    }


def _signed_qr_images(qr_images: list | None) -> list[dict]:
    """items.qr_images의 Storage 경로를 24시간짜리 서명 URL로 변환해 반환."""
    out = []
    for qi in qr_images or []:
        path = qi.get("image_path") or ""
        url = None
        if path and not path.startswith("("):
            try:
                signed = get_db().storage.from_(config.STORAGE_BUCKET).create_signed_url(path, 86400)
                url = signed.get("signedURL") or signed.get("signed_url") or signed.get("signedUrl")
            except Exception:
                url = None
        out.append({"value": qi.get("value"), "format": qi.get("format"), "url": url})
    return out


# ─────────────────────────── helpers ───────────────────────────

# 응답 필드명 규칙 (프론트와 합의): DB 컬럼명(snake_case) 그대로 반환.
# computed 필드도 snake_case로 통일 (status, conflict_count, time, desc, time_str,
# qr_code_str, qr_images, document_url, original_url)


def _trip_out(t: dict | None) -> dict | None:
    if not t:
        return None
    # status는 저장값이 아니라 조회 시점 계산: 여행 종료일이 지났으면 past, 아니면 active
    # (여행 전/여행 중/종료일 당일 = active, end_date 없음(빈 여행) = active)
    end_date = t.get("end_date")
    today = datetime.now().date().isoformat()
    status = "past" if end_date and end_date < today else "active"
    return {**t, "status": status}


def _item_out(r: dict) -> dict:
    """items 행의 모든 컬럼(DB 필드명 그대로) + computed 필드."""
    return {
        **r,
        "conflict_msg": r.get("conflict_msg") or "",
        "qr_code_str": r.get("qr_code") or r.get("booking_ref") or "",
        "notes": r.get("notes") or [],
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
    """여행 기간을 일정 범위에 맞춰 갱신 — 단조 확장(늘어나기만 하고 줄어들지 않음).

    범위 밖 일정이 추가되면 그 일정까지 포함하도록 넓히고,
    기존 기간보다 좁아지는 방향으로는 절대 갱신하지 않는다.
    """
    db = get_db()
    rows = db.table("items").select("type,starts_at,ends_at").eq("trip_id", trip_id).execute().data or []
    dates = []
    for r in rows:
        s = _dt(r.get("starts_at"))
        if s:
            dates.append(s)
        # 교통편은 출발 날짜만 반영 — 귀국편 도착일(다음날 새벽 등)이
        # 여행 종료일을 늘리지 않도록 도착 시각(ends_at)은 제외
        if (r.get("type") or "").lower() not in _TRANSPORT_TYPES:
            e = _dt(r.get("ends_at"))
            if e:
                dates.append(e)
    if not dates:
        return
    new_start = min(dates).date().isoformat()
    new_end = max(dates).date().isoformat()

    trip = db.table("trips").select("start_date,end_date").eq("id", trip_id).single().execute().data or {}
    cur_start, cur_end = trip.get("start_date"), trip.get("end_date")
    # 기존 기간이 있으면 더 넓은 쪽만 채택
    start = min(new_start, cur_start) if cur_start else new_start
    end = max(new_end, cur_end) if cur_end else new_end
    if start == cur_start and end == cur_end:
        return
    db.table("trips").update({"start_date": start, "end_date": end}).eq("id", trip_id).execute()
