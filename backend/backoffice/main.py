"""Docket 백오피스 서버 (실험/디버깅용, 포트 8001 권장).

기능:
1. Playground — Classify / Parse / Extract를 DB 기록 없이 단독 호출, 전체 파이프라인 프록시
2. DB 브라우저 — Supabase의 trips / items / documents 조회

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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
    """실험 도중 에러가 나면 원인이 보이는 JSON으로 반환."""
    detail = str(exc)[:800]
    if hasattr(exc, "response") and getattr(exc, "response", None) is not None:
        try:
            detail = f"HTTP {exc.response.status_code}: {exc.response.text[:600]}"
        except Exception:
            pass
    return JSONResponse({"error": type(exc).__name__, "detail": detail}, status_code=500)

# ─────────────────────────── 디자인 셸 ───────────────────────────

_CSS = """
<style>
  :root {
    --bg: #f6f7f9; --card: #ffffff; --border: #e6e8ec;
    --text: #16181d; --muted: #7a7f8a;
    --accent: #4f46e5; --accent-soft: #eef2ff; --accent-border: #c7d2fe;
    --ok: #16a34a; --warn: #d97706; --bad: #dc2626;
    --code-bg: #14161c; --code-text: #e5e7eb;
    --radius: 14px;
    --shadow: 0 1px 2px rgba(16,24,40,.05), 0 4px 16px rgba(16,24,40,.05);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Pretendard", "Apple SD Gothic Neo", sans-serif;
    font-size: 14.5px; line-height: 1.55;
  }
  header {
    position: sticky; top: 0; z-index: 10;
    background: rgba(255,255,255,.85); backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--border);
  }
  .header-inner {
    max-width: 1080px; margin: 0 auto; padding: 12px 24px;
    display: flex; align-items: center; gap: 20px;
  }
  .logo { font-weight: 700; font-size: 15.5px; letter-spacing: -.01em; }
  .logo .dot { color: var(--accent); }
  nav { display: flex; gap: 4px; flex: 1; }
  nav a {
    color: var(--muted); text-decoration: none; padding: 6px 12px;
    border-radius: 8px; font-weight: 500;
  }
  nav a:hover { background: var(--accent-soft); color: var(--accent); }
  nav a.active { background: var(--accent-soft); color: var(--accent); }
  .api-status { display: flex; align-items: center; gap: 7px; color: var(--muted); font-size: 13px; }
  .api-status .led { width: 8px; height: 8px; border-radius: 50%; background: #d1d5db; }
  .api-status.up .led { background: var(--ok); box-shadow: 0 0 0 3px rgba(22,163,74,.15); }
  .api-status.down .led { background: var(--bad); box-shadow: 0 0 0 3px rgba(220,38,38,.12); }

  main { max-width: 1080px; margin: 0 auto; padding: 28px 24px 80px; }
  h1 { font-size: 20px; letter-spacing: -.02em; margin: 4px 0 4px; }
  .subtitle { color: var(--muted); margin: 0 0 24px; }
  h2.section {
    font-size: 12.5px; text-transform: uppercase; letter-spacing: .08em;
    color: var(--muted); margin: 36px 0 12px; font-weight: 600;
  }

  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 860px) { .grid { grid-template-columns: 1fr; } }
  .card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: var(--radius); box-shadow: var(--shadow);
    padding: 20px; display: flex; flex-direction: column; gap: 12px;
  }
  .card.wide { grid-column: 1 / -1; }
  .card-head { display: flex; align-items: baseline; gap: 10px; }
  .card-title { font-weight: 650; font-size: 15.5px; }
  .card-desc { color: var(--muted); font-size: 13px; }

  .drop {
    border: 1.5px dashed #cdd2da; border-radius: 10px;
    padding: 18px; text-align: center; color: var(--muted);
    cursor: pointer; transition: all .15s ease; background: #fafbfc;
  }
  .drop:hover, .drop.over { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); }
  .drop.hasfile { border-style: solid; border-color: var(--accent-border); background: var(--accent-soft); color: var(--text); }
  .drop .fname { font-weight: 600; }
  .drop small { display: block; margin-top: 2px; font-size: 12px; opacity: .8; }

  .controls { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; }
  select, input[type=text] {
    border: 1px solid var(--border); border-radius: 8px; padding: 7px 10px;
    font: inherit; background: #fff; color: var(--text); width: 100%;
  }
  .field { display: flex; flex-direction: column; gap: 4px; flex: 1; min-width: 150px; }
  .field-name {
    font: 600 11px/1 "SF Mono", ui-monospace, Menlo, monospace;
    color: var(--muted); letter-spacing: .04em;
  }
  .field-name .req { color: var(--bad); }
  .field-name .opt { color: #b0b4bd; font-weight: 500; }
  label.toggle {
    display: flex; align-items: center; gap: 7px; cursor: pointer;
    border: 1px solid var(--border); border-radius: 8px; padding: 7px 12px;
    background: #fff; user-select: none; white-space: nowrap;
  }
  label.toggle:has(input:checked) {
    border-color: var(--accent-border); background: var(--accent-soft); color: var(--accent); font-weight: 600;
  }
  label.toggle input { accent-color: var(--accent); }
  button.run {
    border: 0; border-radius: 9px; padding: 8px 18px; font: inherit; font-weight: 600;
    background: var(--accent); color: #fff; cursor: pointer; transition: filter .15s;
    display: inline-flex; align-items: center; gap: 8px;
  }
  button.run:hover { filter: brightness(1.08); }
  button.run:disabled { background: #c7cad1; cursor: not-allowed; }
  .spinner {
    width: 13px; height: 13px; border-radius: 50%;
    border: 2px solid rgba(255,255,255,.4); border-top-color: #fff;
    animation: spin .7s linear infinite; display: none;
  }
  .running .spinner { display: inline-block; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .status { font-size: 12.5px; color: var(--muted); min-height: 18px; }
  .status.ok { color: var(--ok); } .status.err { color: var(--bad); }

  pre.result {
    background: var(--code-bg); color: var(--code-text); border-radius: 10px;
    padding: 14px 16px; margin: 0; overflow-x: auto; max-height: 420px; overflow-y: auto;
    font: 12.5px/1.6 "SF Mono", ui-monospace, Menlo, Consolas, monospace;
    white-space: pre-wrap; word-break: break-word; display: none;
  }
  pre.result.show { display: block; }
  .j-key { color: #93c5fd; } .j-str { color: #86efac; }
  .j-num { color: #fcd34d; } .j-bool { color: #f0abfc; } .j-null { color: #94a3b8; }

  table {
    border-collapse: separate; border-spacing: 0; width: 100%;
    background: var(--card); border: 1px solid var(--border);
    border-radius: var(--radius); overflow: hidden; box-shadow: var(--shadow);
    font-size: 13.5px;
  }
  th, td { padding: 10px 14px; text-align: left; vertical-align: top; }
  th {
    background: #fafbfc; color: var(--muted); font-size: 12px;
    text-transform: uppercase; letter-spacing: .05em; font-weight: 600;
    border-bottom: 1px solid var(--border);
  }
  tr + tr td { border-top: 1px solid #f0f1f4; }
  tbody tr:hover td { background: #fafbff; }
  td a { color: var(--accent); text-decoration: none; font-weight: 500; }
  td a:hover { text-decoration: underline; }

  .badge {
    display: inline-block; padding: 2px 9px; border-radius: 999px;
    font-size: 12px; font-weight: 600; background: var(--accent-soft); color: var(--accent);
  }
  .badge.gray { background: #f1f2f4; color: var(--muted); }
  .badge.red { background: #fee2e2; color: var(--bad); }
  .badge.green { background: #dcfce7; color: var(--ok); }

  .empty {
    background: var(--card); border: 1px dashed var(--border); border-radius: var(--radius);
    padding: 40px; text-align: center; color: var(--muted);
  }
  .hint { color: var(--muted); font-size: 13px; margin: 10px 2px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chips code {
    background: #f1f2f4; border-radius: 6px; padding: 2px 8px;
    font: 12px "SF Mono", ui-monospace, Menlo, monospace;
  }
  iframe.doc {
    width: 100%; height: 520px; border: 1px solid var(--border);
    border-radius: var(--radius); background: #fff; box-shadow: var(--shadow);
  }
  pre.plain {
    background: var(--card); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 16px; overflow-x: auto; font: 12.5px/1.6 "SF Mono", ui-monospace, Menlo, monospace;
    white-space: pre-wrap; word-break: break-word; box-shadow: var(--shadow);
  }
</style>
"""


def _shell(title: str, body: str, active: str = "") -> HTMLResponse:
    def nav_cls(name: str) -> str:
        return ' class="active"' if name == active else ""

    page = f"""<!doctype html><html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · Docket Backoffice</title>{_CSS}</head>
<body>
<header><div class="header-inner">
  <div class="logo">Docket <span class="dot">Backoffice</span></div>
  <nav>
    <a href="/"{nav_cls('home')}>Playground</a>
    <a href="/db/trips"{nav_cls('trips')}>Trips</a>
    <a href="/db/items"{nav_cls('items')}>Items</a>
    <a href="/db/documents"{nav_cls('documents')}>Documents</a>
  </nav>
  <div class="api-status" id="apiStatus"><span class="led"></span><span id="apiStatusText">main api</span></div>
</div></header>
<main>{body}</main>
<script>
(async () => {{
  const el = document.getElementById('apiStatus');
  const txt = document.getElementById('apiStatusText');
  // 원격 접속자는 자신의 localhost가 아니라 이 페이지를 서빙한 호스트를 체크해야 함
  let base = '{MAIN_API_URL}';
  if (/127\\.0\\.0\\.1|localhost/.test(base) && !/127\\.0\\.0\\.1|localhost/.test(location.hostname)) {{
    base = location.protocol + '//' + location.hostname + ':' + (new URL(base).port || '8000');
  }}
  try {{
    const r = await fetch(base + '/health', {{signal: AbortSignal.timeout(2500)}});
    if (r.ok) {{ el.classList.add('up'); txt.textContent = 'main api 연결됨'; return; }}
    throw 0;
  }} catch {{ el.classList.add('down'); txt.textContent = 'main api 꺼짐'; }}
}})();
</script>
</body></html>"""
    return HTMLResponse(page)


# ─────────────────────────── Playground ───────────────────────────

_PLAYGROUND_JS = """
<script>
function prettyJson(obj) {
  const raw = JSON.stringify(obj, null, 2)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return raw.replace(
    /("(?:\\\\.|[^"\\\\])*")(\\s*:)?|\\b(true|false)\\b|\\bnull\\b|-?\\d+(?:\\.\\d+)?(?:[eE][+-]?\\d+)?/g,
    (m, str, colon, bool) => {
      if (str) return colon ? '<span class="j-key">' + str + '</span>' + colon
                            : '<span class="j-str">' + str + '</span>';
      if (bool) return '<span class="j-bool">' + bool + '</span>';
      if (m === 'null') return '<span class="j-null">null</span>';
      return '<span class="j-num">' + m + '</span>';
    });
}

function setupCard(cardId, endpoint) {
  const card = document.getElementById(cardId);
  const drop = card.querySelector('.drop');
  const fileInput = card.querySelector('input[type=file]');
  const btn = card.querySelector('button.run');
  const status = card.querySelector('.status');
  const result = card.querySelector('pre.result');
  let file = null, timer = null;

  const setFile = f => {
    if (!f) return;
    file = f;
    drop.classList.add('hasfile');
    drop.innerHTML = '<span class="fname">📄 ' + f.name + '</span><small>' +
      (f.size / 1024).toFixed(0) + ' KB — 클릭해서 다른 파일 선택</small>';
  };
  drop.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', () => setFile(fileInput.files[0]));
  drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', e => {
    e.preventDefault(); drop.classList.remove('over');
    setFile(e.dataTransfer.files[0]);
  });

  btn.addEventListener('click', async () => {
    if (!file) { status.className = 'status err'; status.textContent = '파일을 먼저 선택하세요.'; return; }
    const fd = new FormData();
    fd.append('document', file);
    card.querySelectorAll('[data-field]').forEach(el => {
      if (el.type === 'checkbox') {
        if (el.checked) fd.append(el.dataset.field, el.value || 'true');
        return;
      }
      if (el.value !== '') fd.append(el.dataset.field, el.value);
    });
    btn.disabled = true; btn.classList.add('running');
    result.classList.remove('show');
    const t0 = Date.now();
    status.className = 'status';
    timer = setInterval(() => {
      status.textContent = '처리 중… ' + ((Date.now() - t0) / 1000).toFixed(1) + 's';
    }, 100);
    try {
      const r = await fetch(endpoint, { method: 'POST', body: fd });
      const data = await r.json().catch(() => ({ error: 'JSON 파싱 실패 (HTTP ' + r.status + ')' }));
      clearInterval(timer);
      const secs = ((Date.now() - t0) / 1000).toFixed(1);
      status.className = r.ok ? 'status ok' : 'status err';
      const dryTag = data && data.dryRun === true ? ' · 🧪 DRY RUN (DB에 안 씀)' : '';
      status.textContent = (r.ok ? '완료' : '실패 (HTTP ' + r.status + ')') + ' · ' + secs + 's' + dryTag;
      result.innerHTML = prettyJson(data);
      result.classList.add('show');
    } catch (e) {
      clearInterval(timer);
      status.className = 'status err';
      status.textContent = '요청 실패: ' + e.message;
    } finally {
      btn.disabled = false; btn.classList.remove('running');
    }
  });
}

setupCard('card-classify', '/test/classify');
setupCard('card-parse', '/test/parse');
setupCard('card-extract', '/test/extract');
setupCard('card-pipeline', '/test/pipeline');
</script>
"""


def _tester_card(card_id: str, title: str, desc: str, extra_controls: str = "",
                 button_label: str = "실행", wide: bool = False,
                 button_own_row: bool = False) -> str:
    btn = f'<button class="run"><span class="spinner"></span>{button_label}</button>'
    if button_own_row:
        controls = (f'<div class="controls">{extra_controls}</div>'
                    f'<div class="controls" style="justify-content: flex-end">{btn}</div>')
    else:
        controls = f'<div class="controls">{extra_controls} {btn}</div>'
    return f"""
    <div class="card{' wide' if wide else ''}" id="{card_id}">
      <div class="card-head"><span class="card-title">{title}</span>
        <span class="card-desc">{desc}</span></div>
      <div class="drop">문서를 끌어다 놓거나 클릭해서 선택<small>document 필드 · PDF / 이미지(JPG·PNG·HEIC) / DOCX / XLSX / HWP</small></div>
      <input type="file" hidden accept=".pdf,.jpg,.jpeg,.png,.bmp,.tif,.tiff,.heic,.heif,.docx,.pptx,.xlsx,.hwp,.hwpx">
      {controls}
      <div class="status"></div>
      <pre class="result"></pre>
    </div>"""


@app.get("/", response_class=HTMLResponse)
def index():
    doc_type_options = "".join(f'<option value="{t}">{t}</option>' for t in EXTRACTION_SCHEMAS)
    category_chips = "".join(f"<code>{c['name']}</code>" for c in CATEGORIES)

    body = f"""
    <h1>Playground</h1>
    <p class="subtitle">Upstage API를 단독으로 실험하거나, 전체 에이전트 파이프라인을 실행해봅니다.</p>

    <h2 class="section">Upstage 단독 실험 — DB에 기록하지 않음</h2>
    <div class="grid">
      {_tester_card('card-classify', 'Classify', '문서 유형 분류')}
      {_tester_card('card-parse', 'Parse', 'HTML/text 구조화')}
      {_tester_card('card-extract', 'Extract', '유형별 스키마로 필드 추출',
                    f'''<div class="field">
                          <span class="field-name">doc_type <span class="opt">— 추출 스키마 선택</span></span>
                          <select data-field="doc_type">{doc_type_options}</select>
                        </div>''', wide=True)}
    </div>
    <p class="hint">분류 카테고리:</p>
    <div class="chips">{category_chips}</div>

    <h2 class="section">전체 파이프라인 — 메인 API로 실행, DB에 기록됨</h2>
    <div class="grid">
      {_tester_card('card-pipeline', 'POST /api/documents/parse',
                    'ingest → classify → (parse ∥ extract) → orchestrate → act · 10~20초 소요',
                    f'''<div class="field">
                          <span class="field-name">targetType <span class="req">*</span></span>
                          <select data-field="targetType">
                            <option value="schedule">schedule — 바우처 1건, 일정 생성 (구현 완료)</option>
                            <option value="trip">trip — 여행 계획 문서 (플로우 미구현)</option>
                          </select>
                        </div>
                        <div class="field">
                          <span class="field-name">tripId <span class="opt">— 여행 uuid, 비우면 새 여행</span></span>
                          <input type="text" data-field="tripId" placeholder="예: ed61138f-ec43-…">
                        </div>
                        <div class="field">
                          <span class="field-name">text <span class="opt">— 사용자 프롬프트 (선택)</span></span>
                          <input type="text" data-field="text" placeholder="예: 오사카 여행 시작!">
                        </div>
                        <div class="field" style="flex:0 0 auto">
                          <span class="field-name">dryRun <span class="opt">— DB에 안 씀</span></span>
                          <label class="toggle"><input type="checkbox" data-field="dryRun" value="true"> 미리보기만</label>
                        </div>''',
                    button_label='파이프라인 실행', wide=True, button_own_row=True)}
    </div>
    {_PLAYGROUND_JS}
    """
    return _shell("Playground", body, active="home")


# ─────────────────── Upstage 단독 실험 엔드포인트 ───────────────────

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


@app.post("/test/pipeline")
async def test_pipeline(
    document: UploadFile = File(...),
    targetType: str = Form("schedule"),
    tripId: str = Form(""),
    text: str = Form(""),
    dryRun: str = Form(""),
):
    data, name, mime = await _read(document)
    form: dict = {"targetType": targetType}
    if tripId.strip():
        form["tripId"] = tripId.strip()
    if text.strip():
        form["text"] = text.strip()
    if dryRun.strip():
        form["dryRun"] = dryRun.strip()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0)) as client:
            r = await client.post(
                f"{MAIN_API_URL}/api/documents/parse",
                files={"document": (name, data, mime)},
                data=form,
            )
        try:
            body = r.json()
        except ValueError:
            body = {"error": f"main api가 JSON이 아닌 응답을 반환 (HTTP {r.status_code})",
                    "body": r.text[:600]}
        return JSONResponse(body, status_code=r.status_code)
    except httpx.ConnectError:
        return JSONResponse(
            {"error": f"메인 API({MAIN_API_URL})에 연결할 수 없습니다. "
                      "`uvicorn app.main:app --port 8000`으로 먼저 실행하세요."},
            status_code=502,
        )


# ─────────────────────────── DB 브라우저 ───────────────────────────

_DOC_TYPE_BADGE = {"hotel", "flight", "train", "attraction_ticket", "rental_car", "tour", "receipt"}


def _cell(value, column: str) -> str:
    if value is None or value == "":
        return '<span class="badge gray">—</span>' if column in ("doc_type", "type", "status") else ""
    v = str(value)
    if column in ("doc_type", "type"):
        cls = "" if v in _DOC_TYPE_BADGE else " gray"
        return f'<span class="badge{cls}">{html.escape(v)}</span>'
    if column == "status":
        return f'<span class="badge green">{html.escape(v)}</span>'
    if column == "has_conflict":
        return '<span class="badge red">충돌</span>' if value else '<span class="badge gray">정상</span>'
    return html.escape(v[:120])


def _table(rows: list[dict], columns: list[str], link: dict | None = None) -> str:
    if not rows:
        return '<div class="empty">아직 데이터가 없습니다</div>'
    head = "".join(f"<th>{c}</th>" for c in columns)
    body = ""
    for r in rows:
        tds = ""
        for c in columns:
            cell = _cell(r.get(c), c)
            if link and c == link["column"] and r.get(c):
                cell = f'<a href="{link["href"].format(**r)}">{cell}</a>'
            tds += f"<td>{cell}</td>"
        body += f"<tr>{tds}</tr>"
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


@app.get("/db/trips", response_class=HTMLResponse)
def db_trips():
    rows = get_db().table("trips").select("*").order("created_at", desc=True).execute().data or []
    t = _table(rows, ["id", "title", "start_date", "end_date", "status", "created_at"],
               link={"column": "id", "href": "/db/items?trip_id={id}"})
    body = f"""<h1>Trips</h1>
    <p class="subtitle">{len(rows)}개 · id를 클릭하면 해당 여행의 일정으로 이동합니다.</p>{t}"""
    return _shell("Trips", body, active="trips")


@app.get("/db/items", response_class=HTMLResponse)
def db_items(trip_id: str | None = None):
    q = get_db().table("items").select("*")
    if trip_id:
        q = q.eq("trip_id", trip_id)
    rows = q.order("starts_at", desc=False).execute().data or []
    scope = f"trip <code>{html.escape(trip_id)}</code>의 일정" if trip_id else "전체 일정"
    t = _table(rows, ["id", "type", "title", "location", "starts_at", "ends_at",
                      "price", "has_conflict", "conflict_msg", "booking_ref", "qr_code"])
    body = f"""<h1>Items</h1><p class="subtitle">{scope} · {len(rows)}개</p>{t}"""
    return _shell("Items", body, active="items")


@app.get("/db/documents", response_class=HTMLResponse)
def db_documents():
    rows = (
        get_db().table("documents")
        .select("id,item_id,file_name,mime_type,doc_type,created_at")
        .order("created_at", desc=True).execute().data or []
    )
    t = _table(rows, ["id", "file_name", "doc_type", "item_id", "created_at"],
               link={"column": "id", "href": "/db/documents/{id}"})
    body = f"""<h1>Documents</h1>
    <p class="subtitle">{len(rows)}개 · id를 클릭하면 파싱/추출 결과 상세를 볼 수 있습니다.</p>{t}"""
    return _shell("Documents", body, active="documents")


@app.get("/db/documents/{doc_id}", response_class=HTMLResponse)
def db_document_detail(doc_id: str):
    res = get_db().table("documents").select("*").eq("id", doc_id).execute()
    if not res.data:
        return _shell("Document", '<div class="empty">문서를 찾을 수 없습니다</div>', active="documents")
    d = res.data[0]
    meta = {k: d.get(k) for k in ("id", "file_name", "mime_type", "doc_type",
                                  "item_id", "storage_path", "created_at")}
    extracted = json.dumps(d.get("extracted"), ensure_ascii=False, indent=2)
    parsed_html = d.get("parsed_html") or "<p style='padding:1rem;color:#888'>파싱 결과 없음</p>"
    doc_type = d.get("doc_type") or "—"
    body = f"""
    <h1>{html.escape(d.get('file_name') or 'document')} <span class="badge">{html.escape(doc_type)}</span></h1>
    <p class="subtitle">문서 처리 결과 상세</p>
    <h2 class="section">메타데이터</h2>
    <pre class="plain">{html.escape(json.dumps(meta, ensure_ascii=False, indent=2))}</pre>
    <h2 class="section">Extract 결과</h2>
    <pre class="plain">{html.escape(extracted)}</pre>
    <h2 class="section">Parse 결과 — text</h2>
    <pre class="plain">{html.escape((d.get('parsed_text') or '없음')[:5000])}</pre>
    <h2 class="section">Parse 결과 — HTML 렌더링</h2>
    <iframe class="doc" srcdoc="{html.escape(parsed_html)}"></iframe>
    """
    return _shell(d.get("file_name") or "Document", body, active="documents")
