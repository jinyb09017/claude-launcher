/* global t, setLang, _lang, showToast */

// ── Theme ──────────────────────────────────────────────────────
let _theme = localStorage.getItem('launcher_theme') || 'dark';
const _mq = window.matchMedia('(prefers-color-scheme: dark)');

function applyTheme(mode) {
  _theme = mode;
  localStorage.setItem('launcher_theme', mode);
  _applyThemeToDOM();
}

function _applyThemeToDOM() {
  if (_theme === 'light') {
    document.documentElement.setAttribute('data-theme', 'light');
  } else if (_theme === 'dark') {
    document.documentElement.removeAttribute('data-theme');
  } else {
    // auto — follow system
    if (_mq.matches) {
      document.documentElement.removeAttribute('data-theme');
    } else {
      document.documentElement.setAttribute('data-theme', 'light');
    }
  }
}

_mq.addEventListener('change', () => {
  if (_theme === 'auto') _applyThemeToDOM();
});

// Apply theme before first paint
_applyThemeToDOM();

// ── Sheet render ───────────────────────────────────────────────
function renderSheet() {
  const sheet = document.getElementById('settings-sheet');
  if (!sheet) return;

  sheet.innerHTML = `
    <div class="sheet-handle"></div>

    <div class="sheet-section-label">${t('settings_appearance')}</div>
    <div class="sheet-group">
      <div class="sheet-row" style="cursor:default">
        <span class="sheet-icon">🌐</span>
        <span class="sheet-label">${t('settings_language')}</span>
        <div class="seg-ctrl" id="lang-seg">
          <button class="seg-item${_lang === 'zh' ? ' active' : ''}" data-lang="zh">中文</button>
          <button class="seg-item${_lang === 'en' ? ' active' : ''}" data-lang="en">EN</button>
        </div>
      </div>
      <div class="sheet-row" style="cursor:default">
        <span class="sheet-icon">🎨</span>
        <span class="sheet-label">${t('settings_theme')}</span>
        <div class="seg-ctrl" id="theme-seg">
          <button class="seg-item${_theme === 'light' ? ' active' : ''}" data-theme-val="light">${t('theme_light')}</button>
          <button class="seg-item${_theme === 'dark'  ? ' active' : ''}" data-theme-val="dark">${t('theme_dark')}</button>
          <button class="seg-item${_theme === 'auto'  ? ' active' : ''}" data-theme-val="auto">${t('theme_auto')}</button>
        </div>
      </div>
    </div>
  `;

  sheet.querySelector('#lang-seg').addEventListener('click', e => {
    const btn = e.target.closest('[data-lang]');
    if (!btn) return;
    setLang(btn.dataset.lang);
  });

  sheet.querySelector('#theme-seg').addEventListener('click', e => {
    const btn = e.target.closest('[data-theme-val]');
    if (!btn) return;
    applyTheme(btn.dataset.themeVal);
    renderSheet();
  });
}

// ── Open / close ───────────────────────────────────────────────
function openSettings() {
  renderSheet();
  document.getElementById('gear-btn').classList.add('active');
  document.getElementById('sheet-overlay').classList.add('show');
}

function closeSettings() {
  document.getElementById('sheet-overlay').classList.remove('show');
  document.getElementById('gear-btn').classList.remove('active');
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('gear-btn').addEventListener('click', openSettings);
  document.getElementById('sheet-overlay').addEventListener('click', e => {
    if (e.target.id === 'sheet-overlay') closeSettings();
  });
});

