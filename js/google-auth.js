// Client ID는 js/config.local.js에서 읽습니다.
const GOOGLE_CLIENT_ID = window.GOOGLE_CLIENT_ID || '';

const GoogleAuth = {
    buttonContainer: null,
    userContainer: null,

    isLoginPage: () => window.location.pathname.endsWith('/login.html') || window.location.pathname.endsWith('login.html'),

    getStoredUser: () => {
        try {
            return JSON.parse(sessionStorage.getItem('docket_user'));
        } catch (error) {
            return null;
        }
    },

    showMessage: (message) => {
        GoogleAuth.buttonContainer.innerHTML = `<p class="google-auth-message">${message}</p>`;
    },

    decodeTokenPayload: (token) => {
        const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
        const binary = atob(base64);
        const bytes = Uint8Array.from(binary, character => character.charCodeAt(0));
        return JSON.parse(new TextDecoder().decode(bytes));
    },

    renderUser: (payload) => {
        const displayName = payload.name || payload.email || 'Google 사용자';
        const email = payload.email || '';

        sessionStorage.setItem('docket_user', JSON.stringify({ id: payload.sub || payload.email, name: displayName, email }));
        sessionStorage.setItem('docket_auth_version', '2');

        if (GoogleAuth.isLoginPage()) {
            window.location.replace('main.html');
            return;
        }

        GoogleAuth.buttonContainer.classList.add('hidden');
        GoogleAuth.userContainer.classList.remove('hidden');
        GoogleAuth.userContainer.innerHTML = `
            <div class="google-auth-user">
                <div class="google-auth-avatar">${displayName.charAt(0).toUpperCase()}</div>
                <div class="google-auth-user-info">
                    <strong>${displayName}</strong>
                    <span>${email}</span>
                </div>
                <button type="button" id="google-signout-button" class="google-auth-signout">로그아웃</button>
            </div>
        `;
        document.getElementById('google-signout-button').addEventListener('click', GoogleAuth.signOut);
    },

    renderSignedInUser: (credentialResponse) => {
        const payload = GoogleAuth.decodeTokenPayload(credentialResponse.credential);
        GoogleAuth.renderUser(payload);
    },

    signOut: () => {
        if (window.google?.accounts?.id) {
            window.google.accounts.id.disableAutoSelect();
        }
        sessionStorage.removeItem('docket_user');
        if (!GoogleAuth.isLoginPage()) {
            window.location.replace('login.html');
            return;
        }
        if (!GoogleAuth.buttonContainer || !GoogleAuth.userContainer) return;
        GoogleAuth.userContainer.classList.add('hidden');
        GoogleAuth.userContainer.innerHTML = '';
        GoogleAuth.buttonContainer.classList.remove('hidden');
        GoogleAuth.renderButton();
    },

    renderButton: () => {
        if (!window.google?.accounts?.id) return;
        window.google.accounts.id.renderButton(GoogleAuth.buttonContainer, {
            type: 'standard',
            theme: 'outline',
            size: 'medium',
            text: 'signin_with',
            shape: 'rectangular',
            logo_alignment: 'left'
        });
    },

    init: () => {
        GoogleAuth.buttonContainer = document.getElementById('google-login-button');
        GoogleAuth.userContainer = document.getElementById('google-user-container');
        if (!GoogleAuth.buttonContainer || !GoogleAuth.userContainer) return;

        const storedUser = GoogleAuth.getStoredUser();
        if (storedUser && !GoogleAuth.isLoginPage()) {
            GoogleAuth.renderUser(storedUser);
            return;
        }

        if (!GOOGLE_CLIENT_ID) {
            GoogleAuth.showMessage('Google Client ID를 설정하면 로그인할 수 있습니다.');
            return;
        }

        if (!window.google?.accounts?.id) {
            window.setTimeout(GoogleAuth.init, 300);
            return;
        }

        window.google.accounts.id.initialize({
            client_id: GOOGLE_CLIENT_ID,
            callback: GoogleAuth.renderSignedInUser,
            auto_select: false,
            cancel_on_tap_outside: true
        });
        GoogleAuth.renderButton();
    }
};

document.addEventListener('DOMContentLoaded', GoogleAuth.init);
