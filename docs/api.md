# Docket Backend API 명세

프론트엔드 연동 기준 문서. 구현 위치: [backend/app/api/routes.py](../backend/app/api/routes.py)

- **Base URL**: `http://127.0.0.1:8000` (로컬 개발 기준)
- **CORS**: 전체 허용 (데모용)
- **헬스체크**: `GET /health` → `{"ok": true}`
- **백오피스**(실험/디버깅): `http://127.0.0.1:8001` — Upstage 단독 테스트, DB 브라우저

---

## 1. `POST /api/documents/parse` — 문서 업로드·분석 및 저장

문서 1개를 업로드하면 에이전트 파이프라인이 실행된다:
`저장(ingest) → 유형 분류(classify) → 구조화(parse) ∥ 필드 추출(extract) → 판단(orchestrate) → 액션 실행(act)`

### 요청 — `multipart/form-data`

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `document` | file | ✅ | PDF / JPG / PNG (그 외 415 에러) |
| `targetType` | string | | `trip`(새 여행 생성) 또는 `schedule`(기존 여행에 일정 추가). 기본 `schedule` |
| `tripId` | string(uuid) | | `targetType=schedule`일 때 대상 여행. 비어 있으면 새 여행이 생성됨 |
| `text` | string | | 사용자 프롬프트(선택). orchestrator 판단에 반영됨 |

```bash
curl -X POST http://127.0.0.1:8000/api/documents/parse \
  -F "document=@hotel_voucher.pdf" \
  -F "targetType=trip" \
  -F "text=오사카 여행 시작!"
```

### 응답 — `200 OK`

```json
{
  "documentId": "3f2a…",
  "docType": "hotel",
  "trip": {
    "id": "b81c…",
    "title": "오사카 여행",
    "startDate": "2026-09-01",
    "endDate": "2026-09-05",
    "status": "active"
  },
  "item": {
    "id": "9d4e…",
    "type": "hotel",
    "title": "힐튼 오사카 체크인",
    "startsAt": "2026-09-01T15:00:00",
    "endsAt": "2026-09-05T11:00:00",
    "location": "1-8-8 Umeda, Kita-ku, Osaka",
    "price": 720000,
    "hasConflict": false,
    "conflictMsg": "",
    "qrCodeStr": "HTL-2026-88431"
  },
  "extracted": {
    "hotel_name": "Hilton Osaka",
    "check_in_date": "2026-09-01",
    "check_out_date": "2026-09-05",
    "guests": 2,
    "booking_reference": "HTL-2026-88431",
    "total_price": 720000,
    "currency": "KRW",
    "cancellation_deadline": "2026-08-28T23:59",
    "confirmation_status": "confirmed"
  },
  "judgments": {
    "confirmed": "yes",
    "onsite_exchange_required": "no",
    "cancellation_deadline_open": "yes",
    "warnings": ["8월 28일까지 무료 취소 가능", "체크인 시 여권 지참 필요"]
  },
  "warnings": ["8월 28일까지 무료 취소 가능", "체크인 시 여권 지참 필요"],
  "conflicts": [
    { "id": "겹치는 item id", "title": "겹치는 일정 제목" }
  ],
  "actions": [
    { "tool": "add_to_itinerary", "status": "done", "item_id": "9d4e…", "conflicts": [] },
    { "tool": "register_calendar", "status": "stub", "args": { "...": "..." } },
    { "tool": "set_reminder", "status": "stub", "args": { "...": "..." } },
    { "tool": "record_expense", "status": "stub", "args": { "...": "..." } }
  ]
}
```

### 프론트 참고사항

- **처리 시간 10~20초** (Upstage 호출 3회 + LLM 1회). 업로드 애니메이션이 이 구간을 커버할 것.
- `docType`은 8종: `hotel` `flight` `train` `attraction_ticket` `rental_car` `tour` `receipt` `other`
- `extracted`의 필드 구성은 docType마다 다름 ([backend/app/graph/schemas.py](../backend/app/graph/schemas.py) 참고).
- `judgments`의 값은 `"yes" | "no" | "unknown"` 3값 문자열.
- `targetType=trip`이면 여행 제목·기간이 문서에서 자동 생성됨. 응답의 `trip`으로 갱신된 값 확인.
- `actions`에서 `status: "stub"`은 아직 미구현 툴(캘린더/알림/비용) — 담당자 구현 후 `done`으로 바뀜.

### 에러

| 코드 | 원인 |
|---|---|
| `400` | 빈 파일 |
| `415` | PDF/JPG/PNG 이외의 형식 |
| `422` | 필수 필드 누락 (FastAPI 기본 검증) |
| `500` | Upstage/Supabase 호출 실패 등 (detail에 원인) |

---

## 2. `GET /api/trips` — 여행 목록 조회

### 응답 — `200 OK`

```json
[
  {
    "id": "b81c…",
    "title": "오사카 여행",
    "startDate": "2026-09-01",
    "endDate": "2026-09-05",
    "status": "active",
    "conflictCount": 2
  }
]
```

- `startDate`/`endDate`는 소속 일정들의 최소/최대 날짜로 자동 계산됨. 일정이 없으면 `null`.
- `conflictCount` = 해당 여행에서 `hasConflict=true`인 일정 수.
- 정렬: 생성일 내림차순.

---

## 3. `GET /api/trips/{tripId}/items` — 여행 일정 조회

### 응답 — `200 OK` (시작 시각 오름차순)

```json
[
  {
    "id": "9d4e…",
    "type": "hotel",
    "time": "15:00",
    "title": "힐튼 오사카 체크인",
    "desc": "1-8-8 Umeda, Kita-ku, Osaka",
    "price": 720000,
    "hasConflict": false,
    "conflictMsg": ""
  }
]
```

- `time`: 시작 시각 `HH:MM`. **시각이 없는 문서(영수증 등)는 빈 문자열 `""`** — 프론트에서 처리 필요.
- `desc`: 장소가 있으면 장소, 없으면 요약/주의사항.

---

## 4. `GET /api/items/{itemId}` — 일정 상세 조회

### 응답 — `200 OK`

```json
{
  "id": "9d4e…",
  "title": "힐튼 오사카 체크인",
  "timeStr": "2026-09-01 15:00 ~ 2026-09-05 11:00",
  "price": 720000,
  "hasConflict": true,
  "conflictDetail": "시간이 겹치는 일정: 유니버설 스튜디오 입장",
  "qrCodeStr": "HTL-2026-88431"
}
```

- `timeStr` 형식: 같은 날이면 `YYYY-MM-DD HH:MM ~ HH:MM`, 다른 날이면 양쪽 다 전체 표기, 종료 없으면 시작만.
- `qrCodeStr`: **현재는 예약번호(booking_ref)로 채워짐.** QR 이미지 디코딩(pyzbar)은 추후 추가 예정.
- 없는 id → `404`.

---

## 충돌 판정 규칙

- 같은 여행 안에서 시간 구간이 겹치면 충돌 (`starts_at < 상대.ends_at && ends_at > 상대.starts_at`).
- 종료 시각이 없는 일정은 시작 후 2시간으로 간주.
- 시작 시각이 없는 일정(영수증 등)은 충돌 검사에서 제외.

## DB 스키마

[backend/supabase_schema.sql](../backend/supabase_schema.sql) — `trips` / `items` / `documents` 3개 테이블 + 스토리지 버킷 `documents`.
