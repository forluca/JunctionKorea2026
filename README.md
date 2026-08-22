# JunctionKorea2026

여행 문서와 일정을 한 화면에서 관리하는 Docket 프로토타입입니다.

## 주요 기능 
gof
- 여행 목록 조회 및 활성 여행 표시
- 여행별 일정 타임라인 조회
- 일정 충돌 여부와 충돌 사유 표시
- 일정 상세 정보, QR 예약 번호, 결제 금액 표시
- 여행 추가와 일정 추가 흐름 분리
- PDF 및 이미지 파일 업로드
- 여행·일정·상세 정보 로딩 시 정적 스켈레톤 표시
- 일정 상세 패널 열림·닫힘 애니메이션
- 상세 페이지가 열린 일정 블록 하이라이트
- Google Maps 연동 영역
- 여행 목록, 일정 목록, 상세 정보, 업로드 파일 목록별 독립 스크롤

## 프로젝트 구조

```text
JunctionKorea2026/
├─ main.html                 # 애플리케이션 진입점
├─ css/
│  └─ selectTravel.css       # 패널 상태, 애니메이션, 스켈레톤, 지도 레이아웃
├─ js/
│  ├─ app.js                 # API 목업, 화면 렌더링, 업로드, 지도 초기화
│  └─ config.local.js        # 로컬 환경 설정
├─ .gitignore
└─ README.md
```

## API 구현 대상

현재 `js/app.js`에는 서버 연결 전 동작 확인을 위한 목업 함수가 있습니다. 아래 엔드포인트를 구현한 뒤 각 함수 내부의 목업 응답을 실제 `fetch` 요청으로 교체합니다.

### 1. 여행 목록 조회

- `GET /api/trips`
- 프론트 함수: `DocketAPI.fetchTrips()`
- 사용 위치: `UIRenderer.renderTripList()`
- 응답 필드: `id`, `title`, `startDate`, `endDate`, `conflictCount`, `status`

### 2. 여행 일정 조회

- `GET /api/trips/:tripId/items`
- 프론트 함수: `DocketAPI.fetchTripDetails(tripId)`
- 사용 위치: `UIRenderer.openTimeline(tripId, tripTitle)`
- 응답 필드: `id`, `type`, `time`, `title`, `desc`, `price`, `hasConflict`, `conflictMsg`

### 3. 일정 상세 조회

- `GET /api/items/:itemId`
- 프론트 함수: `DocketAPI.fetchItemDetail(itemId)`
- 사용 위치: `UIRenderer.openItem(itemId)`
- 응답 필드: `id`, `title`, `timeStr`, `price`, `hasConflict`, `conflictDetail`, `qrCodeStr`

### 4. 문서 업로드·분석 및 저장

- `POST /api/documents/parse`
- 파일 처리 함수: `UploadController.handleFiles(files)`
- 분석 시작 함수: `UploadController.startParsing()`
- 요청 형식: `multipart/form-data`
- 요청 필드: `document`, `targetType`, `tripId`, `text`
- `targetType`: `trip`이면 새 여행 생성, `schedule`이면 기존 여행에 일정 생성
- 응답 데이터: 문서 유형, 추출된 여행·일정 정보, 충돌 후보, 원본 문서 식별자
- 저장 결과: 분석 결과를 기준으로 여행 또는 일정 생성

여행 추가와 일정 추가는 별도 생성 함수나 별도 업로드 API를 사용하지 않습니다. 공통 함수 `UploadController.openUpload(uploadMode, returnState)`가 진입 모드만 저장하고, `UploadController.startParsing()`이 동일한 업로드·분석·저장 흐름을 처리합니다.
