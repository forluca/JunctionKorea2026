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
    infoWindow: null, // 싱글턴 InfoWindow (한 번에 하나만 열림)

    // 구글맵 기본 POI(상점·명소)와 대중교통 아이콘 숨김 — 우리 일정 핀만 보이게
    POI_HIDE_STYLES: [
        { featureType: 'poi', elementType: 'labels', stylers: [{ visibility: 'off' }] },
        { featureType: 'transit', elementType: 'labels.icon', stylers: [{ visibility: 'off' }] },
    ],

    getMapStyles: (theme = document.documentElement.dataset.theme) =>
        [...MapController.POI_HIDE_STYLES, ...(theme === 'dark' ? DARK_MAP_STYLES : [])],

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
            // 첫 진입 시 사용자 현재 위치로 이동
            MapController.goToUserLocation();
        };

        const script = document.createElement('script');
        script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(GOOGLE_MAPS_API_KEY)}&callback=initGoogleMap`;
        script.async = true;
        script.defer = true;
        document.head.appendChild(script);
    },

    // 문서 썸네일 URL (백엔드가 PDF 첫 페이지를 PNG로 렌더링)
    getThumbUrl: (item) => {
        if (!item?.document_id || typeof API_BASE_URL === 'undefined') return null;
        return `${API_BASE_URL}/api/documents/${item.document_id}/thumbnail`;
    },

    // 핀 위에 항상 떠 있는 문서 썸네일 말풍선 (애플 사진 지도 스타일)
    createDocThumbOverlay: (position, imgUrl, onClick) => {
        class DocThumbOverlay extends google.maps.OverlayView {
            onAdd() {
                const div = document.createElement('div');
                div.className = 'doc-thumb-overlay';
                div.innerHTML = `<img src="${imgUrl}" alt="문서">`;
                div.addEventListener('click', (e) => { e.stopPropagation(); onClick(); });
                div.querySelector('img').addEventListener('error', () => div.remove());
                this.div = div;
                this.getPanes().overlayMouseTarget.appendChild(div);
            }
            draw() {
                if (!this.div) return;
                const p = this.getProjection().fromLatLngToDivPixel(position);
                if (p) { this.div.style.left = `${p.x}px`; this.div.style.top = `${p.y}px`; }
            }
            onRemove() { this.div?.remove(); this.div = null; }
        }
        const overlay = new DocThumbOverlay();
        overlay.setMap(MapController.map);
        return overlay;
    },

    // 일정 정보 말풍선(InfoWindow) — 싱글턴으로 하나만 유지, 텍스트 위에 문서 썸네일
    showInfoWindow: (markerObj) => {
        if (!MapController.map || !markerObj?.marker || !markerObj.item) return;
        if (!MapController.infoWindow) {
            MapController.infoWindow = new google.maps.InfoWindow();
        }
        const item = markerObj.item;
        const esc = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const timeStr = (typeof UIRenderer !== 'undefined' && UIRenderer.formatDateTime)
            ? UIRenderer.formatDateTime(item.starts_at) : (item.starts_at || '');
        const thumbUrl = MapController.getThumbUrl(item);
        MapController.infoWindow.setContent(`
            <div class="map-info-wrap">
                ${thumbUrl ? `<img class="map-info-thumb" src="${thumbUrl}" alt="원본 문서" onerror="this.remove()">` : ''}
                <div class="map-info-card">
                    ${timeStr ? `<div class="map-info-time">${esc(timeStr)}</div>` : ''}
                    <div class="map-info-title">${esc(item.title || '')}</div>
                    ${item.location ? `<div class="map-info-location">${esc(item.location)}</div>` : ''}
                </div>
            </div>`);
        MapController.infoWindow.open({ map: MapController.map, anchor: markerObj.marker });
    },

    // 타임라인 닫을 때 호출될 마커 및 폴리라인 완전 삭제 메서드
    clearMarkers: () => {
        if (MapController.infoWindow) MapController.infoWindow.close();
        MapController.markers.forEach(obj => {
            if (obj.marker) obj.marker.setMap(null);
            if (obj.overlay) obj.overlay.setMap(null);
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
                        
                        const marker = new google.maps.Marker({
                            map: MapController.map,
                            position: position,
                            title: item.title,
                            icon: MapController.getPinIcon(item) // 파랑/충돌 시 빨강 표준 핀
                        });

                        const uniqueNodeId = `${item.id}-in`;
                        const openThisItem = () => {
                            // openItem → focusMarker가 카메라 이동 + InfoWindow까지 처리
                            if (typeof UIRenderer !== 'undefined' && UIRenderer.openItem) {
                                UIRenderer.openItem(item.id, uniqueNodeId);
                            }
                        };
                        marker.addListener('click', openThisItem);

                        // 핀 위 상시 문서 썸네일 말풍선 (클릭 시 핀과 동일 동작)
                        let thumbOverlay = null;
                        const thumbUrl = MapController.getThumbUrl(item);
                        if (thumbUrl) {
                            thumbOverlay = MapController.createDocThumbOverlay(position, thumbUrl, openThisItem);
                        }

                        MapController.markers.push({ itemId: item.id, marker: marker, item: item, overlay: thumbOverlay });
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
                                            title: `${item.title} (도착)`,
                                            icon: MapController.getPinIcon(item)
                                        });
                                        MapController.markers.push({ itemId: item.id, marker: arrMarker, item: item });
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
            // 좌측 플로팅 패널이 지도를 덮는 만큼 왼쪽 패딩을 늘려 가시 영역 기준으로 맞춤
            const leftPad = MapController.getCoveredLeftWidth() + 60;
            MapController.map.fitBounds(bounds, { top: 100, right: 100, bottom: 100, left: leftPad });
            google.maps.event.addListenerOnce(MapController.map, 'bounds_changed', () => {
                if (MapController.map.getZoom() > 13) MapController.map.setZoom(13);
            });
        }
    },

    // 핀: 구글 기본 스타일(풍선 + 안쪽 진한 원). 일반 파랑(blue-500) / 충돌 빨강(red-500)
    getPinIcon: (item) => {
        const fill = item?.has_conflict ? '#ef4444' : '#3b82f6';
        const inner = item?.has_conflict ? '#991b1b' : '#1e3a8a';
        const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">`
            + `<path fill="${fill}" d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z"/>`
            + `<circle cx="12" cy="9" r="2.6" fill="${inner}"/></svg>`;
        return {
            url: 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg),
            scaledSize: new google.maps.Size(38, 38),
            anchor: new google.maps.Point(19, 35), // 핀 꼬리 끝이 좌표를 가리키도록
        };
    },

    // 사용자 현재 위치로 지도 이동 (메인 화면 진입/복귀 시)
    userLocation: null,
    // 현재 위치 마커 (구글 순정 스타일: 파란 점 + 흰 링 + 은은한 헤일로)
    userLocationMarker: null,
    showUserLocationMarker: (latLng) => {
        if (!MapController.map) return;
        if (MapController.userLocationMarker) {
            MapController.userLocationMarker.setPosition(latLng);
            return;
        }
        const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48">`
            + `<circle cx="24" cy="24" r="22" fill="#4285F4" fill-opacity="0.18"/>`
            + `<circle cx="24" cy="24" r="10" fill="#ffffff"/>`
            + `<circle cx="24" cy="24" r="7.5" fill="#4285F4"/></svg>`;
        MapController.userLocationMarker = new google.maps.Marker({
            map: MapController.map,
            position: latLng,
            clickable: false,
            zIndex: 1, // 여행 핀들보다 아래
            title: '현재 위치',
            icon: {
                url: 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg),
                scaledSize: new google.maps.Size(44, 44),
                anchor: new google.maps.Point(22, 22), // 원 중심이 좌표
            },
        });
    },

    goToUserLocation: (zoom = 15) => {
        if (!MapController.map || !navigator.geolocation) return;
        const apply = (latLng) => {
            MapController.showUserLocationMarker(latLng);
            MapController.map.panTo(latLng);
            MapController.map.setZoom(zoom);
            // 좌측 패널을 제외한 가시 영역 중앙으로 보정
            setTimeout(() => {
                const offsetX = MapController.getCoveredLeftWidth() / 2;
                if (offsetX > 0) MapController.map.panBy(-offsetX, 0);
            }, 250);
        };
        if (MapController.userLocation) {
            apply(MapController.userLocation);
            return;
        }
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                MapController.userLocation = { lat: pos.coords.latitude, lng: pos.coords.longitude };
                apply(MapController.userLocation);
            },
            () => {}, // 권한 거부/실패 시 조용히 유지
            { enableHighAccuracy: false, timeout: 5000, maximumAge: 600000 }
        );
    },

    // 지도 좌측을 덮고 있는 플로팅 패널들의 폭 계산 (목록/상세 카드)
    // 패널이 지도를 덮지 않는 레이아웃에서는 자동으로 0이 됨
    getCoveredLeftWidth: () => {
        const mapEl = document.getElementById('map');
        if (!mapEl) return 0;
        const mapRect = mapEl.getBoundingClientRect();
        let covered = 0;
        document.querySelectorAll('.floating-left, #item-panel').forEach(el => {
            const r = el.getBoundingClientRect();
            // 화면에 보이면서 지도 왼쪽 가장자리에 붙어 지도를 덮는 패널만 계산
            if (r.width > 0 && r.height > 0 && r.left < mapRect.left + 40) {
                covered = Math.max(covered, r.right - mapRect.left);
            }
        });
        return Math.max(0, covered);
    },

    focusMarker: (itemId) => {
        if (!MapController.map) return;
        const targetMarkerObj = MapController.markers.find(m => m.itemId === itemId);
        if (targetMarkerObj && targetMarkerObj.marker) {
            const position = targetMarkerObj.marker.getPosition();
            if (position) {
                // 패널 제외 가시 영역의 중앙에 핀이 오도록: 덮인 폭의 절반만큼 지도를 왼쪽으로 이동
                const settle = () => {
                    const offsetX = MapController.getCoveredLeftWidth() / 2;
                    if (offsetX > 0) MapController.map.panBy(-offsetX, 0);
                    MapController.showInfoWindow(targetMarkerObj);
                };
                MapController.map.panTo(position);
                // 이미 충분히 가까우면 줌 유지, 멀면 15까지 확대
                // (settle은 패널 폭 전환 애니메이션 250ms가 끝난 뒤 측정·적용)
                if (MapController.map.getZoom() < 15) {
                    setTimeout(() => {
                        MapController.map.setZoom(15);
                        setTimeout(settle, 300);
                    }, 50);
                } else {
                    setTimeout(settle, 300);
                }
            }
        }
    }
};

const UIRenderer = {
    selectedItemId: null,
    docsData: [],
    tripsData: [],

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
        const app = document.getElementById('app-container');
        // 보관함 오버레이는 좌측 패널 상태 전환과 독립 — 열려 있으면 유지
        const keepDocs = stateClass !== 'state-docs'
            && document.querySelector('.floating-left')
            && app.classList.contains('state-docs');
        app.className = `h-screen w-screen overflow-hidden flex bg-[#f3f4f6] text-[#1e293b] antialiased ${stateClass}${keepDocs ? ' state-docs' : ''}`;
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
        UIRenderer.tripsData = await DocketAPI.fetchTrips();
        UIRenderer.renderTripCards();
    },

    // 여행 카드 렌더 — tripsData 캐시에 검색어(있으면)를 적용
    renderTripCards: () => {
        const container = document.getElementById('trip-list-container');
        const query = (document.getElementById('trip-search-input')?.value || '').toLowerCase().trim();
        const trips = query
            ? UIRenderer.tripsData.filter(t => (t.title || '').toLowerCase().includes(query))
            : UIRenderer.tripsData;
        container.innerHTML = '';

        if (trips.length === 0) {
            container.innerHTML = `<div class="text-center py-10 text-gray-400 text-sm">${query ? '검색 결과가 없습니다.' : '아직 여행이 없습니다.'}</div>`;
            return;
        }

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

            // 문서를 여행 카드 위에 드랍하면 그 여행에 일정으로 추가
            // (ring은 실선 그림자라 점선 표현이 안 됨 — outline은 레이아웃에 영향 없이 점선 가능)
            const highlight = ['outline-dashed', 'outline-2', 'outline-blue-400', 'outline-offset-[-2px]', 'bg-blue-50'];
            const prevent = (e) => { e.preventDefault(); e.stopPropagation(); };
            ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(name =>
                tripCard.addEventListener(name, prevent, false));
            ['dragenter', 'dragover'].forEach(name =>
                tripCard.addEventListener(name, () => tripCard.classList.add(...highlight), false));
            ['dragleave', 'drop'].forEach(name =>
                tripCard.addEventListener(name, () => tripCard.classList.remove(...highlight), false));
            tripCard.addEventListener('drop', async (event) => {
                const files = event.dataTransfer.files;
                if (!files || files.length === 0) return;
                // 진행 표시는 카드가 가로로 차오르는 애니메이션 하나로만
                const fillControl = createCardFill(tripCard, files.length);
                const result = await UploadController.uploadFiles(files, {
                    targetType: 'schedule',
                    tripId: trip.id,
                    onProgress: (done) => fillControl.advance(done),
                });
                if (result.failed.length > 0) {
                    fillControl.fail();
                    alert(result.failed.map(f => `${f.file}: ${f.message}`).join('\n'));
                } else {
                    fillControl.finish();
                }
                setTimeout(() => UIRenderer.renderTripList(), 700);
            });

            container.appendChild(tripCard);
        });
    },

    openTimeline: async (tripId, tripTitle) => {
        // 타임라인 패널 전체 드롭 업로드용 현재 여행 추적
        UIRenderer.currentTripId = tripId;
        UIRenderer.currentTripTitle = tripTitle;
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
        // 세로선 중심(30px)을 점(w-5, 중심 30px)과 정확히 정렬
        container.innerHTML = '<div class="absolute left-[29px] top-6 bottom-6 w-[2px] bg-gray-200 z-0 h-full"></div>';
        
        let lastDateKey = null;
        timelineItems.forEach(item => {
            // 날짜가 바뀌면 구분선(날짜 칩 + 가로선) 삽입 — 날짜 없는 일정은 '날짜 미정' 그룹
            const dateMatch = typeof item.sortTime === 'string' ? item.sortTime.match(/^(\d{4})-(\d{2})-(\d{2})/) : null;
            const dateKey = dateMatch ? dateMatch[0] : '__undated__';
            if (dateKey !== lastDateKey) {
                lastDateKey = dateKey;
                let dateLabel = '날짜 미정';
                if (dateMatch) {
                    const weekday = ['일', '월', '화', '수', '목', '금', '토'][new Date(+dateMatch[1], +dateMatch[2] - 1, +dateMatch[3]).getDay()];
                    dateLabel = `${+dateMatch[2]}월 ${+dateMatch[3]}일 (${weekday})`;
                }
                const divider = document.createElement('div');
                divider.className = 'relative z-10 flex items-center gap-2.5 mb-4';
                divider.innerHTML = `
                    <span class="flex-shrink-0 bg-gray-800 text-white text-[11px] font-bold px-3 py-1 rounded-full shadow-sm">${dateLabel}</span>
                    <div class="flex-1 h-px bg-gray-200"></div>
                `;
                container.appendChild(divider);
            }

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
                <div class="w-5 h-5 ${dotClass} rounded-full border-4 border-gray-50 z-10 flex-shrink-0 mt-1"></div>
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

        // 상세 아이템 패널이 열려 있는 경우 상세 창만 닫고 타임라인 상태로 복귀
        // (여행은 계속 보고 있으므로 currentTripId는 유지 — 패널 드롭 업로드가 계속 동작)
        if (appContainer.classList.contains('state-item')) {
            const itemPanel = document.getElementById('item-panel');
            if (itemPanel) {
                itemPanel.classList.add('is-loading');
            }
            UIRenderer.selectedItemId = null;
            UIRenderer.setAppClass('state-trip');
            return;
        }

        // 그 외의 경우 마커를 지우고 전체 여행 목록 상태로 복귀 + 지도는 현재 위치로
        UIRenderer.currentTripId = null;
        UIRenderer.currentTripTitle = null;
        if (typeof MapController !== 'undefined' && typeof MapController.clearMarkers === 'function') {
            MapController.clearMarkers();
        }
        UIRenderer.setAppClass('state-list');
        if (typeof MapController !== 'undefined' && MapController.goToUserLocation) {
            MapController.goToUserLocation();
        }
    },

    openItem: async (itemId, nodeId = null) => {
        const targetNodeId = nodeId || `${itemId}-in`;
        if (UIRenderer.selectedItemId === targetNodeId && document.getElementById('app-container').classList.contains('state-item')) {
            UIRenderer.closeItem();
            return;
        }

        UIRenderer.selectedItemId = targetNodeId;
        // 상세 패널(z-20)이 보관함 오버레이(z-35)에 가려지지 않도록 보관함은 닫음
        document.getElementById('app-container').classList.remove('state-docs');
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
                    <div class="flex justify-between items-start gap-4">
                        <dt class="text-xs text-gray-500 flex-shrink-0 whitespace-nowrap">장소</dt>
                        <dd class="text-xs font-medium text-gray-900 text-right break-words min-w-0">${displayLocation}</dd>
                    </div>
                    <div class="flex justify-between items-start gap-4 border-t border-gray-50 pt-3">
                        <dt class="text-xs text-gray-500 flex-shrink-0 whitespace-nowrap">예약 번호</dt>
                        <dd class="text-xs font-medium text-gray-900 text-right break-words min-w-0">${displayBookingRef}</dd>
                    </div>
                    ${displayCancelDead ? `
                    <div class="flex justify-between items-center gap-4 border-t border-gray-50 pt-3">
                        <dt class="text-xs text-gray-500 flex-shrink-0 whitespace-nowrap">무료 취소 기한</dt>
                        <dd class="text-xs font-medium text-red-600 text-right">${displayCancelDead}</dd>
                    </div>
                    ` : ''}
                    <div class="flex justify-between items-center gap-4 border-t border-gray-50 pt-3">
                        <dt class="text-xs text-gray-500 flex-shrink-0 whitespace-nowrap">결제 금액</dt>
                        <dd class="text-xs font-medium text-gray-900 text-right">${displayPrice}</dd>
                    </div>
                    <div class="flex justify-between items-center gap-4 border-t border-gray-50 pt-3">
                        <dt class="text-xs text-gray-500 flex-shrink-0 whitespace-nowrap">원본 문서</dt>
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
        if (document.querySelector('.floating-left')) {
            // 보관함은 오버레이 — 현재 패널 상태(목록/타임라인)를 유지한 채 위에 띄움
            document.getElementById('app-container').classList.add('state-docs');
        } else {
            UIRenderer.setAppClass('state-docs');
        }
        UIRenderer.setLNBActive('docs');
        
        const container = document.getElementById('docs-grid-container');
        container.innerHTML = '<div class="col-span-full text-center py-10 text-gray-400"><i class="fa-solid fa-circle-notch fa-spin text-2xl mb-2"></i><p>문서를 불러오는 중입니다...</p></div>';
        
        UIRenderer.docsData = await DocketAPI.fetchAllDocuments();
        UIRenderer.renderDocsList(UIRenderer.docsData);
    },

    closeDocs: () => {
        if (document.querySelector('.floating-left')) {
            // 오버레이만 걷어내고 이전 화면(목록/타임라인) 그대로 유지
            document.getElementById('app-container').classList.remove('state-docs');
        } else {
            UIRenderer.setAppClass('state-list');
            UIRenderer.setLNBActive('trip');
        }
    },

    renderDocsList: (docs) => {
        const container = document.getElementById('docs-grid-container');
        container.innerHTML = '';

        if (docs.length === 0) {
            container.innerHTML = '<div class="col-span-full text-center py-20 text-gray-400"><i class="fa-regular fa-folder-open text-4xl mb-3"></i><p>보관된 문서가 없습니다.</p></div>';
            return;
        }

        // 여행별 그룹핑 — 문서가 최신순이므로 그룹도 최근 문서가 있는 여행부터
        const groups = new Map();
        docs.forEach(doc => {
            const key = doc.trip_id || doc.trip_title || '__etc__';
            if (!groups.has(key)) groups.set(key, { title: doc.trip_title || '미분류', docs: [] });
            groups.get(key).docs.push(doc);
        });

        groups.forEach(group => {
            // 그룹 헤더: 여행 이름 + 문서 수 + 가로선 (그리드 한 줄 전체 차지)
            const header = document.createElement('div');
            header.className = 'col-span-full flex items-center gap-2.5 mt-2 first:mt-0';
            header.innerHTML = `
                <i class="fa-solid fa-suitcase-rolling text-blue-600 text-sm"></i>
                <h3 class="text-sm font-bold text-gray-900">${group.title}</h3>
                <span class="text-[11px] font-bold text-gray-400">${group.docs.length}</span>
                <div class="flex-1 h-px bg-gray-200"></div>
            `;
            container.appendChild(header);

            group.docs.forEach(doc => {
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

// 카드가 진행바처럼 가로로 차오르는 진행 표시 (문서당 ~40초 기준 시뮬레이션)
const createCardFill = (card, totalFiles) => {
    card.classList.add('relative', 'overflow-hidden');
    const fill = document.createElement('div');
    fill.className = 'absolute inset-y-0 left-0 pointer-events-none';
    fill.style.cssText = 'width:0%; background:rgba(59,130,246,0.14); transition:width .5s ease, opacity .5s ease, background .3s ease;';
    card.appendChild(fill);

    let done = 0;
    let fileStart = Date.now();
    const update = () => {
        const seconds = (Date.now() - fileStart) / 1000;
        const inner = Math.min(0.95, 1 - Math.exp(-seconds / 14)); // 40초쯤에 ~94%
        fill.style.width = `${Math.min(99, ((done + inner) / totalFiles) * 100)}%`;
    };
    const timer = setInterval(update, 400);
    update();

    return {
        advance: (newDone) => { done = newDone; fileStart = Date.now(); update(); },
        finish: () => {
            clearInterval(timer);
            fill.style.background = 'rgba(59,130,246,0.22)';
            fill.style.width = '100%';
            setTimeout(() => { fill.style.opacity = '0'; }, 500);
            setTimeout(() => fill.remove(), 1100);
        },
        fail: () => {
            clearInterval(timer);
            fill.style.background = 'rgba(239,68,68,0.16)';
            fill.style.width = '100%';
            setTimeout(() => { fill.style.opacity = '0'; }, 900);
            setTimeout(() => fill.remove(), 1500);
        },
    };
};

const UploadController = {
    stagedFiles: [],
    returnState: 'state-list',
    uploadMode: 'trip',
    targetTripId: '',   // schedule 모드에서 일정을 추가할 대상 여행 id

    openUpload: (uploadMode = 'trip', returnState = 'state-list', targetTripId = '') => {
        UploadController.uploadMode = uploadMode;
        UploadController.returnState = returnState;
        UploadController.targetTripId = targetTripId;
        const isSchedule = uploadMode === 'schedule';
        document.getElementById('upload-panel-title').innerText = isSchedule ? '새 일정 추가' : '새 여행 추가';
        UIRenderer.setAppClass('state-upload');
    },

    closeUpload: () => {
        const returnState = UploadController.returnState;
        UploadController.clearFiles();
        UploadController.returnState = 'state-list';
        UploadController.uploadMode = 'trip';
        UploadController.targetTripId = '';
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

    // 타임라인(여행 상세) 패널: 어디에 놓아도 현재 열린 여행에 일정으로 추가
    // (드래그 안내·진행 표시는 지도 영역 드롭 독/알약이 전담 — 패널 자체 표시 없음)
    initTimelinePanelDrop: () => {
        const panel = document.getElementById('trip-panel');
        if (!panel) return;

        const uploadToCurrentTrip = async (files) => {
            const tripId = UIRenderer.currentTripId;
            if (!tripId || !files || files.length === 0) return;
            const result = await UploadController.uploadFiles(files, { targetType: 'schedule', tripId });
            if (result.failed.length > 0) {
                alert(result.failed.map(f => `${f.file}: ${f.message}`).join('\n'));
            }
            // 타임라인·지도·여행 목록(기간 확장 반영) 갱신
            UIRenderer.openTimeline(tripId, UIRenderer.currentTripTitle || '');
            UIRenderer.renderTripList();
        };

        panel.addEventListener('dragover', (e) => e.preventDefault());
        panel.addEventListener('drop', (e) => {
            e.preventDefault();
            e.stopPropagation();
            uploadToCurrentTrip(e.dataTransfer.files);
        });
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

    // 드롭 독: 평소 하단 중앙 알약 → 파일이 창 위로 오면 지도 영역 전체로 확장
    initDropDock: () => {
        const dock = document.getElementById('drop-dock');
        if (!dock) return;
        const textEl = document.getElementById('drop-dock-text');
        const defaultText = '문서를 화면으로 끌어오세요';
        let dragDepth = 0;

        const expand = (on) => {
            dock.classList.toggle('expanded', on);
            if (on) {
                textEl.textContent = UIRenderer.currentTripId
                    ? '바보는 방황을 하고 현명한 사람은 여행을 한다. - 토마스 폴러'
                    : '여행은 사람과 같다. 어느 두 여행도 똑같지 않다. - 존 스타인벡';
            } else if (!dock.dataset.busy) {
                textEl.textContent = defaultText;
            }
        };

        // 캡처 단계에서 수신: 패널/카드 핸들러의 stopPropagation과 무관하게
        // 어디에 드롭하든 독이 확실히 접히도록 보장
        window.addEventListener('dragenter', (e) => {
            if (![...(e.dataTransfer?.types || [])].includes('Files')) return;
            dragDepth += 1;
            expand(true);
        }, true);
        window.addEventListener('dragover', (e) => e.preventDefault(), true);
        window.addEventListener('dragleave', () => {
            dragDepth = Math.max(0, dragDepth - 1);
            if (dragDepth === 0) expand(false);
        }, true);
        window.addEventListener('drop', (e) => {
            e.preventDefault(); // 브라우저가 파일을 열어버리는 것 방지
            dragDepth = 0;
            expand(false);
        }, true);

        dock.addEventListener('drop', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            dragDepth = 0;
            expand(false);
            const files = e.dataTransfer.files;
            if (!files || files.length === 0) return;

            const tripId = UIRenderer.currentTripId;
            if (!tripId) {
                UploadController.uploadAsNewTrip(files); // 새 여행: 플레이스홀더 카드가 진행 표시
                return;
            }
            // 현재 열린 여행에 추가 — 알약 진행 표시는 uploadFiles가 공용으로 처리
            const result = await UploadController.uploadFiles(files, { targetType: 'schedule', tripId });
            if (result.failed.length > 0) {
                alert(result.failed.map(f => `${f.file}: ${f.message}`).join('\n'));
            }
            UIRenderer.openTimeline(tripId, UIRenderer.currentTripTitle || '');
            UIRenderer.renderTripList();
        });
    },

    // 하단 드롭존: 새 여행 생성 업로드 — 목록 맨 위에 플레이스홀더 카드가 차오르며 진행 표시
    uploadAsNewTrip: async (files) => {
        if (!files || files.length === 0) return;
        const container = document.getElementById('trip-list-container');
        const placeholder = document.createElement('div');
        placeholder.className = 'bg-white border-2 border-blue-200 rounded-xl p-4 shadow-sm';
        // 실제 여행 카드와 동일한 2줄 구조(제목 + 날짜 줄)로 위아래 간격을 맞춤
        placeholder.innerHTML = `
            <h3 class="text-lg font-bold text-gray-400 mb-1">새 여행 만드는 중…</h3>
            <p class="text-xs text-gray-400"><i class="fa-regular fa-calendar mr-1"></i> <span class="placeholder-stage">문서를 읽는 중</span></p>`;
        container.appendChild(placeholder);
        placeholder.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        const fillControl = createCardFill(placeholder, files.length);

        // 진행 시간에 따라 에이전트 단계 멘트가 순환
        const stageEl = placeholder.querySelector('.placeholder-stage');
        const stages = ['문서를 읽는 중', '문서 유형 분류 중', '핵심 정보 추출 중',
                        '일정으로 정리하는 중', '캘린더에 등록하는 중'];
        let stageIndex = 0;
        const stageTimer = setInterval(() => {
            stageIndex = (stageIndex + 1) % stages.length;
            stageEl.textContent = stages[stageIndex];
        }, 8000);

        const result = await UploadController.uploadFiles(files, {
            targetType: 'trip',
            onProgress: (done) => fillControl.advance(done),
        });
        clearInterval(stageTimer);
        stageEl.textContent = '완료!';
        if (result.failed.length > 0) {
            fillControl.fail();
            alert(result.failed.map(f => `${f.file}: ${f.message}`).join('\n'));
        } else {
            fillControl.finish();
        }
        setTimeout(() => UIRenderer.renderTripList(), 700);
    },

    // 하단 알약(드롭 독) 공용 진행 표시 — 어떤 경로로 업로드하든 동일하게 동작
    // 에이전트 파이프라인 단계에 맞춰 멘트가 8초마다 넘어감 (문서당 30~45초 소요 기준)
    // 처리 중에 추가로 드롭한 문서도 전역 큐로 합산: (1/1) → 추가 드롭 → (1/2), (2/2)
    DOCK_STAGES: ['문서를 읽는 중', '문서 유형 분류 중', '핵심 정보 추출 중',
                  '일정으로 정리하는 중', '캘린더에 등록하는 중'],
    _dockState: { active: 0, total: 0, done: 0, stageIndex: 0, timer: null },

    _renderDockStage: () => {
        const state = UploadController._dockState;
        const dock = document.getElementById('drop-dock');
        const textEl = document.getElementById('drop-dock-text');
        if (!dock || !textEl || state.active === 0 || dock.classList.contains('expanded')) return;
        // 카운터는 에이전트 단계 진행률 (1/5 ~ 5/5), 문서가 여러 개일 때만 몇 번째 문서인지 앞에 표시
        const stageText = `${UploadController.DOCK_STAGES[state.stageIndex]}… (${state.stageIndex + 1}/${UploadController.DOCK_STAGES.length})`;
        const docCurrent = Math.min(state.done + 1, state.total);
        textEl.textContent = state.total > 1 ? `${docCurrent}번째 문서 · ${stageText}` : stageText;
    },

    dockUploadStart: (count) => {
        const state = UploadController._dockState;
        const dock = document.getElementById('drop-dock');
        state.active += 1;
        state.total += count;
        if (dock) dock.dataset.busy = '1';
        if (!state.timer) {
            state.timer = setInterval(() => {
                state.stageIndex = Math.min(state.stageIndex + 1, UploadController.DOCK_STAGES.length - 1);
                UploadController._renderDockStage();
            }, 8000);
        }
        UploadController._renderDockStage();
    },

    dockFileStart: () => {
        UploadController._dockState.stageIndex = 0; // 새 문서 → 단계 멘트 처음부터
        UploadController._renderDockStage();
    },

    dockFileDone: () => {
        UploadController._dockState.done += 1;
    },

    dockUploadEnd: () => {
        const state = UploadController._dockState;
        state.active = Math.max(0, state.active - 1);
        if (state.active > 0) return; // 다른 업로드가 아직 진행 중이면 큐 유지
        clearInterval(state.timer);
        state.timer = null;
        state.total = 0; state.done = 0; state.stageIndex = 0;
        const dock = document.getElementById('drop-dock');
        const textEl = document.getElementById('drop-dock-text');
        if (!dock) return;
        delete dock.dataset.busy;
        if (textEl && !dock.classList.contains('expanded')) textEl.textContent = '완료!';
        setTimeout(() => {
            if (textEl && !dock.dataset.busy && !dock.classList.contains('expanded')) {
                textEl.textContent = '문서를 화면으로 끌어오세요';
            }
        }, 1200);
    },

    // 실제 업로드 엔진: 파일들을 순차로 백엔드에 전송 (문서당 30~45초 소요)
    // 반환: { ok: 성공 수, failed: [{file, message}] }
    uploadFiles: async (files, { targetType = 'trip', tripId = '', onProgress = null } = {}) => {
        const list = Array.from(files);
        const failed = [];
        let ok = 0;
        UploadController.dockUploadStart(list.length);
        for (let i = 0; i < list.length; i++) {
            if (onProgress) onProgress(i, list.length, list[i].name);
            UploadController.dockFileStart();
            try {
                await DocketAPI.parseDocument({ document: list[i], targetType, tripId });
                ok += 1;
            } catch (error) {
                failed.push({ file: list[i].name, message: error.message });
            }
            UploadController.dockFileDone();
        }
        if (onProgress) onProgress(list.length, list.length, '');
        UploadController.dockUploadEnd();
        return { ok, failed };
    },

    // 업로드 패널용 실행 (진행바 없음 — 진행 표시는 카드 차오르기 방식으로 통일)
    startParsing: async () => {
        if (!UploadController.hasInput()) return;
        const parseButton = document.getElementById('btn-parse');
        parseButton.disabled = true;
        parseButton.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-2"></i>에이전트가 문서를 분석 중입니다…';

        const result = await UploadController.uploadFiles(UploadController.stagedFiles, {
            targetType: UploadController.uploadMode,
            tripId: UploadController.targetTripId || '',
        });
        parseButton.innerHTML = '문서 분석 시작';

        if (result.failed.length > 0) {
            alert(result.failed.map(f => `${f.file}: ${f.message}`).join('\n'));
        }
        UploadController.closeUpload();
        UIRenderer.renderTripList();
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
    UploadController.initTimelinePanelDrop();
    UploadController.initDropDock();

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
    document.getElementById('trip-search-input')?.addEventListener('input', UIRenderer.renderTripCards);
    
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
        ['dragenter', 'dragover'].forEach(eventName => inlineDropZone.addEventListener(eventName, () => inlineDropZone.classList.add('drop-aurora-active'), false));
        ['dragleave', 'drop'].forEach(eventName => inlineDropZone.addEventListener(eventName, () => inlineDropZone.classList.remove('drop-aurora-active'), false));
        
        inlineDropZone.addEventListener('drop', (e) => {
            const files = e.dataTransfer.files;
            if (files.length > 0) UploadController.uploadAsNewTrip(files);
        });

        inlineDropZone.addEventListener('click', () => inlineFileInput.click());
        inlineFileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) UploadController.uploadAsNewTrip(e.target.files);
            inlineFileInput.value = '';
        });
    }
});