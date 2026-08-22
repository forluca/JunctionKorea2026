"""Upstage API 클라이언트 — Classify / Parse / Extract / Solar LLM.

- Classify:  POST /v1/document-classification  (chat 형식, oneOf+const 카테고리 스키마)
- Parse:     POST /v1/document-digitization    (multipart, model=document-parse)
- Extract:   POST /v1/information-extraction   (chat 형식, json_schema 기반 추출)
- LLM:       POST /v1/chat/completions         (orchestrator 판단용)
"""

import base64
import json
from typing import Any

import httpx

from app import config

_HEADERS = {"Authorization": f"Bearer {config.UPSTAGE_API_KEY}"}
_TIMEOUT = httpx.Timeout(120.0)


def _data_url(file_bytes: bytes, mime_type: str) -> str:
    b64 = base64.b64encode(file_bytes).decode()
    return f"data:{mime_type};base64,{b64}"


def _doc_message(file_bytes: bytes, mime_type: str) -> list[dict]:
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": _data_url(file_bytes, mime_type)},
                }
            ],
        }
    ]


async def classify_document(
    file_bytes: bytes, mime_type: str, categories: list[dict[str, str]]
) -> str:
    """문서 유형 분류. categories: [{"name": ..., "description": ...}]"""
    schema = {
        "type": "string",
        "oneOf": [
            {"const": c["name"], "description": c["description"]} for c in categories
        ],
    }
    payload = {
        "model": "document-classify",
        "messages": _doc_message(file_bytes, mime_type),
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "document-classify", "schema": schema},
        },
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.post(
            f"{config.UPSTAGE_BASE_URL}/document-classification",
            headers=_HEADERS,
            json=payload,
        )
        r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip().strip('"')


async def parse_document(
    file_bytes: bytes, filename: str, mime_type: str
) -> dict[str, Any]:
    """문서를 HTML/text로 구조화. {"html": ..., "text": ..., "elements": [...]} 반환."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.post(
            f"{config.UPSTAGE_BASE_URL}/document-digitization",
            headers=_HEADERS,
            files={"document": (filename, file_bytes, mime_type)},
            data={"model": "document-parse", "output_formats": '["html", "text"]'},
        )
        r.raise_for_status()
    body = r.json()
    content = body.get("content", {})
    return {
        "html": content.get("html", ""),
        "text": content.get("text", ""),
        "elements": body.get("elements", []),
    }


async def extract_information(
    file_bytes: bytes, mime_type: str, schema_name: str, schema: dict
) -> dict[str, Any]:
    """스키마 기반 필드 추출. 스키마 1레벨 프로퍼티는 string/integer/number/array만 허용."""
    payload = {
        "model": "information-extract",
        "messages": _doc_message(file_bytes, mime_type),
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": schema},
        },
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.post(
            f"{config.UPSTAGE_BASE_URL}/information-extraction",
            headers=_HEADERS,
            json=payload,
        )
        r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    return json.loads(content)


async def solar_chat(
    messages: list[dict], json_schema: dict | None = None, model: str | None = None
) -> Any:
    """Solar LLM 호출. json_schema를 주면 파싱된 객체를, 없으면 텍스트를 반환."""
    payload: dict[str, Any] = {
        "model": model or config.LLM_MODEL,
        "messages": messages,
    }
    if json_schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "response", "schema": json_schema},
        }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.post(
            f"{config.UPSTAGE_BASE_URL}/chat/completions",
            headers=_HEADERS,
            json=payload,
        )
        r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    if json_schema is not None:
        return json.loads(content)
    return content
