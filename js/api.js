const API_BASE_URL = window.API_BASE_URL || '';
const USE_MOCK_API = window.USE_MOCK_API !== false;

const buildTickets = (qrImages, qrCodeStr, fallbackId = 'ticket', allowTextFallback = false) => {
    if (Array.isArray(qrImages) && qrImages.length > 0) {
        return qrImages.map((image, index) => ({
            id: `${fallbackId}-ticket-${index + 1}`,
            qrCodeStr: image?.value || qrCodeStr || '',
            label: `티켓 ${index + 1}`,
            imageUrl: image?.url || ''
        }));
    }
    if (allowTextFallback && qrCodeStr) {
        return [{ id: `${fallbackId}-ticket-1`, qrCodeStr, label: '티켓 1', imageUrl: '' }];
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
            const detail = typeof payload === 'object' && payload?.detail ? `: ${payload.detail}` : '';
            throw new Error(`API 요청 실패 (${response.status})${detail}`);
        }
        return payload;
    },

    fetchTrips: async () => {
        if (!USE_MOCK_API) {
            return DocketAPI.request('/api/trips');
        }
        const user = JSON.parse(sessionStorage.getItem('docket_user') || '{}');
        return new Promise(resolve => setTimeout(() => resolve([
            { id: 'T001', userId: user.id || 'demo-user', title: '서유럽 3개국 일주', startDate: '2026.09.01', endDate: '2026.09.15', conflictCount: 1, status: 'active' },
            { id: 'T002', userId: user.id || 'demo-user', title: '도쿄 주말 여행', startDate: '2026.07.12', endDate: '2026.07.14', conflictCount: 0, status: 'past' }
        ]), 400));
    },

    fetchTripDetails: async (tripId) => {
        if (!USE_MOCK_API) {
            const rows = await DocketAPI.request(`/api/trips/${encodeURIComponent(tripId)}/items`);
            return rows.map(row => {
                const actualQrCode = row.qr_code || row.qrCode || row.qrCodeStr || '';
                return {
                    ...row,
                    tripId,
                    time: row.time || '',
                    desc: row.desc || '',
                    tickets: buildTickets(row.qrImages, actualQrCode, row.id)
                };
            });
        }
        const items = tripId === 'T001' ? [
            { id: 'I001', tripId, type: 'flight', time: '10:00 AM', title: '인천(ICN) -> 파리(CDG)', desc: '대한항공 KE901', price: null, hasConflict: false },
            { id: 'I002', tripId, type: 'hotel', time: '18:00 PM', title: '르 메르디앙 파리 에투알', desc: '체크인', price: 450000, hasConflict: false, refundDeadline: '오늘 23:59' },
            { id: 'I003', tripId, type: 'museum', time: '19:00 PM', title: '루브르 박물관 야간 입장', desc: '예약번호: LVR-9928', price: 35000, hasConflict: true, conflictMsg: '물리적 이동 시간 부족', location: '파리, 프랑스', tickets: [
                { id: 'TK001', qrCodeStr: 'LVR-9928-ABC', label: '티켓 1' },
                { id: 'TK002', qrCodeStr: 'LVR-9928-XYZ', label: '티켓 2' }
            ] }
        ] : [];
        return new Promise(resolve => setTimeout(() => resolve(items), 500));
    },

    fetchItemDetail: async (itemId) => {
        if (!USE_MOCK_API) {
            const row = await DocketAPI.request(`/api/items/${encodeURIComponent(itemId)}`);
            const actualQrCode = row.qr_code || '';
            return {
                ...row,
                qrCodeStr: actualQrCode,
                notes: Array.isArray(row.notes) ? row.notes : [],
                tickets: buildTickets(row.qrImages, actualQrCode, row.id, true)
            };
        }
        
        return new Promise(resolve => setTimeout(() => {
            if (itemId === 'I001') {
                resolve({
                    id: itemId, title: '인천(ICN) -> 파리(CDG)', timeStr: '2026.09.01 10:00 - 22:00', price: null, hasConflict: false, qrCodeStr: '', tickets: []
                });
            } else if (itemId === 'I002') {
                resolve({
                    id: itemId, title: '르 메르디앙 파리 에투알', timeStr: '2026.09.01 18:00 - 18:30', price: 450000, hasConflict: false, qrCodeStr: '', tickets: []
                });
            } else {
                resolve({
                    id: itemId, title: '루브르 박물관 야간 입장', timeStr: '2026.09.01 19:00 - 22:00', price: 35000, hasConflict: true,
                    conflictDetail: '이전 일정 종료 후 대중교통으로 1시간 15분이 소요되어 19:00 입장이 물리적으로 불가능합니다.', qrCodeStr: 'LVR-9928-ABC', tickets: [
                        { id: 'TK001', qrCodeStr: 'LVR-9928-ABC', label: '티켓 1' },
                        { id: 'TK002', qrCodeStr: 'LVR-9928-XYZ', label: '티켓 2' }
                    ]
                });
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
            return DocketAPI.request('/api/documents/parse', {
                method: 'POST',
                body: formData
            });
        }

        return new Promise(resolve => setTimeout(() => resolve({
            dryRun: Boolean(dryRun),
            docType: targetType === 'trip' ? null : 'hotel',
            trip: { id: 'T001', title: '새 여행', startDate: null, endDate: null, status: 'active' },
            item: null,
            items: [],
            extracted: {},
            notes: ['목업 응답입니다. USE_MOCK_API=false로 백엔드와 연결하세요.'],
            conflicts: [],
            actions: [{ tool: 'trip_flow', status: 'not_implemented' }]
        }), 600));
    }
};