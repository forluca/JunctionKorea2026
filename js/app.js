// Google Cloud Console에서 발급한 Maps JavaScript API 키를 입력합니다.
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
    markers: [], // 마커 객체 배열
    polylines: [], // 교통편 폴리라인 배열
    geocoder: null,

    getMapStyles: (theme = document.documentElement.dataset.theme) => theme === 'dark' ? DARK_MAP_STYLES : [],

    showFallback: (message) => {
        document.getElementById('map').classList.add('hidden');
        document.getElementById('map-fallback').classList.remove('hidden');
        document.getElementById('map-status').innerText = message;
    },

    init: () => {
        if (!GOOGLE_MAPS_API_KEY) {
            MapController.showFallback('Google Maps API 키를 js/app.js에 설정하세요.');
            return;
        }

        window.gm_authFailure = () => {
            MapController.showFallback('Google Maps 인증에 실패했습니다.');
        };

        window.initGoogleMap = () => {
            const map = new google.maps.Map(document.getElementById('map'), {
                center: { lat: 48.8566, lng: 2.3522 },
                zoom: 13,
                styles: MapController.getMapStyles(),
                mapTypeControl: false,
                streetViewControl: false,
                fullscreenControl: false
            });
            MapController.map = map;
            MapController.geocoder = new google.maps.Geocoder();

            window.addEventListener('resize', () => {
                google.maps.event.trigger(map, 'resize');
            });
            document.getElementById('map').classList.remove('hidden');
            document.getElementById('map-fallback').classList.add('hidden');
        };

        const script = document.createElement('script');
        script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(GOOGLE_MAPS_API_KEY)}&callback=initGoogleMap`;
        script.async = true;
        script.defer = true;
        document.head.appendChild(script);
    },

    // 타임라인 닫을 때 호출될 마커 및 폴리라인 완전 삭제 메서드
    clearMarkers: () => {
        MapController.markers.forEach(obj => {
            if (obj.marker) obj.marker.setMap(null);
        });
        MapController.markers = [];

        MapController.polylines.forEach(line => {
            if (line) line.setMap(null);
        });
        MapController.polylines = [];
    },

    renderMarkersForTrip: async (items) => {
        if (!MapController.map || !MapController.geocoder) return;
        MapController.clearMarkers();

        const bounds = new google.maps.LatLngBounds();
        let validLocationCount = 0;
                    

        for (const item of items) {
            console.log(`Rendering marker for item: ${item.title}, Location: ${item.location}`);
            const rawType = (item.type || '').toLowerCase();
            const locationText = item.location;
            if (!locationText || locationText === '...') continue;
            await new Promise((resolve) => {
                MapController.geocoder.geocode({ address: locationText }, async (results, status) => {
                    if (status === 'OK' && results[0]) {
                        const position = results[0].geometry.location;
                        
                        // 호텔일 경우 특수 아이콘 지정 (Google 기본 숙박/호텔 아이콘 또는 마커 색상 변경)
                        let iconConfig = undefined;
                        if (rawType === 'hotel') {
                            iconConfig = {
                                url: 'https://maps.google.com/mapfiles/ms/icons/lodging.png', // Google Maps 공식 제공 호텔/숙박 시설 마커 아이콘
                                scaledSize: new google.maps.Size(32, 32) // 아이콘 크기 조절
                            };
                        } else if (rawType === 'transportation') {
                            iconConfig = {
                                url: 'https://maps.google.com/mapfiles/ms/icons/bus.png',
                                scaledSize: new google.maps.Size(32, 32)
                            };
                        }

                        const marker = new google.maps.Marker({
                            map: MapController.map,
                            position: position,
                            title: item.title,
                            icon: iconConfig // 설정된 아이콘 객체 적용
                        });

                        const uniqueNodeId = rawType === 'hotel' ? `${item.id}-in` : `${item.id}-in`;
                        marker.addListener('click', () => {
                            MapController.map.panTo(position);
                            setTimeout(() => MapController.map.setZoom(13), 50);
                            if (typeof UIRenderer !== 'undefined' && UIRenderer.openItem) {
                                UIRenderer.openItem(item.id, uniqueNodeId);
                            }
                        });

                        MapController.markers.push({ itemId: item.id, marker: marker });
                        bounds.extend(position);
                        validLocationCount++;

                        // 교통편 경로 선(Polyline) 처리 유지
                        if (rawType === 'transportation' && item.title.includes('->')) {
                            const parts = item.title.split('->');
                            const arrivalDest = parts[1] ? parts[1].trim() : null;
                            if (arrivalDest) {
                                MapController.geocoder.geocode({ address: arrivalDest }, (arrResults, arrStatus) => {
                                    if (arrStatus === 'OK' && arrResults[0]) {
                                        const arrPosition = arrResults[0].geometry.location;
                                        const arrMarker = new google.maps.Marker({
                                            map: MapController.map,
                                            position: arrPosition,
                                            title: `${item.title} (도착)`
                                        });
                                        MapController.markers.push({ itemId: item.id, marker: arrMarker });
                                        bounds.extend(arrPosition);

                                        const flightPath = new google.maps.Polyline({
                                            path: [position, arrPosition],
                                            geodesic: true,
                                            strokeColor: '#3b82f6',
                                            strokeOpacity: 0.8,
                                            strokeWeight: 3
                                        });
                                        flightPath.setMap(MapController.map);
                                        MapController.polylines.push(flightPath);
                                    }
                                });
                            }
                        }
                    }
                    resolve();
                });
            });
        }

        if (validLocationCount > 0) {
            MapController.map.fitBounds(bounds, { top: 100, right: 100, bottom: 100, left: 100 });
            google.maps.event.addListenerOnce(MapController.map, 'bounds_changed', () => {
                if (MapController.map.getZoom() > 13) MapController.map.setZoom(13);
            });
        }
    },

    focusMarker: (itemId) => {
        if (!MapController.map) return;
        const targetMarkerObj = MapController.markers.find(m => m.itemId === itemId);
        if (targetMarkerObj && targetMarkerObj.marker) {
            const position = targetMarkerObj.marker.getPosition();
            if (position) {
                MapController.map.panTo(position);
                setTimeout(() => MapController.map.setZoom(13), 50);
            }
        }
    }
};

const UIRenderer = {
    selectedItemId: null,
    docsData: [], 

    formatCurrency: (amount, currency = 'KRW') => {
        if (amount === null || amount === undefined || isNaN(amount)) return '';
        
        let curr = (currency || 'KRW').toUpperCase();
        
        // 통화별 로케일 및 화폐 표기 설정
        let locale = 'ko-KR';
        if (curr === 'USD') locale = 'en-US';
        else if (curr === 'EUR') locale = 'de-DE';

        try {
            return new Intl.NumberFormat(locale, { 
                style: 'currency', 
                currency: curr 
            }).format(amount);
        } catch (e) {
            // 지원하지 않는 통화 코드일 경우 기본 원화 또는 원본 숫자 포맷 반환
            return new Intl.NumberFormat('ko-KR', { style: 'currency', currency: 'KRW' }).format(amount);
        }
    },

    formatDateTime: (timeStr) => {
        if (!timeStr) return '';
        const dateTimeMatch = timeStr.match(/^(\d{4})-(\d{2})-(\d{2})(?:T|\s)(\d{2}):(\d{2})/);
        if (dateTimeMatch) {
            return `${dateTimeMatch[1]}.${dateTimeMatch[2]}.${dateTimeMatch[3]} ${dateTimeMatch[4]}:${dateTimeMatch[5]}`;
        }
        const dateMatch = timeStr.match(/^(\d{4})-(\d{2})-(\d{2})/);
        if (dateMatch) {
            return `${dateMatch[1]}.${dateMatch[2]}.${dateMatch[3]}`;
        }
        return String(timeStr);
    },

    formatDateOnly: (timeStr) => {
        if (!timeStr) return '';
        const dateMatch = timeStr.match(/^(\d{4})-(\d{2})-(\d{2})/);
        if (dateMatch) {
            return `${dateMatch[1]}.${dateMatch[2]}.${dateMatch[3]}`;
        }
        return String(timeStr);
    },

    setAppClass: (stateClass) => { 
        document.getElementById('app-container').className = `h-screen w-screen overflow-hidden flex bg-[#f3f4f6] text-[#1e293b] antialiased ${stateClass}`; 
    },

    // 오류 수정: UIRenderer 내부로 LNB 제어 로직 통합
    setLNBActive: (activeMenu) => {
        const tripBtn = document.getElementById('lnb-trip-button');
        const docsBtn = document.getElementById('lnb-docs-button');

        const baseClasses = 'w-full py-4 flex flex-col items-center gap-1.5 transition border-l-4';
        const inactiveClasses = `${baseClasses} text-blue-200 hover:text-white hover:bg-blue-800/50 border-transparent cursor-pointer`;
        const activeClasses = `${baseClasses} bg-blue-800 text-white border-white cursor-default`;

        if (tripBtn) {
            tripBtn.setAttribute('class', activeMenu === 'trip' ? activeClasses : inactiveClasses);
        }
        if (docsBtn) {
            docsBtn.setAttribute('class', activeMenu === 'docs' ? activeClasses : inactiveClasses);
        }
    },

    renderTripListSkeleton: (container) => { 
        container.innerHTML = `<div class="list-skeleton-card"><div class="list-skeleton-title"></div><div class="list-skeleton-line"></div></div><div class="list-skeleton-card"><div class="list-skeleton-title"></div><div class="list-skeleton-line"></div></div>`; 
    },
    
    renderTimelineSkeleton: (container) => { 
        container.innerHTML = `<div class="timeline-skeleton-line"></div><div class="timeline-skeleton-item"><div class="timeline-skeleton-dot"></div><div class="timeline-skeleton-card"><div class="timeline-skeleton-title"></div><div class="timeline-skeleton-text"></div></div></div>`; 
    },

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
            
            const displayStart = UIRenderer.formatDateOnly(trip.start_date);
            const displayEnd = UIRenderer.formatDateOnly(trip.end_date);

            tripCard.innerHTML = `
                <h3 class="text-lg font-bold ${titleColor} mb-1">${trip.title}</h3>
                <p class="text-xs text-gray-500"><i class="fa-regular fa-calendar mr-1"></i> ${displayStart} - ${displayEnd}</p>
                ${conflictBadge}
            `;
            tripCard.addEventListener('click', () => UIRenderer.openTimeline(trip.id, trip.title));
            container.appendChild(tripCard);
        });
    },

    openTimeline: async (tripId, tripTitle) => {
        UIRenderer.setAppClass('state-trip');
        document.getElementById('timeline-header-info').innerHTML = `<h2 class="text-lg font-bold text-gray-900 truncate-text">${tripTitle}</h2><p class="text-xs text-gray-500">상세 타임라인</p>`;
        const container = document.getElementById('timeline-container');
        UIRenderer.renderTimelineSkeleton(container);

        const rawItems = await DocketAPI.fetchTripDetails(tripId);
        // ★ 핵심 추가: 타임라인 데이터가 로드된 직후 지도에 마커(핀)를 그리는 함수 호출
        if (typeof MapController !== 'undefined' && MapController.renderMarkersForTrip) {
            await MapController.renderMarkersForTrip(rawItems);
        }

        const timelineItems = [];

        rawItems.forEach(item => {
            const rawType = item.type || '';
            const startTimeFormatted = UIRenderer.formatDateTime(item.starts_at);
            const endTimeFormatted = UIRenderer.formatDateTime(item.ends_at);

            if (rawType.toLowerCase() === 'hotel') {
                timelineItems.push({
                    ...item, sortTime: item.starts_at, displayTime: startTimeFormatted || '체크인 시간 미상', displayTitle: item.title, displayDesc: '체크인', isCheckoutNode: false
                });
                if (item.ends_at) {
                    timelineItems.push({
                        ...item, sortTime: item.ends_at, displayTime: endTimeFormatted, displayTitle: item.title, displayDesc: '체크아웃', isCheckoutNode: true, has_conflict: false
                    });
                }
            } else {
                timelineItems.push({
                    ...item, sortTime: item.starts_at, displayTime: startTimeFormatted, displayTitle: item.title, displayDesc: item.location || '', isCheckoutNode: false
                });
            }
        });

        timelineItems.sort((a, b) => {
            if (!a.sortTime) return 1;
            if (!b.sortTime) return -1;
            const timeA = new Date(a.sortTime).getTime();
            const timeB = new Date(b.sortTime).getTime();
            if (!isNaN(timeA) && !isNaN(timeB)) return timeA - timeB;
            return String(a.sortTime).localeCompare(String(b.sortTime));
        });

        // 타임라인 컨테이너의 배경 세로선이 전체 높이를 커버할 수 있도록 relative 및 선 스타일 보강
        container.innerHTML = '<div class="absolute left-[28px] top-6 bottom-6 w-[2px] bg-gray-200 z-0 h-full"></div>';
        
        timelineItems.forEach(item => {
            const dotClass = item.has_conflict ? 'bg-red-500 animate-pulse' : 'bg-blue-500';
            const borderClass = item.has_conflict ? 'border-red-300 group-hover:border-red-500' : 'border-gray-200 group-hover:border-blue-400';
            const textClass = item.has_conflict ? 'text-red-600' : 'text-blue-600';
            const conflictDiv = item.has_conflict ? `<div class="mt-2 text-[10px] text-red-600 bg-red-50 p-1.5 rounded truncate-text"><i class="fa-solid fa-triangle-exclamation"></i> ${item.conflict_msg}</div>` : '';
            
            const timelineItem = document.createElement('div');
            // 각 아이템마다 원(Dot)과 카드 영역이 플렉스 구조로 반복 생성되도록 설정
            timelineItem.className = 'relative flex items-start gap-3 cursor-pointer group z-10 mb-6';
            const uniqueNodeId = item.isCheckoutNode ? `${item.id}-out` : `${item.id}-in`;
            timelineItem.dataset.nodeId = uniqueNodeId;
            timelineItem.dataset.itemId = item.id;
            
            if (UIRenderer.selectedItemId === uniqueNodeId) timelineItem.classList.add('timeline-item-selected');

            timelineItem.innerHTML = `
                <div class="w-4 h-4 ${dotClass} rounded-full border-4 border-gray-50 z-10 flex-shrink-0 mt-1"></div>
                <div class="flex-1 min-w-0 bg-white border ${borderClass} p-3 rounded-xl shadow-sm transition">
                    <span class="${textClass} text-xs" style="font-weight: 700;">${item.displayTime}</span>
                    <h4 class="text-sm font-bold text-gray-900 mt-1 timeline-title">${item.displayTitle}</h4>
                    <p class="text-[11px] text-gray-500 mt-0.5 timeline-desc">${item.displayDesc}</p>
                    ${conflictDiv}
                </div>
            `;
            timelineItem.addEventListener('click', () => UIRenderer.openItem(item.id, uniqueNodeId));
            container.appendChild(timelineItem);
        });
    },

    closeTimeline: () => {
        const appContainer = document.getElementById('app-container');
        if (!appContainer) return;

        // 상세 아이템 패널이 열려 있는 경우 상세 창을 닫고 타임라인 상태로 복귀
        if (appContainer.classList.contains('state-item')) {
            const itemPanel = document.getElementById('item-panel');
            if (itemPanel) {
                itemPanel.classList.add('is-loading');
            }
            UIRenderer.selectedItemId = null;
            UIRenderer.setAppClass('state-trip');
            return;
        }

        // 그 외의 경우 마커를 지우고 전체 여행 목록 상태로 복귀
        if (typeof MapController !== 'undefined' && typeof MapController.clearMarkers === 'function') {
            MapController.clearMarkers();
        }
        UIRenderer.setAppClass('state-list');
    },

    openItem: async (itemId, nodeId = null) => {
        const targetNodeId = nodeId || `${itemId}-in`;
        if (UIRenderer.selectedItemId === targetNodeId && document.getElementById('app-container').classList.contains('state-item')) {
            UIRenderer.closeItem();
            return;
        }

        UIRenderer.selectedItemId = targetNodeId;
        document.querySelectorAll('.timeline-item-selected').forEach(item => item.classList.remove('timeline-item-selected'));
        document.querySelector(`[data-node-id="${targetNodeId}"]`)?.classList.add('timeline-item-selected');
        
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

        const rawType = data.type || '';
        const displayType = rawType ? rawType.toUpperCase() : '미지정';
        
        const startTimeFormatted = UIRenderer.formatDateTime(data.starts_at) || '일시 정보 없음';
        const endTimeFormatted = UIRenderer.formatDateTime(data.ends_at);

        let displayTime = startTimeFormatted;
        if (endTimeFormatted && startTimeFormatted !== '일시 정보 없음') {
            displayTime += ` ~ ${endTimeFormatted}`;
        }
        
        const displayLocation = data.location || '...';
        const displayBookingRef = data.booking_ref || '...';
        // openItem 내부의 가격 포맷 호출부 변경
        const displayPrice = data.price ? UIRenderer.formatCurrency(data.price, data.currency) : '...';
        const displayCancelDead = UIRenderer.formatDateTime(data.cancellation_deadline) || null;
        const conflictMessage = data.conflict_msg || '상세 내용 없음';

        let displayNotes = [];
        if (Array.isArray(data.notes) && data.notes.length > 0) {
            displayNotes = data.notes;
        } else if (typeof data.notes === 'string' && data.notes.trim() !== '') {
            displayNotes = [data.notes];
        }

        document.getElementById('item-header').innerHTML = `
            <div>
                <div class="text-xs text-blue-600 mb-1" style="font-weight: 700;">${displayType}</div>
                <h2 class="text-xl font-bold text-gray-900">${data.title}</h2>
                <p class="text-xs text-gray-500 mt-1">${displayTime}</p>
            </div>
            <button id="close-item-button" class="text-gray-400 hover:text-gray-700 transition"><i class="fa-solid fa-xmark text-xl"></i></button>
        `;
        document.getElementById('close-item-button').addEventListener('click', (event) => UIRenderer.closeItem(event));

        let validTickets = [];
        if (Array.isArray(data.tickets) && data.tickets.length > 0) {
            validTickets = data.tickets.filter(ticket => ticket.qr_code);
        } else if (data.qr_code) {
            validTickets = [{ id: `${data.id}-ticket`, qr_code: data.qr_code, label: '티켓 1' }];
        }

        let html = '';
        
        if (data.has_conflict) {
            html += `<div class="bg-red-50 border border-red-200 p-4 rounded-xl mb-4"><h4 class="text-sm text-red-800 mb-2" style="font-weight: 700;"><i class="fa-solid fa-triangle-exclamation"></i> 일정 충돌 발생</h4><p class="text-xs text-red-600 leading-relaxed">${conflictMessage}</p></div>`;
        }

        // 장소, 예약 번호, 무료 취소 기한에 이어 결제 금액과 원본 문서 보기까지 동일한 리스트 디자인으로 통합
        html += `
            <div class="bg-white border border-gray-200 p-4 rounded-xl shadow-sm mb-4">
                <dl class="space-y-3">
                    <div class="flex justify-between items-center">
                        <dt class="text-xs text-gray-500">장소</dt>
                        <dd class="text-xs font-medium text-gray-900">${displayLocation}</dd>
                    </div>
                    <div class="flex justify-between items-center border-t border-gray-50 pt-3">
                        <dt class="text-xs text-gray-500">예약 번호</dt>
                        <dd class="text-xs font-medium text-gray-900">${displayBookingRef}</dd>
                    </div>
                    ${displayCancelDead ? `
                    <div class="flex justify-between items-center border-t border-gray-50 pt-3">
                        <dt class="text-xs text-gray-500">무료 취소 기한</dt>
                        <dd class="text-xs font-medium text-red-600">${displayCancelDead}</dd>
                    </div>
                    ` : ''}
                    <div class="flex justify-between items-center border-t border-gray-50 pt-3">
                        <dt class="text-xs text-gray-500">결제 금액</dt>
                        <dd class="text-xs font-medium text-gray-900">${displayPrice}</dd>
                    </div>
                    <div class="flex justify-between items-center border-t border-gray-50 pt-3">
                        <dt class="text-xs text-gray-500">원본 문서</dt>
                        <dd>
                            <button id="view-document-button" class="text-blue-600 text-xs hover:underline font-bold" ${data.document_id ? '' : 'disabled'}>
                                문서 보기
                            </button>
                        </dd>
                    </div>
                </dl>
            </div>
        `;

        // 참고 사항(Notes) 영역 조건부 렌더링 유지
        if (displayNotes.length > 0) {
            html += `
                <div class="bg-white border border-gray-200 p-4 rounded-xl shadow-sm mb-4">
                    <h4 class="text-xs font-bold text-gray-900 mb-2">참고 사항</h4>
                    <ul class="text-xs text-gray-600 space-y-1.5 list-disc pl-4 marker:text-gray-300">
                        ${displayNotes.map(note => `<li>${note}</li>`).join('')}
                    </ul>
                </div>
            `;
        }
        
        content.innerHTML = html;

        if (validTickets.length > 0) {
            const ticketSlider = content.querySelector('.detail-ticket-slider');
            if (ticketSlider) TicketSlider.bind(ticketSlider, { tickets: validTickets });
        }
        
        const viewDocButton = document.getElementById('view-document-button');
        if (viewDocButton && data.document_id) {
            viewDocButton.addEventListener('click', async (event) => {
                event.preventDefault();
                const originalText = viewDocButton.innerText;
                viewDocButton.innerText = '문서 불러오는 중...';
                viewDocButton.classList.add('opacity-50', 'pointer-events-none');
                
                try {
                    const docDetail = await DocketAPI.fetchDocumentDetail(data.document_id);
                    if (docDetail && docDetail.original_url) {
                        window.open(docDetail.original_url, '_blank');
                    } else {
                        alert('원본 문서 링크를 찾을 수 없습니다.');
                    }
                } catch (error) {
                    alert('문서 정보를 불러오는 데 실패했습니다.');
                } finally {
                    viewDocButton.innerText = originalText;
                    viewDocButton.classList.remove('opacity-50', 'pointer-events-none');
                }
            });
        }
        if (typeof MapController !== 'undefined' && MapController.focusMarker) {
            MapController.focusMarker(itemId);
        }
        
        UIRenderer.setAppClass('state-item');
        window.setTimeout(() => itemPanel.classList.remove('is-loading'), 300);
    },

    closeItem: (event) => {
        if (event) event.stopPropagation();
        UIRenderer.selectedItemId = null;
        document.querySelectorAll('.timeline-item-selected').forEach(item => item.classList.remove('timeline-item-selected'));
        document.getElementById('item-panel').classList.add('is-loading');
        
        UIRenderer.setAppClass('state-trip');
    },

    openDocs: async () => {
        UIRenderer.setAppClass('state-docs');
        UIRenderer.setLNBActive('docs');
        
        const container = document.getElementById('docs-grid-container');
        container.innerHTML = '<div class="col-span-full text-center py-10 text-gray-400"><i class="fa-solid fa-circle-notch fa-spin text-2xl mb-2"></i><p>문서를 불러오는 중입니다...</p></div>';
        
        UIRenderer.docsData = await DocketAPI.fetchAllDocuments();
        UIRenderer.renderDocsList(UIRenderer.docsData);
    },

    renderDocsList: (docs) => {
        const container = document.getElementById('docs-grid-container');
        container.innerHTML = '';

        if (docs.length === 0) {
            container.innerHTML = '<div class="col-span-full text-center py-20 text-gray-400"><i class="fa-regular fa-folder-open text-4xl mb-3"></i><p>보관된 문서가 없습니다.</p></div>';
            return;
        }

        docs.forEach(doc => {
            const iconMap = { hotel: 'fa-bed', flight: 'fa-plane', museum: 'fa-building-columns', other: 'fa-file-lines' };
            const icon = iconMap[doc.doc_type] || 'fa-file-pdf';
            const dateStr = doc.created_at ? UIRenderer.formatDateOnly(doc.created_at) : '날짜 없음';

            const card = document.createElement('div');
            card.className = 'bg-white border border-gray-200 rounded-xl p-4 shadow-sm hover:shadow-md hover:border-blue-300 transition cursor-pointer flex flex-col group';
            card.innerHTML = `
                <div class="h-32 bg-gray-50 rounded-lg border border-gray-100 flex items-center justify-center mb-3 group-hover:bg-blue-50 transition">
                    <i class="fa-solid ${icon} text-4xl text-gray-300 group-hover:text-blue-400 transition"></i>
                </div>
                <h3 class="text-sm font-bold text-gray-900 truncate-text mb-1" title="${doc.file_name}">${doc.file_name}</h3>
                <p class="text-[11px] text-gray-500 truncate-text"><i class="fa-solid fa-map-pin mr-1"></i>${doc.trip_title}</p>
                <div class="mt-auto pt-3 flex justify-between items-center text-[10px] text-gray-400">
                    <span>${doc.item_title}</span>
                    <span>${dateStr}</span>
                </div>
            `;
            
            card.addEventListener('click', async () => {
                try {
                    const docDetail = await DocketAPI.fetchDocumentDetail(doc.document_id);
                    if (docDetail && docDetail.original_url) {
                        window.open(docDetail.original_url, '_blank');
                    } else {
                        alert('원본 문서 링크를 찾을 수 없습니다.');
                    }
                } catch (error) {
                    alert('문서 정보를 불러오는 데 실패했습니다.');
                }
            });
            container.appendChild(card);
        });
    },

    handleDocsSearch: (event) => {
        const query = event.target.value.toLowerCase().trim();
        if (!query) {
            UIRenderer.renderDocsList(UIRenderer.docsData);
            return;
        }
        
        const filteredDocs = UIRenderer.docsData.filter(doc => 
            (doc.file_name && doc.file_name.toLowerCase().includes(query)) ||
            (doc.trip_title && doc.trip_title.toLowerCase().includes(query)) ||
            (doc.item_title && doc.item_title.toLowerCase().includes(query))
        );
        UIRenderer.renderDocsList(filteredDocs);
    }
};

const UploadController = {
    stagedFiles: [],
    returnState: 'state-list',
    uploadMode: 'trip',

    openUpload: (uploadMode = 'trip', returnState = 'state-list') => {
        UploadController.uploadMode = uploadMode;
        UploadController.returnState = returnState;
        const isSchedule = uploadMode === 'schedule';
        document.getElementById('upload-panel-title').innerText = isSchedule ? '새 일정 추가' : '새 여행 추가';
        UIRenderer.setAppClass('state-upload');
    },

    closeUpload: () => {
        const returnState = UploadController.returnState;
        UploadController.clearFiles();
        UploadController.returnState = 'state-list';
        UploadController.uploadMode = 'trip';
        UIRenderer.setAppClass(returnState);
    },

    initDragAndDrop: () => {
        const dropZone = document.getElementById('drop-zone');
        const prevent = (event) => { event.preventDefault(); event.stopPropagation(); };
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => dropZone.addEventListener(eventName, prevent, false));
        ['dragenter', 'dragover'].forEach(eventName => dropZone.addEventListener(eventName, () => dropZone.classList.add('drag-active'), false));
        ['dragleave', 'drop'].forEach(eventName => dropZone.addEventListener(eventName, () => dropZone.classList.remove('drag-active'), false));
        dropZone.addEventListener('drop', event => UploadController.handleFiles(event.dataTransfer.files), false);
        dropZone.addEventListener('click', () => document.getElementById('file-input').click());
    },

    handleFiles: (files) => {
        UploadController.stagedFiles = [...UploadController.stagedFiles, ...Array.from(files)];
        UploadController.renderFileList();
    },

    removeFile: (index) => {
        UploadController.stagedFiles.splice(index, 1);
        UploadController.renderFileList();
    },

    clearFiles: () => {
        UploadController.stagedFiles = [];
        document.getElementById('file-input').value = '';
        UploadController.renderFileList();
        document.getElementById('upload-progress-container').classList.add('hidden');
    },

    // 텍스트 입력 체크를 제거하고 오직 파일 업로드 개수만 확인
    hasInput: () => {
        return UploadController.stagedFiles.length > 0;
    },

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

// 오류 수정: 중첩(Nested) 및 중복 선언된 이벤트 리스너 제거 후 단일화
document.addEventListener('DOMContentLoaded', () => {
    if (!sessionStorage.getItem('docket_user') || sessionStorage.getItem('docket_auth_version') !== '2') {
        sessionStorage.removeItem('docket_user');
        window.location.replace('login.html');
        return;
    }
    
    MapController.init();
    UploadController.initDragAndDrop();

    // 초기 해시 딥링킹 처리
    if (window.location.hash === '#docs') {
        UIRenderer.openDocs();
    } else {
        UIRenderer.renderTripList();
        UIRenderer.setLNBActive('trip');
    }

    // 기본 버튼 이벤트 바인딩
    document.getElementById('close-timeline-button').addEventListener('click', UIRenderer.closeTimeline);
    document.getElementById('close-upload-button').addEventListener('click', UploadController.closeUpload);
    document.getElementById('file-input').addEventListener('change', event => UploadController.handleFiles(event.target.files));
    document.getElementById('clear-files-button').addEventListener('click', UploadController.clearFiles);
    document.getElementById('btn-parse').addEventListener('click', UploadController.startParsing);
    document.getElementById('lnb-signout-button').addEventListener('click', GoogleAuth.signOut);
    
    // 모달 제어 바인딩
    document.getElementById('user-info-button')?.addEventListener('click', () => {
        let user;
        try {
            user = JSON.parse(sessionStorage.getItem('docket_user'));
        } catch (error) {
            user = null;
        }

        if (!user) return;

        const displayName = user.name || user.email || 'Google 사용자';
        const email = user.email || '이메일 정보 없음';
        const initial = displayName.charAt(0).toUpperCase();

        const modalContent = document.getElementById('user-modal-content');
        if (modalContent) {
            modalContent.innerHTML = `
                <!-- 닉네임/이메일 블록: 모든 면에 윤곽선(border) 삽입 -->
                <div class="user-profile-summary flex items-center gap-3.5 p-3.5 border border-gray-200 rounded-xl bg-white shadow-sm">
                    <div class="user-profile-avatar w-12 h-12 rounded-full bg-blue-600 text-white flex items-center justify-center font-bold text-lg flex-shrink-0">${initial}</div>
                    <div class="min-w-0">
                        <h2 class="text-sm font-bold text-gray-900 truncate">${displayName}</h2>
                        <p class="text-xs text-gray-500 truncate">${email}</p>
                    </div>
                </div>

                <!-- 화면 테마 항목 (하단 항목과 폰트 크기 및 색상 일치) -->
                <div class="theme-setting py-3 flex justify-between items-center text-xs">
                    <span class="font-large text-gray-500">화면 테마</span>
                    <div class="theme-options flex gap-1.5">
                        <button type="button" data-theme-choice="light" class="px-3 py-1 text-xs rounded border border-gray-300 hover:bg-gray-100"><i class="fa-solid fa-sun"></i> 라이트</button>
                        <button type="button" data-theme-choice="dark" class="px-3 py-1 text-xs rounded border border-gray-300 hover:bg-gray-100"><i class="fa-solid fa-moon"></i> 다크</button>
                    </div>
                </div>
                <dl class="user-detail-list pt-2 space-y-3 text-xs border-t border-transparent">
                    <div class="flex justify-between items-center"><dt class="text-gray-500 font-medium">로그인 방식</dt><dd class="font-bold text-gray-900">Google 계정</dd></div>
                    <div class="flex justify-between items-center pt-2 border-t border-transparent"><dt class="text-gray-500 font-medium">서비스 이용 상태</dt><dd class="font-bold text-gray-900">이용 중</dd></div>
                </dl>
                                    
            `;
            ThemeController.bind(modalContent);
            document.getElementById('user-info-modal').classList.remove('hidden');
        }
    });
    
    document.getElementById('close-user-modal-button').addEventListener('click', () => {
        document.getElementById('user-info-modal').classList.add('hidden');
    });

    // LNB 및 검색 이벤트 단일화 바인딩
    document.getElementById('lnb-docs-button')?.addEventListener('click', () => {
        window.location.hash = 'docs';
        UIRenderer.openDocs();
    });
    
    document.getElementById('docs-search-input')?.addEventListener('keyup', UIRenderer.handleDocsSearch);
    
    document.getElementById('lnb-trip-button')?.addEventListener('click', () => {
        window.location.hash = '';
        UIRenderer.setAppClass('state-list');
        UIRenderer.setLNBActive('trip');
    });

    // 하단 인라인 드롭존 이벤트 바인딩
    const inlineDropZone = document.getElementById('inline-drop-zone');
    const inlineFileInput = document.getElementById('inline-file-input');

    if (inlineDropZone && inlineFileInput) {
        const prevent = (e) => { e.preventDefault(); e.stopPropagation(); };
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => inlineDropZone.addEventListener(eventName, prevent, false));
        ['dragenter', 'dragover'].forEach(eventName => inlineDropZone.addEventListener(eventName, () => inlineDropZone.classList.add('border-blue-500', 'bg-blue-50/50'), false));
        ['dragleave', 'drop'].forEach(eventName => inlineDropZone.addEventListener(eventName, () => inlineDropZone.classList.remove('border-blue-500', 'bg-blue-50/50'), false));
        
        inlineDropZone.addEventListener('drop', (e) => {
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                UploadController.handleFiles(files);
                UploadController.startParsing(); // 드롭 즉시 분석 시작 연동
            }
        });
        
        inlineDropZone.addEventListener('click', () => inlineFileInput.click());
        inlineFileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                UploadController.handleFiles(e.target.files);
                UploadController.startParsing();
            }
        });
    }
});