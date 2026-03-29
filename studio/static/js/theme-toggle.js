// Reeve 다크/라이트 모드 토글
(function () {
    const theme = localStorage.getItem('reeve-theme') || 'dark';
    document.documentElement.setAttribute('data-bs-theme', theme);

    document.addEventListener('DOMContentLoaded', () => {
        const btn = document.getElementById('themeToggle');
        if (!btn) return;
        const icon = btn.querySelector('i');
        if (icon) icon.className = theme === 'dark' ? 'bi bi-sun' : 'bi bi-moon-stars';

        btn.addEventListener('click', () => {
            const next = document.documentElement.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-bs-theme', next);
            localStorage.setItem('reeve-theme', next);
            if (icon) icon.className = next === 'dark' ? 'bi bi-sun' : 'bi bi-moon-stars';
        });
    });
})();
