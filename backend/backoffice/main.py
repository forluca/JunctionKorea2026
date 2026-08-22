"""Docket 백오피스 서버 (실험/디버깅용, 포트 8001 권장).

기능:
1. Upstage 단독 실험 — Classify / Parse / Extract를 DB 기록 없이 바로 호출해 결과 확인
2. 전체 파이프라인 실험 — 메인 API(POST /api/documents/parse)로 프록시 (메인 서버 필요)
3. DB 브라우저 — Supabase의 trips / items / documents 조회

실행:
    cd backend && .venv/bin/uvicorn backoffice.main:app --reload --port 8001
"""

import html
import json
import os

import httpx
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from app.db import get_db
from app.graph.schemas import CATEGORIES, EXTRACTION_SCHEMAS
from app.services import upstage

MAIN_API_URL = os.getenv("MAIN_API_URL", "http://127.0.0.1:8000")

app = FastAPI(title="Docket Backoffice")

_STYLE = """
<style>
  body { font-family: -apple-system, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; color: #222; }
  h1 { font-size: 1.4rem; } h2 { font-size: 1.1rem; margin-top: 2rem; border-bottom: 1px solid #ddd; padding-bottom: .3rem; }
  form { background: #f6f6f6; padding: 1rem; border-radius: 8px; margin: .5rem 0; }
  table { border-collapse: collapse; width: 100%; font-size: .85rem; }
  th, td { border: 1px solid #ddd; padding: .4rem .6rem; text-align: left; vertical-align: top; }
  th { background: #f0f0f0; }
  pre { background: #f6f6f6; padding: 1rem; border-radius: 8px; overflow-x: auto; font-size: .8rem; white-space: pre-wrap; }
  nav a { margin-right: 1rem; }
  input[type=submit] { padding: .3rem 1rem; cursor: pointer; }
  iframe { width: 100%; height: 480px; border: 1px solid #ddd; border-radius: 8px; background: #fff; }
</style>
"""

_NAV = """
<nav><a href="/">🏠 홈</a> <a href="/db/trips">✈️ trips</a>
<a href="/db/items">📅 items</a> <a href="/db/documents">📄 documents</a></nav>
"""


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"<title>{title}</title>{_STYLE}{_NAV}<h1>{title}</h1>{body}")


@app.get("/", response_class=HTMLResponse)
def index():
    doc_types = "".join(
        f'<option value="{t}">{t}</option>' for t in EXTRACTION_SCHEMAS
    )
    categories = "<br>".join(f"<code>{c['name']}</code> — {c['description']}" for c in CATEGORIES)
    body = f"""
    <h2>1. Upstage 단독 실험 <small>(DB에 기록하지 않음)</small></h2>
    <form action="/test/classify" method="post" enctype="multipart/form-data">
      <b>Classify</b> — 문서 유형 분류<br>
      <input type="file" name="document" required> <input type="submit" value="실행">
    </form>
    <form action="/test/parse" method="post" enctype="multipart/form-data">
      <b>Parse</b> — HTML/text 구조화<br>
      <input type="file" name="document" required> <input type="submit" value="실행">
    </form>
    <form action="/test/extract" method="post" enctype="multipart/form-data">
      <b>Extract</b> — 유형별 스키마로 필드 추출<br>
      <input type="file" name="document" required>
      <select name="doc_type">{doc_types}</select>
      <input type="submit" value="실행">
    </form>

    <h2>2. 전체 파이프라인 실험 <small>(메인 API로 프록시, DB에 기록됨 — 메인 서버가 {MAIN_API_URL}에 떠 있어야 함)</small></h2>
    <form action="/test/pipeline" method="post" enctype="multipart/form-data">
      <input type="file" name="document" required><br><br>
      targetType: <select name="targetType"><option value="trip">trip (새 여행)</option><option value="schedule">schedule (기존 여행)</option></select>
      tripId(schedule일 때): <input type="text" name="tripId" placeholder="uuid (비우면 새 여행)">
      <br><br>text(선택): <input type="text" name="text" size="50" placeholder="사용자 프롬프트">
      <input type="submit" value="파이프라인 실행 (10~20초)">
    </form>

    <h2>참고: 분류 카테고리</h2>
    <p>{categories}</p>
    """
    return _page("Docket Backoffice", body)


# ─────────────────── 1. Upstage 단독 실험 ───────────────────

async def _read(document: UploadFile) -> tuple[bytes, str, str]:
    data = await document.read()
    mime = document.content_type or "application/pdf"
    return data, document.filename or "document", mime


@app.post("/test/classify")
async def test_classify(document: UploadFile = File(...)):
    data, _, mime = await _read(document)
    label = await upstage.classify_document(data, mime, CATEGORIES)
    return JSONResponse({"doc_type": label})


@app.post("/test/parse")
async def test_parse(document: UploadFile = File(...)):
    data, name, mime = await _read(document)
    parsed = await upstage.parse_document(data, name, mime)
    return JSONResponse(
        {
            "text": parsed["text"],
            "html_length": len(parsed["html"]),
            "element_count": len(parsed["elements"]),
            "elements_preview": parsed["elements"][:5],
        }
    )


@app.post("/test/extract")
async def test_extract(document: UploadFile = File(...), doc_type: str = Form("other")):
    data, _, mime = await _read(document)
    schema = EXTRACTION_SCHEMAS.get(doc_type, EXTRACTION_SCHEMAS["other"])
    extracted = await upstage.extract_information(data, mime, f"{doc_type}_fields", schema)
    return JSONResponse({"doc_type": doc_type, "extracted": extracted})


# ─────────────────── 2. 전체 파이프라인 (메인 API 프록시) ───────────────────

@app.post("/test/pipeline")
async def test_pipeline(
    document: UploadFile = File(...),
    targetType: str = Form("trip"),
    tripId: str = Form(""),
    text: str = Form(""),
):
    data, name, mime = await _read(document)
    form: dict = {"targetType": targetType}
    if tripId.strip():
        form["tripId"] = tripId.strip()
    if text.strip():
        form["text"] = text.strip()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0)) as client:
            r = await client.post(
                f"{MAIN_API_URL}/api/documents/parse",
                files={"document": (name, data, mime)},
                data=form,
            )
        return JSONResponse(r.json(), status_code=r.status_code)
    except httpx.ConnectError:
        return JSONResponse(
            {"error": f"메인 API({MAIN_API_URL})에 연결할 수 없습니다. "
                      "`uvicorn app.main:app --port 8000`으로 먼저 실행하세요."},
            status_code=502,
        )


# ─────────────────── 3. DB 브라우저 ───────────────────

def _table(rows: list[dict], columns: list[str], link: dict | None = None) -> str:
    if not rows:
        return "<p>데이터 없음</p>"
    head = "".join(f"<th>{c}</th>" for c in columns)
    body = ""
    for r in rows:
        tds = ""
        for c in columns:
            v = r.get(c)
            v = "" if v is None else str(v)
            v = html.escape(v[:120])
            if link and c == link["column"]:
                v = f'<a href="{link["href"].format(**r)}">{v}</a>'
            tds += f"<td>{v}</td>"
        body += f"<tr>{tds}</tr>"
    return f"<table><tr>{head}</tr>{body}</table>"


@app.get("/db/trips", response_class=HTMLResponse)
def db_trips():
    rows = get_db().table("trips").select("*").order("created_at", desc=True).execute().data or []
    t = _table(rows, ["id", "title", "start_date", "end_date", "status", "created_at"],
               link={"column": "id", "href": "/db/items?trip_id={id}"})
    return _page("trips", t + "<p>id를 클릭하면 해당 여행의 items로 이동</p>")


@app.get("/db/items", response_class=HTMLResponse)
def db_items(trip_id: str | None = None):
    q = get_db().table("items").select("*")
    if trip_id:
        q = q.eq("trip_id", trip_id)
    rows = q.order("starts_at", desc=False).execute().data or []
    t = _table(rows, ["id", "trip_id", "type", "title", "starts_at", "ends_at",
                      "price", "has_conflict", "conflict_msg", "booking_ref"])
    return _page("items", t)


@app.get("/db/documents", response_class=HTMLResponse)
def db_documents():
    rows = (
        get_db().table("documents")
        .select("id,trip_id,item_id,file_name,mime_type,doc_type,created_at")
        .order("created_at", desc=True).execute().data or []
    )
    t = _table(rows, ["id", "file_name", "doc_type", "trip_id", "item_id", "created_at"],
               link={"column": "id", "href": "/db/documents/{id}"})
    return _page("documents", t + "<p>id를 클릭하면 파싱/추출 결과 상세로 이동</p>")


@app.get("/db/documents/{doc_id}", response_class=HTMLResponse)
def db_document_detail(doc_id: str):
    res = get_db().table("documents").select("*").eq("id", doc_id).execute()
    if not res.data:
        return _page("document", "<p>없음</p>")
    d = res.data[0]
    meta = {k: d.get(k) for k in ("id", "file_name", "mime_type", "doc_type",
                                  "trip_id", "item_id", "storage_path", "created_at")}
    extracted = json.dumps(d.get("extracted"), ensure_ascii=False, indent=2)
    parsed_html = d.get("parsed_html") or ""
    body = f"""
    <h2>메타데이터</h2><pre>{html.escape(json.dumps(meta, ensure_ascii=False, indent=2))}</pre>
    <h2>Extract 결과</h2><pre>{html.escape(extracted)}</pre>
    <h2>Parse 결과 (text)</h2><pre>{html.escape((d.get("parsed_text") or "")[:5000])}</pre>
    <h2>Parse 결과 (html 렌더링)</h2>
    <iframe srcdoc="{html.escape(parsed_html)}"></iframe>
    """
    return _page(f"document {d.get('file_name', '')}", body)
