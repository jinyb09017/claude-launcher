/* global t, setLang, openWsPanel */
let workspaces = [];
let activeName = null;
const loadingCards = new Set();

// ── Network detection ──────────────────────────────────────────
const netState = { lan: true, inet: true };

async function checkNetwork() {
  let lanOk = false;
  try {
    const r = await fetch('/api/health', { signal: AbortSignal.timeout(3000) });
    const d = await r.json();
    lanOk = true;
    netState.inet = d.internet;
  } catch {
    lanOk = false;
  }
  netState.lan = lanOk;
  updateNetUI();
}

function updateNetUI() {
  const pill      = document.getElementById('net-pill');
  const pillText  = document.getElementById('net-pill-text');
  const banner    = document.getElementById('net-banner');
  const bannerMsg = document.getElementById('net-banner-msg');

  if (!netState.lan) {
    pill.className = 'net-pill bad';
    pillText.textContent = t('net_bad');
    banner.className = 'net-banner show lan-down';
    bannerMsg.textContent = t('net_banner_lan_down');
    return;
  }
  if (!netState.inet) {
    pill.className = 'net-pill warn';
    pillText.textContent = t('net_warn');
    banner.className = 'net-banner show inet-warn';
    bannerMsg.textContent = t('net_banner_inet_warn');
    return;
  }
  pill.className = 'net-pill ok';
  pillText.textContent = t('net_ok');
  banner.className = 'net-banner';
}

window.addEventListener('offline', () => {
  netState.lan = false; updateNetUI();
  showToast(t('toast_net_offline'), 'warn');
});
window.addEventListener('online', () => {
  checkNetwork();
  showToast(t('toast_net_restored'), 'info');
});

// ── Data ───────────────────────────────────────────────────────
async function load() {
  try {
    const res = await fetch('/api/workspaces');
    const data = await res.json();
    workspaces = data.workspaces;
    document.getElementById('ip-hint').textContent =
      `${t('header_subtitle')} · ${data.ip}:${data.port}`;
    render();
  } catch {
    netState.lan = false; updateNetUI();
  }
}

// ── Render ─────────────────────────────────────────────────────
function render() {
  const pinned = workspaces.filter(w => w.pinned);
  const rest   = workspaces.filter(w => !w.pinned);
  let html = '';

  if (!workspaces.length) {
    document.getElementById('main').innerHTML =
      `<div class="empty">${t('empty_no_ws')}<br><small>${t('empty_no_ws_hint')}</small></div>`;
    return;
  }

  const anyRunning = workspaces.some(w => w.running);
  if (!anyRunning) {
    html += `<div class="guide">
      <strong>${t('guide_title')}</strong>
      <ol>
        <li>${t('guide_step1')}</li>
        <li>${t('guide_step2')}</li>
        <li>${t('guide_step3')}</li>
      </ol>
    </div>`;
  }

  if (pinned.length) {
    html += `<div class="section-label">${t('section_pinned')}</div>`;
    html += pinned.map(cardHTML).join('');
  }
  if (rest.length) {
    html += `<div class="section-label">${pinned.length ? t('section_other') : t('section_all')}</div>`;
    html += rest.map(cardHTML).join('');
  }

  document.getElementById('main').innerHTML = html;
  document.querySelectorAll('.stop-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      doStop(btn.dataset.name);
    });
  });
}

function cardHTML(w) {
  const loading   = loadingCards.has(w.name);
  const dotClass  = loading ? 'spinning' : (w.running ? 'on' : 'off');
  const cardClass = loading ? 'loading'  : (w.running ? 'running' : '');
  const ne = escAttr(w.name), nh = escHTML(w.name);
  return `<div class="card ${cardClass}" data-name="${ne}">
    <div class="card-left">
      <div class="card-name">${nh}</div>
      <div class="card-path">${escHTML(w.short_path)}</div>
    </div>
    <div class="card-right">
      <button class="stop-btn" data-name="${ne}">${t('btn_stop')}</button>
      <div class="status-dot ${dotClass}"></div>
    </div>
  </div>`;
}

document.getElementById('main').addEventListener('click', e => {
  const card = e.target.closest('.card');
  if (!card || card.classList.contains('loading')) return;
  const name = card.dataset.name;
  if (name) tap(name);
});

// ── Actions ────────────────────────────────────────────────────
function tap(name) {
  activeName = name;
  const ws = workspaces.find(w => w.name === name);
  if (!ws) return;
  if (ws.running) {
    document.getElementById('modal-title').textContent = ws.name;
    document.getElementById('modal-desc').textContent = t('modal_running_desc');
    document.getElementById('modal').classList.add('show');
  } else {
    doStart(name, false);
  }
}

function closeModal() {
  document.getElementById('modal').classList.remove('show');
  activeName = null;
}

async function doReuse() {
  closeModal();
  showToast(t('toast_reuse'), 'info');
}

async function doNew() {
  const name = activeName;
  closeModal();
  setLoading(name, true);
  await post('/api/start', { name, force_new: true });
  waitForSession(name);
}

async function doStart(name, force_new) {
  setLoading(name, true);
  await post('/api/start', { name, force_new });
  waitForSession(name);
}

async function doStop(name) {
  setLoading(name, true);
  await post('/api/stop', { name });
  setTimeout(() => { setLoading(name, false); load(); }, 700);
  showToast(`${t('toast_stopped')} ${name}`, 'info');
}

function waitForSession(name) {
  let attempts = 0;
  const poll = setInterval(async () => {
    attempts++;
    try {
      const res = await fetch('/api/workspaces');
      const data = await res.json();
      const ws = data.workspaces.find(w => w.name === name);
      if ((ws && ws.running) || attempts >= 10) {
        clearInterval(poll);
        setLoading(name, false);
        workspaces = data.workspaces;
        render();
        if (ws && ws.running)
          showToast(`✓ ${name} ${t('toast_started')}`, 'success');
      }
    } catch { clearInterval(poll); setLoading(name, false); }
  }, 1000);
}

function setLoading(name, val) {
  if (val) loadingCards.add(name); else loadingCards.delete(name);
  render();
}

// ── Workspace manage panel ─────────────────────────────────────
// eslint-disable-next-line no-unused-vars
async function openWsPanel() {
  const res = await fetch('/api/workspaces?all=1');
  const data = await res.json();
  const cfg = data.config;
  const html = data.workspaces.map(w => {
    const isHidden = w.is_hidden;
    const isPinned = cfg.pinned.includes(w.name);
    return `<div class="ws-item ${isHidden ? 'hidden-item' : ''}">
      <span class="ws-item-name">${escHTML(w.name)}</span>
      <div>
        <button class="tag-btn ${isPinned ? 'active-pin' : ''}"
          data-action="pin" data-name="${escAttr(w.name)}">${t('btn_pin')}</button>
        <button class="tag-btn ${isHidden ? 'active-hide' : ''}"
          data-action="hide" data-name="${escAttr(w.name)}">${t('btn_hide')}</button>
      </div>
    </div>`;
  }).join('');
  document.getElementById('settings-list').innerHTML =
    html || `<div style="color:var(--sub)">${t('empty_no_ws')}</div>`;
  document.getElementById('settings-overlay').classList.add('show');
}

function closeWsPanel() {
  document.getElementById('settings-overlay').classList.remove('show');
  load();
}

// ── Modal + ws-panel wiring ────────────────────────────────────
document.getElementById('btn-reuse').addEventListener('click', doReuse);
document.getElementById('btn-new').addEventListener('click', doNew);
document.getElementById('btn-cancel-modal').addEventListener('click', closeModal);
document.getElementById('modal').addEventListener('click',
  e => { if (e.target.id === 'modal') closeModal(); });

document.getElementById('settings-list').addEventListener('click', async e => {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  await post('/api/config/toggle', {
    key: btn.dataset.action === 'pin' ? 'pinned' : 'hidden',
    name: btn.dataset.name,
  });
  openWsPanel();
});

document.getElementById('btn-close-settings').addEventListener('click', closeWsPanel);
document.getElementById('settings-overlay').addEventListener('click',
  e => { if (e.target.id === 'settings-overlay') closeWsPanel(); });

// ── Utils ──────────────────────────────────────────────────────
async function post(url, body) {
  return fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

// eslint-disable-next-line no-unused-vars
function showToast(msg, type = '') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast show' + (type ? ' ' + type : '');
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove('show'), 3200);
}

function escHTML(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function escAttr(s) {
  return String(s).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ── Boot ───────────────────────────────────────────────────────
checkNetwork();
load();
setInterval(load, 15000);
setInterval(checkNetwork, 20000);
