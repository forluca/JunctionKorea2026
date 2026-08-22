from typing import Any, TypedDict


class DocState(TypedDict, total=False):
    # ── 입력 ──
    file_bytes: bytes
    file_name: str
    mime_type: str
    target_type: str          # "trip" | "schedule"
    trip_id: str | None
    user_text: str | None     # 업로드 시 함께 온 사용자 프롬프트

    # ── ingest ──
    document_id: str
    storage_path: str

    # ── classify ──
    doc_type: str

    # ── parse (extract와 병렬) ──
    parsed_html: str
    parsed_text: str

    # ── extract (parse와 병렬) ──
    extracted: dict[str, Any]

    # ── orchestrate ──
    item_fields: dict[str, Any]      # 일정 아이템으로 정규화된 필드
    judgments: dict[str, Any]        # 예약확정/현장교환/취소기한 판단
    planned_actions: list[dict]      # [{"tool": ..., "args": {...}}]

    # ── act ──
    action_results: list[dict]
    item_id: str | None
