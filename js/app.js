// Google Cloud Console에서 발급한 Maps JavaScript API 키를 입력합니다.
// 키가 비어 있으면 안내 화면을 유지해 로컬 파일에서도 페이지가 깨지지 않습니다.
const GOOGLE_MAPS_API_KEY = window.GOOGLE_MAPS_API_KEY || '';
const DARK_MAP_STYLES = [
    { elementType: 'geometry', stylers: [{ color: '#242f3e' }] },
    { elementType: 'labels.text.stroke', stylers: [{ color: '#242f3e' }] },
    { elementType: 'labels.text.fill', stylers: [{ color: '#746855' }] },
    { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#38414e' }] },
    { featureType: 'road', elementType: 'geometry.stroke', stylers: [{ color: '#212a37' }] },
    { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#17263c' }] },
    { featureType: 'poi', elementType: 'labels.text.fill', stylers: [{ color: '#d59563' }] }
];

const MapController = {
    map: null,

    getMapStyles: (theme = document.documentElement.dataset.theme) => theme === 'dark' ? DARK_MAP_STYLES : [],

    // 지도 로딩 실패 원인을 지도 영역 안에 표시합니다.
    showFallback: (message) => {
        document.getElementById('map').classList.add('hidden');
        document.getElementById('map-fallback').classList.remove('hidden');
        document.getElementById('map-status').innerText = message;
    },

    // Google Maps API를 동적으로 불러와 지도 영역을 초기화합니다.
    init: () => {
        if (!GOOGLE_MAPS_API_KEY) {
            MapController.showFallback('Google Maps API 키를 js/app.js에 설정하세요.');
            return;
        }

        // Google이 인증 실패 시 호출하는 전역 콜백입니다.
        window.gm_authFailure = () => {
            MapController.showFallback('Google Maps 인증에 실패했습니다. API 키, 결제 계정, 도메인 제한을 확인하세요.');
        };

        window.initGoogleMap = () => {
            const map = new google.maps.Map(document.getElementById('map'), {
                center: { lat: 48.8566, lng: 2.3522 },
                zoom: 12,
                styles: MapController.getMapStyles(),
                mapTypeControl: false,
                streetViewControl: false,
                fullscreenControl: false
            });
            MapController.map = map;

            new google.maps.Marker({
                map,
                position: { lat: 48.8566, lng: 2.3522 },
                title: '파리 여행지'
            });
            window.addEventListener('resize', () => {
                google.maps.event.trigger(map, 'resize');
            });
            document.getElementById('map').classList.remove('hidden');
            document.getElementById('map-fallback').classList.add('hidden');
        };

        window.addEventListener('docket-theme-change', event => {
            if (MapController.map) MapController.map.setOptions({ styles: MapController.getMapStyles(event.detail) });
        });

        const script = document.createElement('script');
        script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(GOOGLE_MAPS_API_KEY)}&callback=initGoogleMap`;
        script.async = true;
        script.defer = true;
        script.onerror = () => {
            MapController.showFallback('Google Maps를 불러오지 못했습니다. API 키와 Maps JavaScript API 사용 설정을 확인하세요.');
        };
        document.head.appendChild(script);
    }
};

const UIRenderer = {
    selectedItemId: null,

    // 금액을 한국 원화 형식으로 변환합니다.
    formatCurrency: (amount) => {
        if (!amount) return '';
        return new Intl.NumberFormat('ko-KR', { style: 'currency', currency: 'KRW' }).format(amount);
    },

    // 현재 화면 상태를 나타내는 클래스로 패널 구성을 전환합니다.
    setAppClass: (stateClass) => {
        document.getElementById('app-container').className = `h-screen w-screen overflow-hidden flex bg-[#f3f4f6] text-[#1e293b] antialiased ${stateClass}`;
    },

    // 여행 목록을 불러오는 동안 카드 형태의 정적 스켈레톤을 표시합니다.
    renderTripListSkeleton: (container) => {
        container.innerHTML = `
            <div class="list-skeleton-card"><div class="list-skeleton-title"></div><div class="list-skeleton-line"></div></div>
            <div class="list-skeleton-card"><div class="list-skeleton-title"></div><div class="list-skeleton-line"></div></div>
        `;
    },

    // 일정 목록을 불러오는 동안 타임라인 형태의 정적 스켈레톤을 표시합니다.
    renderTimelineSkeleton: (container) => {
        container.innerHTML = `
            <div class="timeline-skeleton-line"></div>
            <div class="timeline-skeleton-item"><div class="timeline-skeleton-dot"></div><div class="timeline-skeleton-card"><div class="timeline-skeleton-title"></div><div class="timeline-skeleton-text"></div></div></div>
            <div class="timeline-skeleton-item"><div class="timeline-skeleton-dot"></div><div class="timeline-skeleton-card"><div class="timeline-skeleton-title"></div><div class="timeline-skeleton-text"></div></div></div>
            <div class="timeline-skeleton-item"><div class="timeline-skeleton-dot"></div><div class="timeline-skeleton-card"><div class="timeline-skeleton-title"></div><div class="timeline-skeleton-text"></div></div></div>
        `;
    },

    // API에서 여행 목록을 받아 카드 형태로 렌더링합니다.
    renderTripList: async () => {
        const container = document.getElementById('trip-list-container');
        UIRenderer.renderTripListSkeleton(container);
        const trips = await DocketAPI.fetchTrips();
        container.innerHTML = '';

        trips.forEach(trip => {
            const isConflict = trip.conflictCount > 0;
            const conflictBadge = isConflict ? `<div class="text-xs text-red-600 bg-red-50 p-2 rounded mt-3" style="font-weight: 700;">충돌 ${trip.conflictCount}건 확인 필요</div>` : '';
            const cardStyle = trip.status === 'active' ? 'border-gray-200' : 'border-gray-200 opacity-70';
            const titleColor = trip.status === 'active' ? 'text-black' : 'text-gray-500';
            const tripCard = document.createElement('div');
            tripCard.className = `bg-white border-2 ${cardStyle} rounded-xl p-4 shadow-sm cursor-pointer hover:-translate-y-1 transition group`;
            tripCard.innerHTML = `
                <h3 class="text-lg font-bold ${titleColor} mb-1">${trip.title}</h3>
                <p class="text-xs text-gray-500"><i class="fa-regular fa-calendar mr-1"></i> ${trip.startDate} - ${trip.endDate}</p>
                ${conflictBadge}
            `;
            tripCard.addEventListener('click', () => UIRenderer.openTimeline(trip.id, trip.title));
            container.appendChild(tripCard);
        });
    },

    // 선택한 여행의 일정을 타임라인으로 표시합니다.
    openTimeline: async (tripId, tripTitle) => {
        UIRenderer.setAppClass('state-trip');
        document.getElementById('timeline-header-info').innerHTML = `<h2 class="text-lg font-bold text-gray-900 truncate-text">${tripTitle}</h2><p class="text-xs text-gray-500">상세 타임라인</p>`;
        const container = document.getElementById('timeline-container');
        UIRenderer.renderTimelineSkeleton(container);

        const items = await DocketAPI.fetchTripDetails(tripId);
        container.innerHTML = '<div class="absolute left-[28px] top-6 bottom-6 w-[2px] bg-gray-200 z-0"></div>';
        items.forEach(item => {
            const dotClass = item.hasConflict ? 'bg-red-500 animate-pulse' : 'bg-blue-500';
            const borderClass = item.hasConflict ? 'border-red-300 group-hover:border-red-500' : 'border-gray-200 group-hover:border-blue-400';
            const textClass = item.hasConflict ? 'text-red-600' : 'text-blue-600';
            const conflictDiv = item.hasConflict ? `<div class="mt-2 text-[10px] text-red-600 bg-red-50 p-1.5 rounded truncate-text"><i class="fa-solid fa-triangle-exclamation"></i> ${item.conflictMsg}</div>` : '';
            const timelineItem = document.createElement('div');
            timelineItem.className = 'relative flex items-center gap-3 cursor-pointer group z-10';
            timelineItem.dataset.itemId = item.id;
            if (UIRenderer.selectedItemId === item.id) timelineItem.classList.add('timeline-item-selected');
            timelineItem.innerHTML = `
                <div class="w-4 h-4 ${dotClass} rounded-full border-4 border-gray-50 z-10"></div>
                <div class="flex-1 bg-white border ${borderClass} p-3 rounded-xl shadow-sm transition">
                    <span class="${textClass} text-xs" style="font-weight: 700;">${item.time}</span>
                    <h4 class="text-sm font-bold text-gray-900 mt-1 truncate-text">${item.title}</h4>
                    <p class="text-[11px] text-gray-500 mt-0.5 truncate-text">${item.desc}</p>
                    ${conflictDiv}
                </div>
            `;
            timelineItem.addEventListener('click', () => UIRenderer.openItem(item.id));
            container.appendChild(timelineItem);
        });
    },

    // 상세 화면에서는 상세 패널만 닫고 일정 목록으로 돌아갑니다.
    closeTimeline: () => {
        const appContainer = document.getElementById('app-container');
        if (appContainer.classList.contains('state-item')) {
            document.getElementById('item-panel').classList.add('is-loading');
            UIRenderer.selectedItemId = null;
            UIRenderer.setAppClass('state-trip');
            return;
        }

        UIRenderer.setAppClass('state-list');
    },

    // 선택한 일정의 상세 정보를 표시합니다.
    openItem: async (itemId) => {
        if (UIRenderer.selectedItemId === itemId && document.getElementById('app-container').classList.contains('state-item')) {
            UIRenderer.closeItem();
            return;
        }

        UIRenderer.selectedItemId = itemId;
        document.querySelectorAll('.timeline-item-selected').forEach(item => item.classList.remove('timeline-item-selected'));
        document.querySelector(`[data-item-id="${itemId}"]`)?.classList.add('timeline-item-selected');
        const itemPanel = document.getElementById('item-panel');
        const content = document.getElementById('item-content');
        itemPanel.classList.add('is-loading');
        UIRenderer.setAppClass('state-trip');
        content.innerHTML = '';

        const data = await DocketAPI.fetchItemDetail(itemId);
        if (!data) {
            itemPanel.classList.remove('is-loading');
            return;
        }

        document.getElementById('item-header').innerHTML = `
            <div>
                ${data.hasConflict ? '<span class="bg-red-100 text-red-700 text-[10px] px-2 py-1 rounded mb-2 inline-block" style="font-weight: 700;">Action Required</span>' : ''}
                <h2 class="text-xl font-bold text-gray-900">${data.title}</h2><p class="text-xs text-gray-500 mt-1">${data.timeStr}</p>
            </div>
            <button id="close-item-button" class="text-gray-400 hover:text-gray-700 transition"><i class="fa-solid fa-xmark text-xl"></i></button>
        `;
        document.getElementById('close-item-button').addEventListener('click', (event) => UIRenderer.closeItem(event));

        let html = '';
        if (data.hasConflict) html += `<div class="bg-red-50 border border-red-200 p-4 rounded-xl"><h4 class="text-sm text-red-800 mb-2" style="font-weight: 700;"><i class="fa-solid fa-triangle-exclamation"></i> 일정 충돌 발생</h4><p class="text-xs text-red-600 leading-relaxed">${data.conflictDetail}</p></div>`;
        const tickets = data.tickets?.length ? data.tickets : [{ id: `${data.id}-ticket`, qrCodeStr: data.qrCodeStr, label: '티켓 1' }];
        html += `
            <div class="bg-white border border-gray-200 p-5 rounded-xl text-center shadow-sm">
                <p class="text-xs text-gray-500 mb-3">입장용 QR 코드 (현장 제시)</p>
                <div class="detail-ticket-slider" data-pass-id="${data.id}" data-ticket-index="0">
                    <button class="wallet-ticket-arrow wallet-ticket-prev" type="button" aria-label="이전 티켓"><i class="fa-solid fa-chevron-left"></i></button>
                    <div class="wallet-ticket-view"><div class="wallet-qr"><i class="fa-solid fa-qrcode"></i></div><strong class="wallet-ticket-code">${tickets[0].qrCodeStr}</strong><small class="wallet-ticket-label">${tickets[0].label || '티켓 1'}</small></div>
                    <button class="wallet-ticket-arrow wallet-ticket-next" type="button" aria-label="다음 티켓"><i class="fa-solid fa-chevron-right"></i></button>
                    <div class="wallet-ticket-dots">${tickets.map((ticket, index) => `<button type="button" class="wallet-ticket-dot${index === 0 ? ' is-active' : ''}" data-ticket-index="${index}" aria-label="${ticket.label || `티켓 ${index + 1}`} "></button>`).join('')}</div>
                </div>
                <div class="mt-4 pt-4 border-t border-gray-100 flex justify-between items-center">
                    <span class="text-xs text-gray-600">결제 금액: ${UIRenderer.formatCurrency(data.price)}</span>
                    <button class="text-blue-600 text-xs hover:underline" style="font-weight: 700;">원본 문서 보기</button>
                </div>
            </div>
        `;
        content.innerHTML = html;
        const ticketSlider = content.querySelector('.detail-ticket-slider');
        if (ticketSlider) TicketSlider.bind(ticketSlider, { tickets: tickets });
        UIRenderer.setAppClass('state-item');
        window.setTimeout(() => itemPanel.classList.remove('is-loading'), 300);
    },

    // 상세 패널을 닫고 타임라인으로 돌아갑니다.
    closeItem: (event) => {
        if (event) event.stopPropagation();
        UIRenderer.selectedItemId = null;
        document.querySelectorAll('.timeline-item-selected').forEach(item => item.classList.remove('timeline-item-selected'));
        document.getElementById('item-panel').classList.add('is-loading');
        UIRenderer.setAppClass('state-trip');
    }
};

const UploadController = {
    stagedFiles: [],
    returnState: 'state-list',
    uploadMode: 'trip',

    // 여행 추가와 일정 추가가 서로 다른 API로 연결될 수 있도록 모드를 저장합니다.
    openUpload: (uploadMode = 'trip', returnState = 'state-list') => {
        UploadController.uploadMode = uploadMode;
        UploadController.returnState = returnState;
        const isSchedule = uploadMode === 'schedule';
        document.getElementById('upload-panel-title').innerText = isSchedule ? '새 일정 추가' : '새 여행 추가';
        document.getElementById('trip-text-label').innerText = isSchedule ? '일정 내용' : '여행 일정 내용';
        document.getElementById('trip-text-input').placeholder = isSchedule
            ? '일정 이름, 시간, 장소, 예약 정보를 직접 입력하세요.'
            : '여행 이름, 일정, 예약 정보를 직접 입력하세요.';
        UIRenderer.setAppClass('state-upload');
    },

    // 업로드 상태를 초기화하고 진입했던 화면으로 돌아갑니다.
    closeUpload: () => {
        const returnState = UploadController.returnState;
        UploadController.clearFiles();
        UploadController.returnState = 'state-list';
        UploadController.uploadMode = 'trip';
        UIRenderer.setAppClass(returnState);
    },

    // 파일 드래그 앤 드롭에 필요한 브라우저 기본 동작을 연결합니다.
    initDragAndDrop: () => {
        const dropZone = document.getElementById('drop-zone');
        const prevent = (event) => { event.preventDefault(); event.stopPropagation(); };
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => dropZone.addEventListener(eventName, prevent, false));
        ['dragenter', 'dragover'].forEach(eventName => dropZone.addEventListener(eventName, () => dropZone.classList.add('drag-active'), false));
        ['dragleave', 'drop'].forEach(eventName => dropZone.addEventListener(eventName, () => dropZone.classList.remove('drag-active'), false));
        dropZone.addEventListener('drop', event => UploadController.handleFiles(event.dataTransfer.files), false);
        dropZone.addEventListener('click', () => document.getElementById('file-input').click());
    },

    // 선택되거나 드롭된 파일을 업로드 대기 목록에 추가합니다.
    handleFiles: (files) => {
        UploadController.stagedFiles = [...UploadController.stagedFiles, ...Array.from(files)];
        UploadController.renderFileList();
    },

    // 대기 목록에서 특정 파일을 제거합니다.
    removeFile: (index) => {
        UploadController.stagedFiles.splice(index, 1);
        UploadController.renderFileList();
    },

    // 대기 파일과 진행률을 모두 초기화합니다.
    clearFiles: () => {
        UploadController.stagedFiles = [];
        document.getElementById('file-input').value = '';
        document.getElementById('trip-text-input').value = '';
        UploadController.renderFileList();
        document.getElementById('upload-progress-container').classList.add('hidden');
    },

    // 파일 또는 직접 입력한 텍스트가 있는지 확인합니다.
    hasInput: () => {
        const textInput = document.getElementById('trip-text-input');
        return UploadController.stagedFiles.length > 0 || textInput.value.trim().length > 0;
    },

    // 현재 대기 중인 파일과 텍스트를 화면에 그리고 분석 버튼 상태를 갱신합니다.
    renderFileList: () => {
        const container = document.getElementById('file-list-container');
        const parseButton = document.getElementById('btn-parse');
        container.innerHTML = '';
        if (UploadController.hasInput()) {
            parseButton.disabled = false;
            parseButton.classList.remove('opacity-50', 'cursor-not-allowed');
            UploadController.stagedFiles.forEach((file, index) => {
                const icon = file.type.includes('pdf') ? 'fa-file-pdf text-red-500' : 'fa-image text-blue-500';
                const fileRow = document.createElement('div');
                fileRow.className = 'flex items-center justify-between bg-white border border-gray-200 p-3 rounded-lg shadow-sm';
                fileRow.innerHTML = `
                    <div class="flex items-center gap-3 overflow-hidden">
                        <i class="fa-solid ${icon} text-lg"></i>
                        <span class="text-sm text-gray-700 truncate-text w-48">${file.name}</span>
                    </div>
                    <button class="remove-file-button text-gray-400 hover:text-red-500 transition"><i class="fa-solid fa-xmark"></i></button>
                `;
                fileRow.querySelector('.remove-file-button').addEventListener('click', () => UploadController.removeFile(index));
                container.appendChild(fileRow);
            });
        } else {
            parseButton.disabled = true;
            parseButton.classList.add('opacity-50', 'cursor-not-allowed');
        }
    },

    // 실제 분석을 대신해 진행률을 시뮬레이션하고 완료 후 목록을 갱신합니다.
    startParsing: () => {
        if (!UploadController.hasInput()) return;
        document.getElementById('btn-parse').disabled = true;
        document.getElementById('upload-progress-container').classList.remove('hidden');
        const progressBar = document.getElementById('progress-bar');
        const progressText = document.getElementById('progress-text');
        let progress = 0;
        const interval = setInterval(() => {
            progress += Math.floor(Math.random() * 15) + 5;
            if (progress >= 100) {
                progress = 100;
                clearInterval(interval);
                setTimeout(() => {
                    UploadController.closeUpload();
                    UIRenderer.renderTripList();
                }, 500);
            }
            progressBar.style.width = `${progress}%`;
            progressText.innerText = `${progress}%`;
        }, 300);
    }
};

// DOM이 준비된 뒤 초기 데이터와 파일 업로드 기능을 연결합니다.
document.addEventListener('DOMContentLoaded', () => {
    if (!sessionStorage.getItem('docket_user') || sessionStorage.getItem('docket_auth_version') !== '2') {
        sessionStorage.removeItem('docket_user');
        window.location.replace('login.html');
        return;
    }
    MapController.init();
    UIRenderer.renderTripList();
    UploadController.initDragAndDrop();
    document.getElementById('add-trip-button').addEventListener('click', () => UploadController.openUpload('trip', 'state-list'));
    document.getElementById('add-schedule-button').addEventListener('click', () => UploadController.openUpload('schedule', 'state-trip'));
    document.getElementById('close-timeline-button').addEventListener('click', UIRenderer.closeTimeline);
    document.getElementById('close-upload-button').addEventListener('click', UploadController.closeUpload);
    document.getElementById('file-input').addEventListener('change', event => UploadController.handleFiles(event.target.files));
    document.getElementById('trip-text-input').addEventListener('input', UploadController.renderFileList);
    document.getElementById('clear-files-button').addEventListener('click', UploadController.clearFiles);
    document.getElementById('btn-parse').addEventListener('click', UploadController.startParsing);
    document.getElementById('lnb-signout-button').addEventListener('click', GoogleAuth.signOut);
    document.getElementById('user-info-button').addEventListener('click', () => {
        const user = GoogleAuth.getStoredUser();
        if (!user) return;
        const displayName = user.name || user.email || 'Google 사용자';
        const email = user.email || '이메일 정보 없음';
        document.getElementById('user-modal-content').innerHTML = `
            <div class="user-profile-summary">
                <div class="user-profile-avatar">${displayName.charAt(0).toUpperCase()}</div>
                <div><h2>${displayName}</h2><p>${email}</p></div>
            </div>
            <div class="theme-setting"><span>화면 테마</span><div class="theme-options"><button type="button" data-theme-choice="light"><i class="fa-solid fa-sun"></i> 라이트</button><button type="button" data-theme-choice="dark"><i class="fa-solid fa-moon"></i> 다크</button></div></div>
            <dl class="user-detail-list">
                <div><dt>로그인 방식</dt><dd>Google 계정</dd></div>
                <div><dt>서비스 이용 상태</dt><dd class="user-status">이용 중</dd></div>
            </dl>
        `;
        ThemeController.bind(document.getElementById('user-modal-content'));
        document.getElementById('user-info-modal').classList.remove('hidden');
    });
    document.getElementById('close-user-modal-button').addEventListener('click', () => {
        document.getElementById('user-info-modal').classList.add('hidden');
    });
});
