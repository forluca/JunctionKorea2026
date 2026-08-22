# Docket Backend API 명세

프론트엔드 연동 기준 문서. 구현 위치: [backend/app/api/routes.py](../backend/app/api/routes.py)

- **Base URL**: `http://127.0.0.1:8000` (로컬 개발 기준)
  - 팀원 접속: 서버를 `--host 0.0.0.0`으로 실행하면 같은 와이파이에서 `http://<서버 맥의 LAN IP>:8000`으로 접속 가능. 외부 공개는 `cloudflared tunnel --url http://localhost:8000`으로 발급된 URL 사용.
- **CORS**: 전체 허용 (데모용)
- **헬스체크**: `GET /health` → `{"ok": true}`
- **백오피스**(실험/디버깅): `http://127.0.0.1:8001` — Upstage 단독 테스트, DB 브라우저
- **테스트 문서**: `backend/dataset/` 에 실제 여행 문서 PDF 샘플 (hotel / transportation / etc)

---

## 1. `POST /api/documents/parse` — 문서 업로드·분석 및 저장

문서 1개를 업로드하면 에이전트 파이프라인이 실행된다:
`저장(ingest) → 유형 분류(classify) → 구조화(parse) ∥ 필드 추출(extract) → 판단(orchestrate) → 액션 실행(act)`

### 요청 — `multipart/form-data`

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `document` | file | ✅ | PDF / 이미지(JPG·PNG·BMP·TIFF·**HEIC**) / DOCX / PPTX / XLSX / HWP·HWPX (그 외 415 에러, 50MB 이하) |
| `targetType` | string | | `schedule` — 바우처·티켓 1건(일정 1개 생성, **구현 완료**) / `trip` — 전체 여행 계획 문서(**플로우 미구현** — 현재는 파일 저장 + 빈 여행 생성까지만). 기본 `schedule` |
| `tripId` | string(uuid) | | `targetType=schedule`일 때 대상 여행. 비어 있으면 새 여행이 생성됨 |
| `text` | string | | 사용자 프롬프트(선택). orchestrator 판단에 반영됨 |
| `dryRun` | string | | `true`면 파이프라인은 전부 실행하되 **Storage/DB에 쓰지 않고** 미리보기만 반환 |

> **분기 방식**: 요청의 `targetType`으로 명시적으로 분기한다 (Classify로 판별하지 않음).
> `trip` 플로우는 자리만 잡아둔 상태 — 응답의 `actions`에 `{"tool": "trip_flow", "status": "not_implemented"}`가 담긴다.
> 구현되면 일정 여러 개가 응답의 `items` 배열로 반환될 예정.

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
  "notes": [
    "예약이 확정되었습니다",
    "8월 28일까지 무료 취소 가능합니다",
    "체크인 시 여권 지참 필요",
    "도시세(€6.00/인/박)는 호텔에서 별도 지불"
  ],
  "items": [],
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
- `docType`은 4종: `hotel` / `transportation`(항공·기차·버스·페리) / `tour`(투어·액티비티·관광지 입장권) / `other`(안전망) — 차근차근 확장 예정 (`targetType=trip`이면 classify를 건너뛰므로 `null`)
- `items` 배열은 trip 플로우용으로 예약된 필드 — 현재는 항상 빈 배열.
- `dryRun=true` 응답은 형태가 다름: `{"dryRun": true, "docType", "wouldCreate": {"trip", "item"}, "extracted", "notes", "conflicts", "actions"}` — `wouldCreate.item`이 실제 insert될 row 미리보기.
- `extracted`의 필드 구성은 docType마다 다름 ([backend/app/graph/schemas.py](../backend/app/graph/schemas.py) 참고).
- `notes`: 사용자가 알아둬야 할 사항의 **한국어 문장 배열** — 예약 확정 상태, 현장 교환 필요 여부, 취소기한, 잔글씨 주의사항이 전부 여기로 통합됨. `items.notes`(jsonb)에 저장되어 일정 상세 조회에서도 반환. UI 로직용 구조화 값은 별도 필드 사용: 취소기한 D-day → `item.cancellation_deadline`(DB), 충돌 배지 → `hasConflict`/`conflictMsg`.
- `targetType=trip`이면 여행 제목·기간이 문서에서 자동 생성됨. 응답의 `trip`으로 갱신된 값 확인.
- `actions`의 툴 상태: `register_calendar`는 Google Calendar 연동 완료 — 이벤트 등록 + **1시간 전 팝업 알림**까지 설정됨(리마인드 기능 통합). `record_expense`는 영수증 확장 시 구현 예정(`stub`).

### 에러

| 코드 | 원인 |
|---|---|
| `400` | 빈 파일 |
| `404` | 존재하지 않는 tripId |
| `409` | 중복 문서(같은 예약번호) — 위 "충돌/중복 정책" 참고. 시간 겹침은 409가 아니라 200+conflictMsg |
| `415` | 지원 형식(PDF/이미지/오피스/한글) 이외의 파일 |
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
- `status`: 조회 시점에 계산됨 — `endDate`가 오늘보다 이전이면 `"past"`, 여행 전/여행 중/종료일 당일이면 `"active"` (일정 없는 여행도 `active`). 2종뿐.
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
  "tripId": "b81c…",
  "documentId": "3f2a…",
  "type": "hotel",
  "title": "힐튼 오사카 체크인",
  "timeStr": "2026-09-01 15:00 ~ 2026-09-05 11:00",
  "startsAt": "2026-09-01T15:00:00+00:00",
  "endsAt": "2026-09-05T11:00:00+00:00",
  "location": "1-8-8 Umeda, Kita-ku, Osaka",
  "price": 720000,
  "currency": "KRW",
  "bookingRef": "HTL-2026-88431",
  "cancellationDeadline": "2026-08-28T23:59:00+00:00",
  "hasConflict": true,
  "conflictDetail": "시간이 겹치는 일정: 유니버설 스튜디오 입장",
  "qrCodeStr": "HTL-2026-88431",
  "notes": [
    "예약이 확정되었습니다",
    "8월 28일까지 무료 취소 가능합니다",
    "체크인 시 여권 지참 필요"
  ]
}
```

- `notes`: 알아둬야 할 사항 문장 배열 (`items.notes` jsonb에 저장) — 상세 화면의 주의사항 목록으로 그대로 렌더링.

- `timeStr` 형식: 같은 날이면 `YYYY-MM-DD HH:MM ~ HH:MM`, 다른 날이면 양쪽 다 전체 표기, 종료 없으면 시작만.
- `qrCodeStr`: 문서 내 QR/Data Matrix/Aztec/바코드를 **실제로 디코딩한 코드 값** (여러 개면 쉼표로 연결). 문서에 코드가 없으면 예약번호(booking_ref)로 fallback.
- `qrImages`: 코드의 **원본 크롭 이미지** 목록 — `[{"value": 코드값, "format": "DataMatrix", "url": 서명URL}]`. `url`은 24시간 유효한 Supabase Storage 서명 URL이라 `<img src>`로 바로 표시 가능 (만료되면 상세 조회를 다시 호출하면 재발급됨). 현장 스캐너 호환을 위해 재생성 코드가 아닌 **원본 이미지 그대로** 보여줄 것.
- 없는 id → `404`.

---

## 충돌/중복 정책

**① 중복(duplicate) — 같은 여행에 같은 예약번호가 이미 있으면 저장하지 않고(캘린더 등록도 중단) `409 Conflict`로 응답:**

```json
{
  "error": "rejected",
  "reason": "duplicate",
  "message": "문서가 중복되었습니다.",
  "conflicts": [ { "id": "…", "title": "기존 일정 제목" } ],
  "documentId": "…",
  "docType": "tour",
  "notes": ["…"]
}
```

프론트는 `message`를 그대로 토스트/알럿으로 띄우면 됨.

**② 시간 겹침(overlap) — 에러 없이 정상 저장(200)하되 충돌 표시만:**
- 일정은 저장되고 캘린더에도 등록됨
- `item.hasConflict: true` + `conflictMsg`/`conflictDetail`에 "시간이 겹치는 일정: <제목>" 기록
- 프론트는 타임라인에서 충돌 배지로 표시

**시간 겹침 판정 규칙:**
- 같은 여행 안에서 `starts_at < 상대.ends_at && ends_at > 상대.starts_at`이면 겹침.
- 종료 시각이 없는 일정은 시작 후 2시간으로 간주.
- 시작 시각이 없는 일정(영수증 등)은 충돌 검사에서 제외.

## DB 스키마

[backend/supabase_schema.sql](../backend/supabase_schema.sql) — `trips` / `items` / `documents` 3개 테이블 + 스토리지 버킷 `documents`.
