const TicketSlider = {
    bind: (passElement, pass) => {
        const tickets = pass.tickets || [];
        if (tickets.length < 2) {
            passElement.querySelectorAll('.wallet-ticket-arrow, .wallet-ticket-dots').forEach(element => { element.hidden = true; });
            return;
        }

        const ticketView = passElement.querySelector('.wallet-ticket-view');
        const update = (index, direction = 1) => {
            const ticketIndex = (index + tickets.length) % tickets.length;
            const ticket = tickets[ticketIndex];
            const slideClass = direction < 0 ? 'ticket-slide-prev' : 'ticket-slide-next';
            ticketView.classList.remove('ticket-slide-prev', 'ticket-slide-next');
            void ticketView.offsetWidth;
            ticketView.classList.add(slideClass);
            window.setTimeout(() => {
                // 속성명을 복수로 참조하여 누락을 방지함
                passElement.querySelector('.wallet-ticket-code').textContent = ticket.code || ticket.qrCodeStr || '';
                passElement.querySelector('.wallet-ticket-label').textContent = ticket.label || `티켓 ${ticketIndex + 1}`;
            }, 160);
            window.setTimeout(() => ticketView.classList.remove(slideClass), 360);
            passElement.dataset.ticketIndex = ticketIndex;
            passElement.querySelectorAll('.wallet-ticket-dot').forEach((dot, dotIndex) => dot.classList.toggle('is-active', dotIndex === ticketIndex));
        };

        passElement.querySelector('.wallet-ticket-prev').addEventListener('click', () => update(Number(passElement.dataset.ticketIndex) - 1, -1));
        passElement.querySelector('.wallet-ticket-next').addEventListener('click', () => update(Number(passElement.dataset.ticketIndex) + 1, 1));
        passElement.querySelectorAll('.wallet-ticket-dot').forEach(dot => dot.addEventListener('click', () => {
            const targetIndex = Number(dot.dataset.ticketIndex);
            const currentIndex = Number(passElement.dataset.ticketIndex);
            update(targetIndex, targetIndex < currentIndex ? -1 : 1);
        }));

        let dragStartX = null;
        let dragPointerId = null;
        ticketView.addEventListener('pointerdown', event => {
            if (event.isPrimary === false) return;
            dragStartX = event.clientX;
            dragPointerId = event.pointerId;
            ticketView.setPointerCapture(event.pointerId);
        });
        ticketView.addEventListener('pointerup', event => {
            if (dragStartX === null || event.pointerId !== dragPointerId) return;
            const dragDistance = event.clientX - dragStartX;
            if (Math.abs(dragDistance) >= 40) update(Number(passElement.dataset.ticketIndex) + (dragDistance < 0 ? 1 : -1), dragDistance < 0 ? 1 : -1);
            dragStartX = null;
            if (ticketView.hasPointerCapture(event.pointerId)) ticketView.releasePointerCapture(event.pointerId);
            dragPointerId = null;
        });
        ticketView.addEventListener('pointercancel', event => {
            if (event.pointerId === dragPointerId) {
                dragStartX = null;
                dragPointerId = null;
            }
        });
        ticketView.addEventListener('lostpointercapture', event => {
            if (event.pointerId === dragPointerId) {
                dragStartX = null;
                dragPointerId = null;
            }
        });
    }
};