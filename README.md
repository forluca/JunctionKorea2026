# JunctionKorea2026

여행 문서와 일정을 한 화면에서 관리하는 Docket 프로토타입입니다.

## 주요 기능
- Google 계정 로그인 및 로그인하지 않은 사용자의 서비스 접근 차단
- 로그인 사용자별 여행 정보 조회 구조
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
- 로그인한 사용자의 여행별 QR 패스를 모아보는 통합 지갑
- 일정 하나에 여러 티켓이 있을 때 QR 코드 좌우 버튼·점·마우스 드래그·터치 스와이프 전환
- 사용자 정보 모달 및 별도 사용자 정보 페이지
- 라이트 모드와 다크 모드 선택 및 설정 유지
- 여행 목록, 일정 목록, 상세 정보, 업로드 파일 목록별 독립 스크롤

## 프로젝트 구조

```text
JunctionKorea2026/
├─ login.html                # Google 로그인 화면
├─ main.html                 # 여행 서비스 화면
├─ wallet.html               # 통합 지갑 화면
├─ user.html                 # 사용자 정보 화면
├─ assets/
│  └─ logo.png               # 선택 가능한 공통 PNG 로고
├─ css/
│  └─ selectTravel.css       # 패널 상태, 애니메이션, 스켈레톤, 지도 레이아웃
├─ js/
│  ├─ api.js                 # 공통 API 및 로컬 목업 데이터
│  ├─ app.js                 # 여행 화면 렌더링, 업로드, 지도 초기화
│  ├─ google-auth.js         # Google Identity Services 로그인
│  ├─ ticket-slider.js       # 지갑·일정 상세 공통 티켓 슬라이더
│  ├─ theme.js               # 라이트·다크 모드 관리
│  ├─ user-page.js            # 사용자 정보 화면
│  ├─ wallet.js              # 통합 지갑 화면 및 패스 렌더링
│  └─ config.local.js        # 로컬 키와 API 설정
├─ .gitignore
└─ README.md
```

## API 구현 대상

공통 모듈 `js/api.js`가 여행 화면과 통합 지갑에서 함께 사용됩니다. `js/config.local.js`의 `USE_MOCK_API` 값으로 로컬 목업과 백엔드 호출을 전환합니다.

```js
window.USE_MOCK_API = true;
window.API_BASE_URL = '';
```

백엔드 연결 시 다음처럼 설정합니다.

```js
window.USE_MOCK_API = false;
window.API_BASE_URL = 'https://your-api-domain.com';
```

### 1. 여행 목록 조회

- `GET /api/trips`
- 프론트 함수: `DocketAPI.fetchTrips()`
- 사용 위치: `UIRenderer.renderTripList()`, `WalletController.load()`
- 요청 예시: `GET /api/trips?userId={googleSub}`
- 응답 필드: `id`, `userId`, `title`, `startDate`, `endDate`, `conflictCount`, `status`

### 2. 여행 일정 조회

- `GET /api/trips/:tripId/items`
- 프론트 함수: `DocketAPI.fetchTripDetails(tripId)`
- 사용 위치: `UIRenderer.openTimeline(tripId, tripTitle)`
- 응답 필드: `id`, `tripId`, `type`, `time`, `title`, `desc`, `price`, `hasConflict`, `conflictMsg`, `qrCodeStr`, `tickets`, `location`
- `qrCodeStr` 또는 `tickets[].qrCodeStr`가 있으면 통합 지갑에 예약 패스로 표시합니다.
- 여러 티켓은 `tickets: [{ id, qrCodeStr, label }]` 형태로 전달하며 지갑에서 좌우 슬라이드로 전환합니다.

### 3. 일정 상세 조회

- `GET /api/items/:itemId`
- 프론트 함수: `DocketAPI.fetchItemDetail(itemId)`
- 사용 위치: `UIRenderer.openItem(itemId)`
- 응답 필드: `id`, `tripId`, `title`, `timeStr`, `price`, `hasConflict`, `conflictDetail`, `qrCodeStr`, `tickets`
- 여러 티켓은 `tickets: [{ id, qrCodeStr, label }]` 형태로 전달합니다.
- 일정 상세 페이지와 통합 지갑은 동일한 `tickets` 배열을 사용합니다.

### 4. 통합 지갑

- 별도 지갑 API를 만들지 않고 기존 `GET /api/trips`와 `GET /api/trips/:tripId/items`를 재사용합니다.
- `tripId`가 현재 여행 ID와 일치하는 일정만 해당 여행 블록에 표시합니다.
- `qrCodeStr` 또는 `tickets[].qrCodeStr`가 있는 일정만 예약 패스로 표시합니다.
- 패스의 QR 코드는 `js/ticket-slider.js`를 통해 버튼, 점, 마우스 드래그, 터치 스와이프로 전환합니다.

### 5. 문서 업로드·분석 및 저장

- `POST /api/documents/parse`
- 파일 처리 함수: `UploadController.handleFiles(files)`
- 분석 시작 함수: `UploadController.startParsing()`
- 요청 형식: `multipart/form-data`
- 요청 필드: `document`, `targetType`, `tripId`, `text`
- `targetType`: `trip`이면 새 여행 생성, `schedule`이면 기존 여행에 일정 생성
- 응답 데이터: 문서 유형, 추출된 여행·일정 정보, 충돌 후보, 원본 문서 식별자
- 저장 결과: 분석 결과를 기준으로 여행 또는 일정 생성

여행 추가와 일정 추가는 별도 생성 함수나 별도 업로드 API를 사용하지 않습니다. 공통 함수 `UploadController.openUpload(uploadMode, returnState)`가 진입 모드만 저장하고, `UploadController.startParsing()`이 동일한 업로드·분석·저장 흐름을 처리합니다.

## 인증 및 화면 설정

- Google Client ID는 `js/config.local.js`의 `GOOGLE_CLIENT_ID`에 입력합니다.
- Google Client Secret은 브라우저 파일에 입력하지 않습니다.
- 로그인 성공 시 Google subject ID를 포함한 사용자 정보가 `sessionStorage`에 저장됩니다.
- 사용자 정보와 테마 설정은 각각 로그인 세션과 브라우저 `localStorage`를 사용합니다.
- `assets/logo.png`를 추가하면 로그인, 여행, 지갑 화면의 텍스트 로고가 공통 PNG 로고로 교체됩니다.
