const API_BASE_URL = window.API_BASE_URL || '';
const USE_MOCK_API = window.USE_MOCK_API !== false;

const buildTickets = (qr_images, qr_code, fallbackId = 'ticket', allowTextFallback = false) => {
    if (Array.isArray(qr_images) && qr_images.length > 0) {
        return qr_images.map((image, index) => ({
            id: `${fallbackId}-ticket-${index + 1}`,
            qr_code: image?.value || qr_code || '',
            label: `티켓 ${index + 1}`,
            image_url: image?.url || ''
        }));
    }
    if (allowTextFallback && qr_code) {
        return [{ id: `${fallbackId}-ticket-1`, qr_code: qr_code, label: '티켓 1', image_url: '' }];
    }
    return [];
};

const DocketAPI = {
    request: async (path, options = {}) => {
        const headers = { Accept: 'application/json', ...(options.headers || {}) };
        const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
        const isJson = (response.headers.get('content-type') || '').includes('application/json');
        const payload = isJson ? await response.json() : await response.text();
        if (!response.ok) {
            // 409(중복 등)는 body의 message에 사용자용 문구가 담김
            const reason = typeof payload === 'object' ? (payload?.message || payload?.detail) : '';
            throw new Error(reason || `API 요청 실패 (${response.status})`);
        }
        return payload;
    },

    fetchTrips: async () => {
        if (!USE_MOCK_API) {
            return DocketAPI.request('/api/trips');
        }
        const user = JSON.parse(sessionStorage.getItem('docket_user') || '{}');
        return new Promise(resolve => setTimeout(() => resolve([
            { id: 'T001', title: '서유럽 3개국 일주', start_date: '2026-09-01', end_date: '2026-09-15', conflictCount: 1, status: 'active' },
            { id: 'T002', title: '도쿄 주말 여행', start_date: '2026-07-12', end_date: '2026-07-14', conflictCount: 0, status: 'past' }
        ]), 400));
    },

    fetchTripDetails: async (tripId) => {
        if (!USE_MOCK_API) {
            const rows = await DocketAPI.request(`/api/trips/${encodeURIComponent(tripId)}/items`);
            return rows.map(row => ({
                ...row,
                tickets: buildTickets(row.qr_images, row.qr_code, row.id)
            }));
        }
        const items = tripId === 'T001' ? [
            { id: 'I001', trip_id: tripId, type: 'flight', title: '인천(ICN) -> 파리(CDG)', starts_at: '2026-09-01T10:00:00Z', ends_at: '2026-09-01T22:00:00Z', price: null, has_conflict: false },
            { id: 'I002', trip_id: tripId, type: 'hotel', title: '르 메르디앙 파리 에투알', location: '파리, 프랑스', starts_at: '2026-09-01T18:00:00Z', ends_at: '2026-09-03T11:00:00Z', price: 450000, has_conflict: false, booking_ref: 'MER-8812', cancellation_deadline: '2026-08-31T23:59:00Z' },
            { id: 'I003', trip_id: tripId, type: 'museum', title: '루브르 박물관 야간 입장', location: '파리, 프랑스', starts_at: '2026-09-01T19:00:00Z', ends_at: '2026-09-01T22:00:00Z', price: 35000, has_conflict: true, conflict_msg: '물리적 이동 시간 부족', booking_ref: 'LVR-9928', qr_code: 'LVR-9928-ABC', tickets: [
                { id: 'TK001', qr_code: 'LVR-9928-ABC', label: '티켓 1' },
                { id: 'TK002', qr_code: 'LVR-9928-XYZ', label: '티켓 2' }
            ] }
        ] : [];
        return new Promise(resolve => setTimeout(() => resolve(items), 500));
    },

    fetchItemDetail: async (itemId) => {
        if (!USE_MOCK_API) {
            const row = await DocketAPI.request(`/api/items/${encodeURIComponent(itemId)}`);
            return {
                ...row,
                tickets: buildTickets(row.qr_images, row.qr_code, row.id, true)
            };
        }
        
        return new Promise(resolve => setTimeout(() => {
            if (itemId === 'I001') {
                resolve({ id: itemId, type: 'flight', title: '인천(ICN) -> 파리(CDG)', starts_at: '2026-09-01T10:00:00Z', ends_at: '2026-09-01T22:00:00Z', price: null, has_conflict: false, tickets: [] });
            } else if (itemId === 'I002') {
                resolve({ id: itemId, type: 'hotel', title: '르 메르디앙 파리 에투알', location: '파리, 프랑스', starts_at: '2026-09-01T18:00:00Z', ends_at: '2026-09-03T11:00:00Z', price: 450000, has_conflict: false, booking_ref: 'MER-8812', cancellation_deadline: '2026-08-31T23:59:00Z', tickets: [] });
            } else {
                resolve({ id: itemId, type: 'museum', title: '루브르 박물관 야간 입장', location: '파리, 프랑스', starts_at: '2026-09-01T19:00:00Z', ends_at: '2026-09-01T22:00:00Z', price: 35000, has_conflict: true, conflict_msg: '이전 일정 종료 후 19:00 입장이 물리적으로 불가능합니다.', booking_ref: 'LVR-9928', qr_code: 'LVR-9928-ABC', tickets: [
                    { id: 'TK001', qr_code: 'LVR-9928-ABC', label: '티켓 1' },
                    { id: 'TK002', qr_code: 'LVR-9928-XYZ', label: '티켓 2' }
                ]});
            }
        }, 300));
    },

    parseDocument: async ({ document, targetType = 'schedule', tripId = '', text = '', dryRun = false }) => {
        if (!document) throw new Error('document 파일이 필요합니다.');
        const formData = new FormData();
        formData.append('document', document);
        formData.append('targetType', targetType);
        if (tripId) formData.append('tripId', tripId);
        if (text) formData.append('text', text);
        if (dryRun) formData.append('dryRun', 'true');

        if (!USE_MOCK_API) {
            return DocketAPI.request('/api/documents/parse', { method: 'POST', body: formData });
        }
        return new Promise(resolve => setTimeout(() => resolve({
            dryRun: Boolean(dryRun),
            docType: targetType === 'trip' ? null : 'hotel',
            trip: { id: 'T001', title: '새 여행', start_date: null, end_date: null, status: 'active' },
            item: null, items: [], extracted: {}, notes: [], conflicts: [], actions: []
        }), 600));
    },

    // 신규 추가: 문서 상세 정보 및 원본 URL을 호출하는 통신 메서드
    fetchDocumentDetail: async (documentId) => {
        if (!USE_MOCK_API) {
            return DocketAPI.request(`/api/documents/${encodeURIComponent(documentId)}`);
        }
        
        // 목업 환경 동작 시뮬레이션
        return new Promise(resolve => setTimeout(() => resolve({
            id: documentId,
            item_id: 'mock-item-id',
            file_name: 'mock_voucher.pdf',
            mime_type: 'application/pdf',
            doc_type: 'hotel',
            storage_path: 'mock_path.pdf',
            original_url: 'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf', // 임시 테스트 PDF
            parsed_html: '<html><body>Mock HTML</body></html>',
            extracted: {},
            created_at: '2026-08-22T15:55:57Z'
        }), 400));
    },

    // 신규 추가: 프론트엔드 기반 문서 집계 로직
    fetchAllDocuments: async () => {
        const trips = await DocketAPI.fetchTrips();
        const allDocs = new Map();

        for (const trip of trips) {
            const items = await DocketAPI.fetchTripDetails(trip.id);
            items.forEach(item => {
                if (item.document_id && !allDocs.has(item.document_id)) {
                    allDocs.set(item.document_id, {
                        document_id: item.document_id,
                        file_name: item.document_file_name || `${item.type || 'document'}_voucher.pdf`, // API 응답 누락 대비 방어
                        doc_type: item.type || 'other',
                        trip_id: trip.id,
                        trip_title: trip.title,
                        item_title: item.title,
                        created_at: item.created_at || item.starts_at || ''
                    });
                }
            });
        }
        // 최신 등록순 정렬 반환
        return Array.from(allDocs.values()).sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
    },
};