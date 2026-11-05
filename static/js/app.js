(function () {
  // ---- Dark mode toggle (remembered per browser)
  const root = document.documentElement;
  const toggle = document.getElementById('themeToggle');
  const setTheme = (t) => {
    root.setAttribute('data-bs-theme', t);
    if (toggle) toggle.innerHTML = t === 'dark' ? '<i class="bi bi-sun"></i>' : '<i class="bi bi-moon-stars"></i>';
  };
  let saved = null;
  try { saved = localStorage.getItem('theme'); } catch (e) {}
  setTheme(saved || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
  toggle && toggle.addEventListener('click', () => {
    const next = root.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark';
    setTheme(next);
    try { localStorage.setItem('theme', next); } catch (e) {}
  });

  // ---- Paste button
  const pasteBtn = document.getElementById('pasteBtn');
  const urlInput = document.getElementById('urlInput');
  if (pasteBtn && urlInput) {
    pasteBtn.addEventListener('click', async () => {
      try {
        urlInput.value = (await navigator.clipboard.readText()).trim();
        document.getElementById('urlForm').submit();
      } catch (e) {
        urlInput.focus();
      }
    });
  }

  // ---- "Preparing your file" modal, hidden when the server sets the dl_token cookie
  const modalEl = document.getElementById('dlModal');
  if (modalEl) {
    const modal = new bootstrap.Modal(modalEl);
    document.querySelectorAll('.dl-btn').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const token = Math.random().toString(36).slice(2);
        const url = new URL(btn.href, location.href);
        url.searchParams.set('token', token);
        modal.show();
        const started = Date.now();
        const timer = setInterval(() => {
          if (document.cookie.includes('dl_token=' + token) || Date.now() - started > 10 * 60 * 1000) {
            clearInterval(timer);
            modal.hide();
          }
        }, 500);
        location.href = url.toString();
      });
    });
  }
})();
