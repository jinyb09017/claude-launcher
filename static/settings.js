/* global t, setLang, _lang, load, openWsPanel, showToast */

let _requireMd = true;
let _scanDir = '';

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
// eslint-disable-next-line no-unused-vars
function renderSheet() {
  const sheet = document.getElementById('settings-sheet');
  if (!sheet) return;

  const scanDisplay = _scanDir.replace(/^\/Users\/[^/]+/, '~') || '—';

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

    <div class="sheet-section-label">${t('settings_workspace_section')}</div>
    <div class="sheet-group">
      <div class="sheet-row" id="row-scan-dir">
        <span class="sheet-icon">📁</span>
        <span class="sheet-label">${t('settings_scan_dir')}</span>
        <span class="sheet-value">${escSafe(scanDisplay)}</span>
        <span class="sheet-chevron">›</span>
      </div>
      <div class="sheet-row" id="row-manage-ws">
        <span class="sheet-icon">📋</span>
        <span class="sheet-label">${t('settings_manage_ws')}</span>
        <span class="sheet-chevron">›</span>
      </div>
      <div class="sheet-row" style="cursor:default">
        <span class="sheet-icon">📄</span>
        <span class="sheet-label">${t('settings_require_md')}</span>
        <label class="toggle-wrap">
          <input type="checkbox" id="toggle-require-md"${_requireMd ? ' checked' : ''}>
          <div class="toggle-track"></div>
        </label>
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

  sheet.querySelector('#row-scan-dir').addEventListener('click', () => {
    // eslint-disable-next-line no-alert
    const val = prompt(t('settings_scan_dir'), _scanDir);
    if (val === null || val.trim() === _scanDir) return;
    saveScanDir(val.trim());
  });

  sheet.querySelector('#row-manage-ws').addEventListener('click', () => {
    openWsPanel();
  });

  sheet.querySelector('#toggle-require-md').addEventListener('change', e => {
    saveRequireMd(e.target.checked);
  });
}

async function loadSheetData() {
  try {
    const res = await fetch('/api/workspaces');
    const data = await res.json();
    _requireMd = data.config.require_claude_md !== false;
    _scanDir = data.config.scan_dir || '';
  } catch { /* ignore, use cached values */ }
}

async function saveScanDir(val) {
  if (!val) return;
  await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scan_dir: val }),
  });
  _scanDir = val;
  renderSheet();
  if (typeof load === 'function') load();
}

async function saveRequireMd(val) {
  _requireMd = val;
  await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ require_claude_md: val }),
  });
  if (typeof load === 'function') load();
}

// ── Open / close ───────────────────────────────────────────────
async function openSettings() {
  await loadSheetData();
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

// ── Helper ─────────────────────────────────────────────────────
function escSafe(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
