const API_BASE_URL = window.API_BASE_URL || '';
const USE_MOCK_API = window.USE_MOCK_API !== false;

const DocketAPI = {
    request: async (path) => {
        const response = await fetch(`${API_BASE_URL}${path}`, { headers: { Accept: 'application/json' } });
        if (!response.ok) throw new Error(`API 요청 실패 (${response.status})`);
        return response.json();
    },

    fetchTrips: async () => {
        const user = JSON.parse(sessionStorage.getItem('docket_user') || '{}');
        if (!USE_MOCK_API) {
            const query = user.id ? `?userId=${encodeURIComponent(user.id)}` : '';
            return DocketAPI.request(`/api/trips${query}`);
        }
        return new Promise(resolve => setTimeout(() => resolve([
            { id: 'T001', userId: user.id || 'demo-user', title: '서유럽 3개국 일주', startDate: '2026.09.01', endDate: '2026.09.15', conflictCount: 1, status: 'active' },
            { id: 'T002', userId: user.id || 'demo-user', title: '도쿄 주말 여행', startDate: '2026.07.12', endDate: '2026.07.14', conflictCount: 0, status: 'past' }
        ]), 400));
    },

    fetchTripDetails: async (tripId) => {
        if (!USE_MOCK_API) return DocketAPI.request(`/api/trips/${encodeURIComponent(tripId)}/items`);
        const items = tripId === 'T001' ? [
            { id: 'I001', tripId, type: 'flight', time: '10:00 AM', title: '인천(ICN) -> 파리(CDG)', desc: '대한항공 KE901', price: null, hasConflict: false },
            { id: 'I002', tripId, type: 'hotel', time: '18:00 PM', title: '르 메르디앙 파리 에투알', desc: '체크인', price: 450000, hasConflict: false, refundDeadline: '오늘 23:59' },
            { id: 'I003', tripId, type: 'museum', time: '19:00 PM', title: '루브르 박물관 야간 입장', desc: '예약번호: LVR-9928', price: 35000, hasConflict: true, conflictMsg: '물리적 이동 시간 부족', qrCodeStr: 'LVR-9928-ABC', location: '파리, 프랑스' }
        ] : [];
        return new Promise(resolve => setTimeout(() => resolve(items), 500));
    },

    fetchItemDetail: async (itemId) => {
        if (!USE_MOCK_API) return DocketAPI.request(`/api/items/${encodeURIComponent(itemId)}`);
        return new Promise(resolve => setTimeout(() => resolve({
            id: itemId, title: '루브르 박물관 야간 입장', timeStr: '2026.09.01 19:00 - 22:00', price: 35000, hasConflict: true,
            conflictDetail: '이전 일정 종료 후 대중교통으로 1시간 15분이 소요되어 19:00 입장이 물리적으로 불가능합니다.', qrCodeStr: 'LVR-9928-ABC'
        }), 300));
    }
};
