const ThemeController = {
    storageKey: 'docket_theme',

    getTheme: () => localStorage.getItem(ThemeController.storageKey) || 'light',

    apply: (theme = ThemeController.getTheme()) => {
        const normalizedTheme = theme === 'dark' ? 'dark' : 'light';
        document.documentElement.dataset.theme = normalizedTheme;
        window.dispatchEvent(new CustomEvent('docket-theme-change', { detail: normalizedTheme }));
        document.querySelectorAll('[data-theme-choice]').forEach(button => {
            button.classList.toggle('is-selected', button.dataset.themeChoice === normalizedTheme);
        });
    },

    setTheme: (theme) => {
        localStorage.setItem(ThemeController.storageKey, theme);
        ThemeController.apply(theme);
    },

    bind: (container) => {
        container?.querySelectorAll('[data-theme-choice]').forEach(button => {
            button.addEventListener('click', () => ThemeController.setTheme(button.dataset.themeChoice));
        });
        ThemeController.apply();
    }
};

ThemeController.apply();
