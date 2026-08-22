"""Upstage Studio Agent 클라이언트 (v2 API).

schedule 플로우의 classify → parse → extract → orchestrate를 Studio에 구성된
에이전트 잡 하나로 대체한다. include=["all"]로 중간 스텝 출력까지 수확:
  step_1_parse    → parsed_html/parsed_text (문서 뷰어용)
  step_2_classify → doc_type
  *Extract*       → extracted (DB 저장용 구조화 필드)
  마지막 Instruct  → item/notes/actions (강화 파서로 정규화)

주의: 마지막 스텝 출력은 ```json 펜스 + 【†N】 인용 마커가 붙고 실행마다
키가 흔들릴 수 있어(type/tool, normalized_item/item) 방어적으로 파싱한다.
"""

import asyncio
import json
import re
from typing import Any

import httpx

from app import config

_TIMEOUT = httpx.Timeout(180.0)
_POLL_INTERVAL = 2.0
_MAX_WAIT = 300.0  # 여행 계획서(일정 28개+)는 잡이 2~4분까지 걸릴 수 있음


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.STUDIO_API_KEY}"}


def clean_json_text(text: str | None) -> dict | None:
    """코드펜스/인용마커/이중 문자열 인코딩을 걷어내고 JSON 객체를 파싱한다."""
    if not text:
        return None
    t = re.sub(r"【†\d+】", "", text).strip()
    if t.startswith('"'):
        # 전체가 JSON 문자열로 한 번 더 감싸진 경우
        try:
            t = json.loads(t)
        except Exception:
            t = t.strip('"')
    if not isinstance(t, str):
        return t if isinstance(t, dict) else None
    m = re.search(r"\{.*\}", t, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


_EXT_BY_MIME = {
    "application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png",
    "image/bmp": ".bmp", "image/tiff": ".tiff", "image/heic": ".heic",
}


def _safe_upload_name(filename: str, mime_type: str) -> str:
    """Studio 업로드는 파일명 확장자를 검사하므로 ASCII 안전한 이름으로 정규화."""
    ext = ""
    if "." in (filename or ""):
        cand = "." + filename.rsplit(".", 1)[-1].lower()
        if re.fullmatch(r"\.[a-z0-9]{2,5}", cand):
            ext = cand
    if not ext:
        ext = _EXT_BY_MIME.get(mime_type, ".pdf")
    return f"document{ext}"


async def run_document_agent(file_bytes: bytes, filename: str, mime_type: str) -> dict[str, Any]:
    """파일 업로드 → 잡 생성 → 폴링 → 스텝별 결과 수확."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        up = (await c.post(
            f"{config.STUDIO_BASE_URL}/files", headers=_headers(),
            files={"file": (_safe_upload_name(filename, mime_type), file_bytes, mime_type)},
            data={"purpose": "user_data"},
        )).json()
        file_id = up.get("id")
        if not file_id:
            raise RuntimeError(f"Studio 파일 업로드 실패: {json.dumps(up)[:300]}")

        payload = {
            "model": config.STUDIO_AGENT_ID,
            "include": ["all"],
            "input": [{"role": "user",
                       "content": [{"type": "input_file", "file_id": file_id}]}],
        }
        # CONFIG_ID가 숫자일 때만 버전 고정 — 비었거나 'latest'면 항상 최신 사용
        if config.STUDIO_CONFIG_ID.isdigit():
            payload["config_id"] = config.STUDIO_CONFIG_ID
        job = (await c.post(
            f"{config.STUDIO_BASE_URL}/responses", headers=_headers(), json=payload,
        )).json()
        job_id = job.get("id")
        if not job_id:
            raise RuntimeError(f"Studio 잡 생성 실패: {json.dumps(job)[:300]}")

        waited = 0.0
        while job.get("status") in ("queued", "in_progress"):
            await asyncio.sleep(_POLL_INTERVAL)
            waited += _POLL_INTERVAL
            if waited > _MAX_WAIT:
                raise RuntimeError(f"Studio 잡 시간 초과({_MAX_WAIT:.0f}s): {job_id}")
            job = (await c.get(
                f"{config.STUDIO_BASE_URL}/responses/{job_id}?include[]=all",
                headers=_headers(),
            )).json()

    if job.get("status") != "completed":
        raise RuntimeError(f"Studio 잡 실패: {json.dumps(job, ensure_ascii=False)[:400]}")

    result: dict[str, Any] = {"doc_type": None, "parsed_html": "", "parsed_text": "",
                              "extracted": {}, "final": {}}
    for out in job.get("output") or []:
        step = (out.get("model") or "").lower()
        text = ""
        for ct in out.get("content") or []:
            if ct.get("type") == "output_text":
                text = ct.get("text") or ""
        if "parse" in step:
            try:
                parsed = json.loads(text)
                content = parsed.get("content", {}) or {}
                result["parsed_html"] = content.get("html", "") or ""
                result["parsed_text"] = (content.get("text", "")
                                         or re.sub(r"<[^>]+>", " ", result["parsed_html"]))
            except Exception:
                pass
        elif "classify" in step:
            result["doc_type"] = text.strip().strip('"')
        elif "extract" in step:
            result["extracted"] = clean_json_text(text) or {}
        else:  # Instruct / Orchestrator / 기타 최종 스텝
            data = clean_json_text(text)
            if data:
                result["final"] = data
    return result
