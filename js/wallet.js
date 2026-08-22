const WalletController = {
    escapeHtml: (value = '') => String(value).replace(/[&<>'"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]),

    renderPass: (pass) => `
        <article class="wallet-pass" data-pass-id="${WalletController.escapeHtml(pass.id)}" data-ticket-index="0">
            <div class="wallet-pass-main">
                <div class="wallet-pass-type"><i class="fa-solid fa-ticket"></i> ${WalletController.escapeHtml(pass.type || '예약 패스')}</div>
                <h3>${WalletController.escapeHtml(pass.title)}</h3>
                <div class="wallet-pass-meta"><span><i class="fa-regular fa-calendar"></i>${WalletController.escapeHtml(pass.date || '날짜 정보 없음')}</span><span><i class="fa-regular fa-clock"></i>${WalletController.escapeHtml(pass.time || '시간 정보 없음')}</span></div>
                <p class="wallet-pass-location"><i class="fa-solid fa-location-dot"></i>${WalletController.escapeHtml(pass.location || '장소 정보 없음')}</p>
            </div>
            <div class="wallet-pass-divider"><span></span><span></span></div>
            <div class="wallet-pass-code">
                <button class="wallet-ticket-arrow wallet-ticket-prev" type="button" aria-label="이전 티켓"><i class="fa-solid fa-chevron-left"></i></button>
                <div class="wallet-ticket-view"><div class="wallet-qr"><i class="fa-solid fa-qrcode"></i></div><strong class="wallet-ticket-code">${WalletController.escapeHtml(pass.tickets[0].code)}</strong><small class="wallet-ticket-label">${WalletController.escapeHtml(pass.tickets[0].label || '티켓 1')}</small></div>
                <button class="wallet-ticket-arrow wallet-ticket-next" type="button" aria-label="다음 티켓"><i class="fa-solid fa-chevron-right"></i></button>
                <div class="wallet-ticket-dots">${pass.tickets.map((ticket, index) => `<button type="button" class="wallet-ticket-dot${index === 0 ? ' is-active' : ''}" data-ticket-index="${index}" aria-label="${WalletController.escapeHtml(ticket.label || `티켓 ${index + 1}`)}"></button>`).join('')}</div>
                <small>현장에서 제시하세요</small>
            </div>
        </article>
    `,

    renderTrip: (trip) => `
        <section class="wallet-trip-block">
            <header class="wallet-trip-header">
                <div><span class="wallet-trip-status ${trip.status === 'active' ? 'active' : 'past'}">${trip.status === 'active' ? '진행 예정' : '지난 여행'}</span><h2>${WalletController.escapeHtml(trip.title)}</h2></div>
                <p>${WalletController.escapeHtml(trip.startDate)} - ${WalletController.escapeHtml(trip.endDate)}</p>
            </header>
            <div class="wallet-pass-list">${trip.passes.length ? trip.passes.map(WalletController.renderPass).join('') : '<div class="wallet-empty"><i class="fa-regular fa-folder-open"></i><p>등록된 QR 패스가 없습니다.</p></div>'}</div>
        </section>
    `,

    load: async () => {
        const content = document.getElementById('wallet-content');
        content.innerHTML = '<div class="wallet-loading"><i class="fa-solid fa-spinner"></i><p>여행과 예약 패스를 불러오는 중입니다.</p></div>';
        const trips = await DocketAPI.fetchTrips();
        const tripsWithPasses = await Promise.all(trips.map(async trip => {
            const items = await DocketAPI.fetchTripDetails(trip.id);
            const passes = items.filter(item => item.tripId === trip.id && (item.qrCodeStr || item.tickets?.some(ticket => ticket.qrCodeStr))).map(item => ({
                id: item.id,
                title: item.title,
                date: item.date || item.time,
                time: item.time,
                location: item.location || item.desc,
                code: item.qrCodeStr,
                type: item.type,
                tickets: item.tickets?.length ? item.tickets : [{ id: `${item.id}-ticket`, qrCodeStr: item.qrCodeStr, label: '티켓 1' }]
            }));
            return { ...trip, passes };
        }));
        content.innerHTML = tripsWithPasses.map(WalletController.renderTrip).join('');
        content.querySelectorAll('.wallet-pass').forEach(passElement => WalletController.bindTicketSlider(passElement, tripsWithPasses));
    },

    bindTicketSlider: (passElement, trips) => {
        const pass = trips.flatMap(trip => trip.passes).find(item => item.id === passElement.dataset.passId);
        if (pass) TicketSlider.bind(passElement, pass);
    },

    init: async () => {
        if (!sessionStorage.getItem('docket_user') || sessionStorage.getItem('docket_auth_version') !== '2') {
            sessionStorage.removeItem('docket_user');
            window.location.replace('login.html');
            return;
        }
        document.getElementById('wallet-signout-button').addEventListener('click', GoogleAuth.signOut);
        try {
            await WalletController.load();
        } catch (error) {
            document.getElementById('wallet-content').innerHTML = '<div class="wallet-error"><i class="fa-solid fa-triangle-exclamation"></i><p>여행 정보를 불러오지 못했습니다.</p><small>백엔드 API 연결 상태를 확인해 주세요.</small></div>';
        }
    }
};

document.addEventListener('DOMContentLoaded', WalletController.init);
