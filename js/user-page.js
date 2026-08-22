document.addEventListener('DOMContentLoaded', () => {
    let user;
    try {
        user = JSON.parse(sessionStorage.getItem('docket_user'));
    } catch (error) {
        user = null;
    }

    if (!user || sessionStorage.getItem('docket_auth_version') !== '2') {
        sessionStorage.removeItem('docket_user');
        window.location.replace('login.html');
        return;
    }

    const displayName = user.name || user.email || 'Google 사용자';
    const email = user.email || '이메일 정보 없음';
    const initial = displayName.charAt(0).toUpperCase();
    document.getElementById('user-profile-content').innerHTML = `
        <div class="user-profile-summary">
            <div class="user-profile-avatar">${initial}</div>
            <div>
                <h2>${displayName}</h2>
                <p>${email}</p>
            </div>
        </div>
        <div class="theme-setting"><span>화면 테마</span><div class="theme-options"><button type="button" data-theme-choice="light"><i class="fa-solid fa-sun"></i> 라이트</button><button type="button" data-theme-choice="dark"><i class="fa-solid fa-moon"></i> 다크</button></div></div>
        <dl class="user-detail-list">
            <div><dt>로그인 방식</dt><dd>Google 계정</dd></div>
            <div><dt>서비스 이용 상태</dt><dd class="user-status">이용 중</dd></div>
        </dl>
        <button id="user-signout-button" class="user-signout-button" type="button">로그아웃</button>
    `;
    ThemeController.bind(document.getElementById('user-profile-content'));

    document.getElementById('user-signout-button').addEventListener('click', () => {
        sessionStorage.removeItem('docket_user');
        window.location.replace('login.html');
    });
});
