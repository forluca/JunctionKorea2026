from typing import Any, TypedDict


class DocState(TypedDict, total=False):
    # ── 입력 ──
    file_bytes: bytes
    file_name: str
    mime_type: str
    target_type: str          # "trip" | "schedule"
    trip_id: str | None
    user_text: str | None     # 업로드 시 함께 온 사용자 프롬프트
    trip_start_date: str | None  # trip 플로우: 여행 시작일 (Day N → 절대 날짜 계산 기준)
    dry_run: bool             # True면 Storage/DB에 쓰지 않고 미리보기만

    # ── ingest ──
    document_id: str
    storage_path: str

    # ── classify ──
    doc_type: str

    # ── parse (extract와 병렬) ──
    parsed_html: str
    parsed_text: str
    qr_codes: list[str]              # figure 크롭에서 디코딩된 QR/바코드 값들
    qr_images: list[dict]            # [{value, format, image_path}] — 원본 크롭 Storage 경로

    # ── extract (parse와 병렬) ──
    extracted: dict[str, Any]

    # ── orchestrate ──
    item_fields: dict[str, Any]      # 일정 아이템으로 정규화된 필드
    notes: list[str]                 # 사용자가 알아둬야 할 사항 문장 배열 (판단+주의사항 통합)
    planned_actions: list[dict]      # [{"tool": ..., "args": {...}}]

    # ── orchestrate (itinerary 분기) ──
    itinerary_items: list[dict]      # 정규화된 일정 목록 (여행 계획 문서일 때)

    # ── act ──
    action_results: list[dict]
    item_id: str | None
    item_ids: list[str]              # itinerary 분기에서 생성된 전체 item id
