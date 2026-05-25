/* global t, setLang, openWsPanel */

// ── Tab state ──────────────────────────────────────────────────
let _currentTab = 'favorites';
let _projects = [];
let _searchQuery = '';
// Session panel state
let _sessEncoded = '';
let _sessPath = '';
let _sessDisplayName = '';
let _sessRunningById = {};
// Message panel state
let _msgSessionId = '';
let _msgEncoded = '';
let _chatLoading = false;
// Live poll state
let _livePollTimer = null;
let _livePollActive = false;
let _liveLineCount = 0;
let _pendingTmuxText = null;
let _lastListScrollAt = 0;
let _suppressTapUntil = 0;

function _suppressTaps(ms = 450) {
  _suppressTapUntil = Date.now() + ms;
}

function _markListScrolled() {
  _lastListScrollAt = Date.now();
  _suppressTaps();
  _closeAllSwipeRows();
}

function _isListScrollCoolingDown() {
  return Date.now() - _lastListScrollAt < 300 || Date.now() < _suppressTapUntil;
}

function _closeAllSwipeRows() {
  document.querySelectorAll('.project-card.swiped, .project-card.swiped-single, .sess-item.swiped').forEach(el => {
    el.classList.remove('swiped', 'swiped-single');
    el.style.transform = '';
  });
  document.querySelectorAll('.project-swipe-wrap.swiped-open, .sess-swipe-wrap.swiped-open').forEach(el => {
    el.classList.remove('swiped-open');
  });
}

function _installNativePwaGuards() {
  const prevent = e => e.preventDefault();
  document.addEventListener('gesturestart', prevent, { passive: false });
  document.addEventListener('gesturechange', prevent, { passive: false });
  document.addEventListener('gestureend', prevent, { passive: false });
  document.addEventListener('touchmove', e => {
    if (e.touches && e.touches.length > 1) e.preventDefault();
  }, { passive: false });
  let lastTouchEnd = 0;
  document.addEventListener('touchend', e => {
    const now = Date.now();
    if (now - lastTouchEnd <= 300) e.preventDefault();
    lastTouchEnd = now;
  }, { passive: false });

  let startX = 0, startY = 0, moved = false;
  const start = (x, y) => { startX = x; startY = y; moved = false; };
  const move = (x, y) => {
    if (Math.abs(x - startX) > 8 || Math.abs(y - startY) > 8) moved = true;
  };
  const end = () => { if (moved) _suppressTaps(); };
  document.addEventListener('touchstart', e => {
    const t = e.touches && e.touches[0];
    if (t) start(t.clientX, t.clientY);
  }, { passive: true, capture: true });
  document.addEventListener('touchmove', e => {
    const t = e.touches && e.touches[0];
    if (t) move(t.clientX, t.clientY);
  }, { passive: true, capture: true });
  document.addEventListener('touchend', end, { passive: true, capture: true });
  document.addEventListener('mousedown', e => start(e.clientX, e.clientY), true);
  document.addEventListener('mousemove', e => move(e.clientX, e.clientY), true);
  document.addEventListener('mouseup', end, true);
}

function _syncAppViewportHeight() {
  const vv = window.visualViewport;
  const height = vv ? vv.height : window.innerHeight;
  const top = vv ? vv.offsetTop : 0;
  const keyboardOpen = vv ? vv.height < window.innerHeight - 80 : false;
  document.documentElement.style.setProperty('--app-height', `${height}px`);
  document.documentElement.style.setProperty('--app-top', `${top}px`);
  if (keyboardOpen) {
    document.documentElement.style.setProperty('--bottom-safe-active', '0px');
  } else {
    document.documentElement.style.removeProperty('--bottom-safe-active');
  }
  if (document.getElementById('msg-panel')?.classList.contains('open')) {
    _scrollMessagesToBottom(true);
  }
}

function _scrollMessagesToBottom(defer = false) {
  const run = () => {
    const list = document.getElementById('msg-list');
    if (list) list.scrollTop = list.scrollHeight;
  };
  if (!defer) { run(); return; }
  requestAnimationFrame(() => {
    run();
    setTimeout(run, 80);
    setTimeout(run, 260);
  });
}

function _applyMsgSessionState(sessionId, running) {
  const isRunning = !!running;
  _sessRunningById[sessionId] = isRunning;
  document.getElementById('msg-resume-btn').hidden = isRunning;
  document.getElementById('msg-input-bar').hidden = !isRunning;
  if (!isRunning) {
    document.getElementById('msg-input').value = '';
    _chatLoading = false;
  }
  _updateSendBtn();
}

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

// ── Workspace manage panel ─────────────────────────────────────
// eslint-disable-next-line no-unused-vars
async function openWsPanel() {
  const res = await fetch('/api/workspaces?all=1');
  const data = await res.json();
  const cfg = data.config;
  const html = data.workspaces.map(w => {
    const isPinned = cfg.pinned.includes(w.display_name);
    return `<div class="ws-item">
      <span class="ws-item-name">${escHTML(w.name)}</span>
      <div>
        <button class="tag-btn ${isPinned ? 'active-pin' : ''}"
          data-action="pin" data-name="${escAttr(w.display_name)}">${t('btn_pin')}</button>
      </div>
    </div>`;
  }).join('');
  document.getElementById('settings-list').innerHTML =
    html || `<div style="color:var(--sub)">${t('empty_no_ws')}</div>`;
  document.getElementById('settings-overlay').classList.add('show');
}

function closeWsPanel() {
  document.getElementById('settings-overlay').classList.remove('show');
  loadProjects();
}

// ── Modal + ws-panel wiring ────────────────────────────────────

document.getElementById('settings-list').addEventListener('click', async e => {
  const btn = e.target.closest('[data-action="pin"]');
  if (!btn) return;
  await post('/api/config/toggle', { key: 'pinned', name: btn.dataset.name });
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

// ── Favorites tab ──────────────────────────────────────────────
function renderFavorites() {
  const pinned = _projects.filter(p => p.pinned);
  const el = document.getElementById('main');
  if (!pinned.length) {
    el.innerHTML = `<div class="empty" style="white-space:pre-line">${t('empty_favorites')}</div>`;
    return;
  }
  el.innerHTML = pinned.map(p => favCardHTML(p)).join('');
  _bindFavSwipe(el);
}

function favCardHTML(p) {
  const enc  = escAttr(p.encoded);
  const path = escAttr(p.path || '');
  const disp = escAttr(p.display_name || p.encoded);
  const pathDisplay = p.path
    ? escHTML(p.path)
    : `<span style="color:var(--red);font-style:italic">路径不存在</span>`;
  const age = _formatAge(p.last_mtime);
  const countClass = p.running ? 'session-count-badge running' : 'session-count-badge';
  return `<div class="project-swipe-wrap" data-encoded="${enc}">
    <button class="project-unpin-btn" data-encoded="${enc}">${t('btn_unfavorite')}</button>
    <div class="card project-card" data-encoded="${enc}" data-path="${path}" data-display="${disp}">
      <div class="card-left">
        <div class="card-name">${escHTML(p.display_name || '')}</div>
        <div class="card-path">${pathDisplay}</div>
        <div class="card-meta">${t('section_recent').includes('天') ? '最近：' : 'Last: '}${age}</div>
      </div>
      <div class="card-right">
        <span class="${countClass}">${p.session_count}</span>
        <span class="card-chevron">›</span>
      </div>
    </div>
  </div>`;
}

function _bindFavSwipe(container) {
  let swipedWrap = null;

  function closeSwipe() {
    if (swipedWrap) {
      swipedWrap.querySelector('.project-card').classList.remove('swiped-single');
      swipedWrap.classList.remove('swiped-open');
      swipedWrap = null;
    }
  }

  container.querySelectorAll('.project-swipe-wrap').forEach(wrap => {
    const card = wrap.querySelector('.project-card');
    const unpinBtn = wrap.querySelector('.project-unpin-btn');
    let startX = 0, startY = 0, dragging = false, moved = false, lockDir = null;

    card.addEventListener('touchstart', e => {
      startX = e.touches[0].clientX;
      startY = e.touches[0].clientY;
      dragging = true; moved = false; lockDir = null;
    }, { passive: true });

    card.addEventListener('touchmove', e => {
      if (!dragging) return;
      const dx = e.touches[0].clientX - startX;
      const dy = e.touches[0].clientY - startY;
      const absX = Math.abs(dx), absY = Math.abs(dy);
      moved = absX > 4 || absY > 4;
      if (!lockDir && (absX > 5 || absY > 5)) lockDir = absX >= absY ? 'h' : 'v';
      if (lockDir === 'v') { _closeAllSwipeRows(); return; }
      if (lockDir === 'h') e.preventDefault();
    }, { passive: false });

    card.addEventListener('touchend', e => {
      if (!dragging) return;
      dragging = false;
      const dx = e.changedTouches[0].clientX - startX;
      const dy = e.changedTouches[0].clientY - startY;
      if (lockDir === 'h' && dx < -40) {
        if (swipedWrap && swipedWrap !== wrap) closeSwipe();
        card.classList.add('swiped-single');
        wrap.classList.add('swiped-open');
        swipedWrap = wrap;
      } else {
        card.classList.remove('swiped-single');
        wrap.classList.remove('swiped-open');
        if (swipedWrap === wrap) swipedWrap = null;
        if (!_isListScrollCoolingDown() && (!moved || (Math.abs(dx) < 5 && Math.abs(dy) < 5))) {
          openSessPanel(card.dataset.encoded, card.dataset.path, card.dataset.display);
        }
      }
    }, { passive: true });

    card.addEventListener('click', () => {
      if (_isListScrollCoolingDown()) return;
      if (card.classList.contains('swiped-single')) { closeSwipe(); return; }
      openSessPanel(card.dataset.encoded, card.dataset.path, card.dataset.display);
    });

    unpinBtn.addEventListener('click', async () => {
      const encoded = card.dataset.encoded;
      const proj = _projects.find(p => p.encoded === encoded);
      if (!proj) return;
      await post('/api/config/toggle', { key: 'pinned', name: proj.display_name });
      proj.pinned = false;
      renderFavorites();
      if (_currentTab === 'all') renderProjects();
      showToast(t('btn_unfavorite'), 'info');
    });
  });

  container.addEventListener('touchstart', e => {
    if (swipedWrap && !swipedWrap.contains(e.target)) closeSwipe();
  }, { passive: true });
}

// ── Tab switching ──────────────────────────────────────────────
function switchTab(tab) {
  _currentTab = tab;
  document.getElementById('main').style.display = tab === 'favorites' ? '' : 'none';
  document.getElementById('projects-view').style.display = tab === 'all' ? '' : 'none';
  document.querySelectorAll('.tab-item').forEach(el => {
    el.classList.toggle('active', el.dataset.tab === tab);
  });
  if (tab === 'favorites') renderFavorites();
  if (tab === 'all') {
    if (_projects.length === 0) loadProjects();
    else renderProjects();
  }
}

document.querySelectorAll('.tab-item').forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

// ── Projects (All tab) ─────────────────────────────────────────
async function loadProjects() {
  try {
    const res = await fetch('/api/projects');
    const data = await res.json();
    _projects = data.projects;
    if (_currentTab === 'favorites') renderFavorites();
    if (_currentTab === 'all') renderProjects();
  } catch { /* ignore */ }
}

function renderProjects() {
  const el = document.getElementById('projects-list');
  const q = _searchQuery.trim().toLowerCase();
  let list = _projects;

  if (q) {
    list = list.filter(p => {
      const hay = ((p.path || '') + ' ' + (p.display_name || '')).toLowerCase();
      return hay.includes(q);
    });
  }

  if (!list.length) {
    el.innerHTML = `<div class="empty">${q ? t('search_results') + ': 0' : t('empty_no_ws')}</div>`;
    return;
  }

  let html = '';
  if (q) {
    html += `<div class="section-label">${t('search_results')} · ${list.length}</div>`;
    html += list.map(p => projectCardHTML(p, q)).join('');
  } else {
    const recent = list.filter(p => p.recent);
    const older  = list.filter(p => !p.recent);
    if (recent.length) {
      html += `<div class="section-label">${t('section_recent')}</div>`;
      html += recent.map(p => projectCardHTML(p, '')).join('');
    }
    if (older.length) {
      html += `<div class="section-label">${t('section_older')}</div>`;
      html += older.map(p => projectCardHTML(p, '')).join('');
    }
  }
  el.innerHTML = html;

  _bindProjectSwipe(el);
}

function _bindProjectSwipe(container) {
  let swipedWrap = null;

  function closeSwipe() {
    if (swipedWrap) {
      swipedWrap.querySelector('.project-card').classList.remove('swiped');
      swipedWrap.classList.remove('swiped-open');
      swipedWrap = null;
    }
  }

  container.querySelectorAll('.project-swipe-wrap').forEach(wrap => {
    const card = wrap.querySelector('.project-card');
    const delBtn = wrap.querySelector('.project-del-btn');
    const pinBtn = wrap.querySelector('.project-pin-btn');
    let startX = 0, startY = 0, dragging = false, moved = false, lockDir = null;

    card.addEventListener('touchstart', e => {
      startX = e.touches[0].clientX;
      startY = e.touches[0].clientY;
      dragging = true; moved = false; lockDir = null;
    }, { passive: true });

    card.addEventListener('touchmove', e => {
      if (!dragging) return;
      const dx = e.touches[0].clientX - startX;
      const dy = e.touches[0].clientY - startY;
      const absX = Math.abs(dx), absY = Math.abs(dy);
      moved = absX > 4 || absY > 4;
      if (!lockDir && (absX > 5 || absY > 5)) lockDir = absX >= absY ? 'h' : 'v';
      if (lockDir === 'v') { _closeAllSwipeRows(); return; }
      if (lockDir === 'h') e.preventDefault();
    }, { passive: false });

    card.addEventListener('touchend', e => {
      if (!dragging) return;
      dragging = false;
      const dx = e.changedTouches[0].clientX - startX;
      const dy = e.changedTouches[0].clientY - startY;
      if (lockDir === 'h' && dx < -40) {
        if (swipedWrap && swipedWrap !== wrap) closeSwipe();
        card.classList.add('swiped');
        wrap.classList.add('swiped-open');
        swipedWrap = wrap;
      } else {
        card.classList.remove('swiped');
        wrap.classList.remove('swiped-open');
        if (swipedWrap === wrap) swipedWrap = null;
        if (!_isListScrollCoolingDown() && (!moved || (Math.abs(dx) < 5 && Math.abs(dy) < 5))) {
          openSessPanel(card.dataset.encoded, card.dataset.path, card.dataset.display);
        }
      }
    }, { passive: true });

    card.addEventListener('click', () => {
      if (_isListScrollCoolingDown()) return;
      if (card.classList.contains('swiped')) {
        closeSwipe();
        return;
      }
      openSessPanel(card.dataset.encoded, card.dataset.path, card.dataset.display);
    });

    delBtn.addEventListener('click', () => _deleteProjectLogs(wrap, card.dataset.encoded));

    pinBtn.addEventListener('click', async () => {
      const encoded = card.dataset.encoded;
      const proj = _projects.find(p => p.encoded === encoded);
      if (!proj) return;
      await post('/api/config/toggle', { key: 'pinned', name: proj.display_name });
      proj.pinned = !proj.pinned;
      if (_currentTab === 'all') renderProjects();
      renderFavorites();
      showToast(proj.pinned ? t('btn_favorite') : t('btn_unfavorite'), 'info');
    });
  });

  container.addEventListener('touchstart', e => {
    if (swipedWrap && !swipedWrap.contains(e.target)) closeSwipe();
  }, { passive: true });
}

async function _deleteProjectLogs(wrap, encoded) {
  const card = wrap.querySelector('.project-card');
  card.classList.add('deleting');
  try {
    const res = await fetch('/api/projects/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ encoded }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    _projects = _projects.filter(p => p.encoded !== encoded);
    renderProjects();
    showToast('日志已删除', 'info');
  } catch (e) {
    card.classList.remove('deleting', 'swiped');
    wrap.classList.remove('swiped-open');
    showToast(e.message === 'project_running' ? '运行中的会话不能删除日志' : '删除失败', 'warn');
  }
}

function projectCardHTML(p, q) {
  const enc  = escAttr(p.encoded);
  const path = escAttr(p.path || '');
  const disp = escAttr(p.display_name || p.encoded);
  const pathDisplay = p.path
    ? escHTML(p.path)
    : `<span style="color:var(--red);font-style:italic">路径不存在</span>`;
  const nameDisplay = q
    ? escHTML(p.display_name || '').replace(
        new RegExp(escRegex(q), 'gi'),
        m => `<span style="color:var(--accent);font-weight:600">${m}</span>`
      )
    : escHTML(p.display_name || '');
  const pathHl = q && p.path
    ? escHTML(p.path).replace(
        new RegExp(escRegex(q), 'gi'),
        m => `<span style="color:var(--accent);font-weight:600">${m}</span>`
      )
    : pathDisplay;
  const age = _formatAge(p.last_mtime);
  const countClass = p.running ? 'session-count-badge running' : 'session-count-badge';
  return `<div class="project-swipe-wrap">
    <div class="project-swipe-actions">
      <button class="project-pin-btn" data-encoded="${enc}">${p.pinned ? '✓ ' + t('btn_favorite') : t('btn_favorite')}</button>
      <button class="project-del-btn" data-encoded="${enc}">删除</button>
    </div>
    <div class="card project-card" data-encoded="${enc}" data-path="${path}" data-display="${disp}">
      <div class="card-left">
        <div class="card-name">${nameDisplay}</div>
        <div class="card-path">${pathHl}</div>
        <div class="card-meta">${t('section_recent').includes('天') ? '最近：' : 'Last: '}${age}</div>
      </div>
      <div class="card-right">
        <span class="${countClass}">${p.session_count}</span>
        <span class="card-chevron">›</span>
      </div>
    </div>
  </div>`;
}

function _formatAge(mtime) {
  const diff = (Date.now() / 1000) - mtime;
  if (diff < 60)     return '刚刚';
  if (diff < 3600)   return Math.floor(diff / 60) + ' 分钟前';
  if (diff < 86400)  return '今天 ' + new Date(mtime * 1000).toLocaleTimeString('zh', {hour:'2-digit', minute:'2-digit'});
  if (diff < 172800) return '昨天 ' + new Date(mtime * 1000).toLocaleTimeString('zh', {hour:'2-digit', minute:'2-digit'});
  return new Date(mtime * 1000).toLocaleDateString('zh', {month:'numeric', day:'numeric'});
}

// Search
document.getElementById('project-search').addEventListener('input', e => {
  _searchQuery = e.target.value;
  document.getElementById('search-clear-btn').classList.toggle('show', !!_searchQuery);
  renderProjects();
});
document.getElementById('search-clear-btn').addEventListener('click', () => {
  _searchQuery = '';
  document.getElementById('project-search').value = '';
  document.getElementById('search-clear-btn').classList.remove('show');
  renderProjects();
});
document.getElementById('main').addEventListener('scroll', _markListScrolled, { passive: true });
document.getElementById('projects-view').addEventListener('scroll', _markListScrolled, { passive: true });

// ── Session panel ──────────────────────────────────────────────
async function openSessPanel(encoded, path, displayName) {
  _sessEncoded = encoded;
  _sessPath = path;
  _sessDisplayName = displayName;

  document.getElementById('sess-title').textContent = displayName;
  document.getElementById('sess-path').textContent = path || '路径不存在';
  document.getElementById('sess-list').innerHTML = `<div class="empty">${t('empty_loading')}</div>`;
  document.getElementById('sess-panel').classList.add('open');

  try {
    const res = await fetch(`/api/projects/sessions?encoded=${encodeURIComponent(encoded)}`);
    const data = await res.json();
    renderSessList(data.sessions, path, displayName);
  } catch {
    document.getElementById('sess-list').innerHTML = `<div class="empty">加载失败</div>`;
  }
}

function renderSessList(sessions, path, displayName) {
  let countEl = `<div class="section-label" style="margin-top:10px" id="sess-count-label">${sessions.length} ${t('sessions_label')}</div>`;
  _sessRunningById = {};

  const itemsHtml = sessions.map(s => {
    const isLive = s.running;
    _sessRunningById[s.id] = isLive;
    const dateStr = _formatAge(s.mtime);
    const sizeStr = _formatSize(s.size);
    const title = s.title || '未命名会话';
    return `<div class="sess-swipe-wrap" data-id="${escAttr(s.id)}">
      <div class="sess-del-btn" data-id="${escAttr(s.id)}">删除</div>
      <div class="sess-item${isLive ? ' live' : ''}" data-id="${escAttr(s.id)}">
        <div class="sess-header">
          <div class="sess-title">${escHTML(title)}</div>
          <div class="sess-meta">
            ${isLive ? `<span class="sess-live-dot">${t('sess_live')}</span>` : ''}
            <span class="sess-date">${dateStr}</span>
            <span class="sess-size">${sizeStr}</span>
          </div>
        </div>
        <div class="sess-preview">${escHTML(s.preview || '（无预览）')}</div>
        <div class="sess-footer">
          <span class="sess-tag ${isLive ? 'live' : 'view'}">${t('sess_view')}</span>
        </div>
      </div>
    </div>`;
  }).join('');

  const newCard = `<div class="new-sess-card" id="new-sess-card">
    <div class="new-sess-title">${t('sess_new_title')}</div>
    <div class="new-sess-hint">${t('sess_new_hint')}<br>
      ${t('sess_name_label')}<code>${escHTML(displayName)}</code>
    </div>
  </div>`;

  const el = document.getElementById('sess-list');
  el.innerHTML = countEl + itemsHtml + newCard;

  _bindSessSwipe(el);

  el.querySelector('#new-sess-card').addEventListener('click', () => {
    if (!path) { showToast(t('toast_path_missing'), 'warn'); return; }
    doStartByPath(path, null);
  });
}

function _bindSessSwipe(container) {
  let _swipedWrap = null;

  function _closeSwipe() {
    if (_swipedWrap) {
      _swipedWrap.querySelector('.sess-item').classList.remove('swiped');
      _swipedWrap.classList.remove('swiped-open');
      _swipedWrap = null;
    }
  }

  container.querySelectorAll('.sess-swipe-wrap').forEach(wrap => {
    const item = wrap.querySelector('.sess-item');
    const delBtn = wrap.querySelector('.sess-del-btn');
    const sid = wrap.dataset.id;
    let startX = 0, startY = 0, dragging = false, moved = false, lockDir = null;

    item.addEventListener('touchstart', e => {
      startX = e.touches[0].clientX;
      startY = e.touches[0].clientY;
      dragging = true; moved = false; lockDir = null;
    }, { passive: true });

    item.addEventListener('touchmove', e => {
      if (!dragging) return;
      const dx = e.touches[0].clientX - startX;
      const dy = e.touches[0].clientY - startY;
      const absX = Math.abs(dx), absY = Math.abs(dy);
      moved = absX > 4 || absY > 4;
      if (!lockDir && (absX > 5 || absY > 5)) lockDir = absX >= absY ? 'h' : 'v';
      if (lockDir === 'v') { _closeAllSwipeRows(); return; }
      if (lockDir === 'h') e.preventDefault();
    }, { passive: false });

    item.addEventListener('touchend', e => {
      if (!dragging) return;
      dragging = false;
      const dx = e.changedTouches[0].clientX - startX;
      const dy = e.changedTouches[0].clientY - startY;
      if (lockDir === 'h' && dx < -40) {
        if (_swipedWrap && _swipedWrap !== wrap) _closeSwipe();
        item.classList.add('swiped');
        wrap.classList.add('swiped-open');
        _swipedWrap = wrap;
      } else {
        item.classList.remove('swiped');
        wrap.classList.remove('swiped-open');
        if (_swipedWrap === wrap) _swipedWrap = null;
        if (!_isListScrollCoolingDown() && (!moved || (Math.abs(dx) < 5 && Math.abs(dy) < 5))) {
          openMsgPanel(sid);
        }
      }
    }, { passive: true });

    // Click on item (mouse / no-swipe tap)
    item.addEventListener('click', () => {
      if (_isListScrollCoolingDown()) return;
      if (item.classList.contains('swiped')) {
        _closeSwipe(); return;
      }
      openMsgPanel(sid);
    });

    delBtn.addEventListener('click', async () => {
      _doDeleteSession(wrap, sid, container);
    });
  });

  // Tap elsewhere to close swipe
  container.addEventListener('touchstart', e => {
    if (_swipedWrap && !_swipedWrap.contains(e.target)) _closeSwipe();
  }, { passive: true });
}

async function _doDeleteSession(wrap, sessionId, container) {
  // Animate out
  const item = wrap.querySelector('.sess-item');
  item.classList.add('deleting');
  await new Promise(r => setTimeout(r, 220));

  // Collapse height
  wrap.style.transition = 'height .2s ease, opacity .2s ease, margin .2s ease';
  wrap.style.overflow = 'hidden';
  wrap.style.height = wrap.offsetHeight + 'px';
  requestAnimationFrame(() => {
    wrap.style.height = '0';
    wrap.style.opacity = '0';
    wrap.style.marginBottom = '0';
  });
  await new Promise(r => setTimeout(r, 220));

  wrap.remove();

  // Update count label
  const remaining = container.querySelectorAll('.sess-swipe-wrap').length;
  const lbl = container.querySelector('#sess-count-label');
  if (lbl) lbl.textContent = `${remaining} ${t('sessions_label')}`;

  // Delete on server
  try {
    await post('/api/sessions/delete', { encoded: _sessEncoded, session_id: sessionId });
    showToast('已删除', 'info');
  } catch {
    showToast('删除失败', 'warn');
  }
}

function _formatSize(bytes) {
  if (bytes < 1024)       return bytes + ' B';
  if (bytes < 1048576)    return (bytes / 1024).toFixed(0) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}

document.getElementById('sess-back').addEventListener('click', () => {
  document.getElementById('sess-panel').classList.remove('open');
});
document.getElementById('sess-panel').addEventListener('scroll', _markListScrolled, { passive: true });
document.getElementById('sess-new-btn').addEventListener('click', () => {
  if (!_sessPath) { showToast(t('toast_path_missing'), 'warn'); return; }
  doStartByPath(_sessPath, null);
});

// ── Message panel ──────────────────────────────────────────────
async function openMsgPanel(sessionId) {
  stopLivePoll();
  _msgSessionId = sessionId;
  _msgEncoded   = _sessEncoded;
  _applyMsgSessionState(sessionId, _sessRunningById[sessionId]);

  document.getElementById('msg-title').textContent = _sessDisplayName;
  document.getElementById('msg-info').innerHTML = `<span>${t('empty_loading')}</span>`;
  document.getElementById('msg-list').innerHTML  = '';
  document.getElementById('msg-input').value = '';
  document.getElementById('msg-panel').classList.add('open');
  _chatLoading = false;
  _updateSendBtn();

  try {
    const url = `/api/sessions/messages?encoded=${encodeURIComponent(_msgEncoded)}&id=${encodeURIComponent(sessionId)}`;
    const res = await fetch(url);
    const data = await res.json();
    if (typeof data.running === 'boolean') {
      _applyMsgSessionState(sessionId, data.running);
    }
    renderMessages(data.messages, sessionId);
    _liveLineCount = data.line_count || 0;
    startLivePoll();
  } catch {
    document.getElementById('msg-list').innerHTML = `<div class="msg-empty">加载失败</div>`;
  }
}

function startLivePoll() {
  stopLivePoll();
  _livePollActive = true;
  _scheduleLivePoll();
}

function stopLivePoll() {
  _livePollActive = false;
  if (_livePollTimer) { clearTimeout(_livePollTimer); _livePollTimer = null; }
}

function _scheduleLivePoll() {
  _livePollTimer = setTimeout(_livePoll, 2000);
}

async function _livePoll() {
  if (!_livePollActive || !_msgSessionId || !_msgEncoded) return;
  try {
    const url = `/api/sessions/live?encoded=${encodeURIComponent(_msgEncoded)}&id=${encodeURIComponent(_msgSessionId)}&from=${_liveLineCount}`;
    const res = await fetch(url);
    const data = await res.json();
    if (data.messages && data.messages.length) {
      _appendLiveMessages(data.messages);
    }
    if (data.line_count > _liveLineCount) {
      _liveLineCount = data.line_count;
    }
  } catch {}
  if (_livePollActive) _scheduleLivePoll();
}

function _appendLiveMessages(messages) {
  const list = document.getElementById('msg-list');
  messages.forEach(m => {
    // Skip optimistically-shown user bubble (already rendered when we sent)
    if (m.role === 'user' && _pendingTmuxText !== null) {
      if (m.text && m.text.startsWith(_pendingTmuxText.slice(0, 60))) {
        _pendingTmuxText = null;
        return;
      }
    }

    // Assistant reply arrived — remove typing indicator and reset loading state
    if (m.role === 'assistant') {
      const typing = document.getElementById('msg-typing');
      if (typing) typing.remove();
      if (_chatLoading) {
        _chatLoading = false;
        _updateSendBtn();
      }
    }

    const div = document.createElement('div');
    if (m.role === 'user') {
      div.className = 'msg-user';
      div.innerHTML = `<div class="bubble md-bubble">${renderMd(m.text)}</div>`;
    } else {
      const toolsHtml = m.tools && m.tools.length
        ? `<div class="tool-chips">${m.tools.map(tool =>
            `<div class="tool-chip">
              <span class="tool-n">${escHTML(tool.name)}</span>
              ${tool.desc ? `<span class="tool-d">${escHTML(tool.desc)}</span>` : ''}
            </div>`
          ).join('')}</div>`
        : '';
      const textHtml = m.text
        ? `<div class="msg-ai"><div class="bubble md-bubble">${renderMd(m.text)}</div></div>`
        : '';
      div.innerHTML = toolsHtml + textHtml;
    }
    list.appendChild(div);
    _scrollMessagesToBottom();
  });
}

function renderMessages(messages, sessionId) {
  const shortId = sessionId.slice(0, 8);
  document.getElementById('msg-info').innerHTML =
    `<strong>${_sessDisplayName}</strong> · ${messages.length} 条消息 · <code style="font-size:11px;color:var(--sub)">${shortId}</code>`;

  if (!messages.length) {
    document.getElementById('msg-list').innerHTML = `<div class="msg-empty">${t('msg_empty')}</div>`;
    return;
  }

  let html = '';
  let lastDay = '';
  messages.forEach(m => {
    // Day separator (best-effort — ts field may be absent)
    if (m.ts) {
      const day = new Date(m.ts).toLocaleDateString('zh');
      if (day !== lastDay) {
        lastDay = day;
        html += `<div class="msg-date-sep"><span>${day}</span></div>`;
      }
    }

    if (m.role === 'user') {
      html += `<div class="msg-user">
        <div class="bubble md-bubble">${renderMd(m.text)}</div>
      </div>`;
    } else {
      const toolsHtml = m.tools && m.tools.length
        ? `<div class="tool-chips">${m.tools.map(tool =>
            `<div class="tool-chip">
              <span class="tool-n">${escHTML(tool.name)}</span>
              ${tool.desc ? `<span class="tool-d">${escHTML(tool.desc)}</span>` : ''}
            </div>`
          ).join('')}</div>`
        : '';
      const textHtml = m.text
        ? `<div class="msg-ai"><div class="bubble md-bubble">${renderMd(m.text)}</div></div>`
        : '';
      html += toolsHtml + textHtml;
    }
  });

  document.getElementById('msg-list').innerHTML = html;
  _scrollMessagesToBottom(true);
}

document.getElementById('msg-back').addEventListener('click', () => {
  stopLivePoll();
  document.getElementById('msg-panel').classList.remove('open');
});

// ── Chat input ─────────────────────────────────────────────────
function _updateSendBtn() {
  const btn = document.getElementById('msg-send-btn');
  const input = document.getElementById('msg-input');
  const hasText = input.value.trim().length > 0;
  btn.disabled = _chatLoading || !hasText;
  btn.textContent = _chatLoading ? '…' : '发送';
}

function _autoResizeInput() {
  const el = document.getElementById('msg-input');
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

document.getElementById('msg-input').addEventListener('input', () => {
  _autoResizeInput();
  _updateSendBtn();
  _scrollMessagesToBottom(true);
});
document.getElementById('msg-input').addEventListener('focus', () => {
  _syncAppViewportHeight();
  _scrollMessagesToBottom(true);
});
document.getElementById('msg-input').addEventListener('blur', () => {
  setTimeout(_syncAppViewportHeight, 120);
});

document.getElementById('msg-input').addEventListener('keydown', e => {
  if ((e.key === 'Enter') && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

document.getElementById('msg-send-btn').addEventListener('click', sendMessage);

async function sendMessage() {
  if (document.getElementById('msg-input-bar').hidden) return;
  const input = document.getElementById('msg-input');
  const text = input.value.trim();
  if (!text || _chatLoading) return;

  input.value = '';
  input.style.height = 'auto';
  _chatLoading = true;
  _updateSendBtn();

  const list = document.getElementById('msg-list');

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ encoded: _msgEncoded, session_id: _msgSessionId, message: text }),
    });
    const data = await res.json();

    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);

    // Message injected into terminal — show user bubble + typing indicator
    // Live poll will deliver the assistant reply when JSONL updates
    _pendingTmuxText = text;
    const userDiv = document.createElement('div');
    userDiv.className = 'msg-user';
    userDiv.innerHTML = `<div class="bubble md-bubble">${renderMd(text)}</div>`;
    list.appendChild(userDiv);

    const typingWrap = document.createElement('div');
    typingWrap.className = 'msg-ai';
    typingWrap.id = 'msg-typing';
    typingWrap.innerHTML = '<div class="bubble md-bubble"><span class="typing-indicator"><span></span><span></span><span></span></span></div>';
    list.appendChild(typingWrap);
    _scrollMessagesToBottom(true);

  } catch (e) {
    showToast('发送失败: ' + e.message, 'error');
    input.value = text;
    _autoResizeInput();
    _chatLoading = false;
    _updateSendBtn();
  }
}
document.getElementById('msg-resume-btn').addEventListener('click', async () => {
  if (!_sessPath) { showToast(t('toast_path_missing'), 'warn'); return; }
  document.getElementById('msg-panel').classList.remove('open');
  document.getElementById('sess-panel').classList.remove('open');
  switchTab('favorites');
  await doStartByPath(_sessPath, _msgSessionId, true);
  showToast(t('toast_resumed'), 'success');
});

// ── Path-based session start ───────────────────────────────────
async function doStartByPath(path, sessionId, quiet = false) {
  await post('/api/start', { path, session_id: sessionId, force_new: !sessionId });
  if (!quiet) showToast(t('toast_started'), 'success');
}

// ── Markdown renderer ──────────────────────────────────────────
function renderMd(raw) {
  if (!raw) return '';

  // 1. Extract code blocks before any escaping
  const blocks = [];
  let s = raw.replace(/```([^\n`]*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const i = blocks.length;
    const langClass = lang.trim() ? ` class="lang-${_esc(lang.trim())}"` : '';
    blocks.push(`<pre class="md-pre"><code${langClass}>${_esc(code.replace(/\n$/, ''))}</code></pre>`);
    return `\x00B${i}\x00`;
  });

  // 2. Escape remaining HTML
  s = s.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

  // 3. Inline code
  s = s.replace(/`([^`\n]+)`/g, '<code class="md-code">$1</code>');

  // 4. Bold + italic
  s = s.replace(/\*\*\*([^*\n]+)\*\*\*/g, '<strong><em>$1</em></strong>');
  s = s.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');

  // 5. Headers
  s = s.replace(/^#{3} (.+)$/gm, '<div class="md-h3">$1</div>');
  s = s.replace(/^#{2} (.+)$/gm, '<div class="md-h2">$1</div>');
  s = s.replace(/^# (.+)$/gm,    '<div class="md-h1">$1</div>');

  // 6. Tables
  s = s.replace(/((?:^\|.+\|\n?)+)/gm, block => {
    const rows = block.trim().split('\n').filter(r => r.trim());
    if (rows.length < 2) return block;
    const isSep = r => /^\|[-:| ]+\|$/.test(r.trim());
    let html = '<table class="md-table"><thead>';
    let inBody = false;
    rows.forEach(row => {
      if (isSep(row)) { html += '</thead><tbody>'; inBody = true; return; }
      const cells = row.trim().replace(/^\||\|$/g, '').split('|');
      const tag = !inBody ? 'th' : 'td';
      html += '<tr>' + cells.map(c => `<${tag}>${c.trim()}</${tag}>`).join('') + '</tr>';
    });
    html += inBody ? '</tbody>' : '</thead>';
    return html + '</table>';
  });

  // 6b. Lists (group consecutive items)
  s = s.replace(/((?:^[ \t]*[-*•] .+\n?)+)/gm, block => {
    const items = block.trim().split('\n')
      .map(l => `<li>${l.replace(/^[ \t]*[-*•] /, '')}</li>`).join('');
    return `<ul class="md-ul">${items}</ul>`;
  });
  s = s.replace(/((?:^\d+\. .+\n?)+)/gm, block => {
    const items = block.trim().split('\n')
      .map(l => `<li>${l.replace(/^\d+\. /, '')}</li>`).join('');
    return `<ol class="md-ol">${items}</ol>`;
  });

  // 7. Paragraphs / line breaks
  s = s.split(/\n{2,}/).map(para => {
    para = para.trim();
    if (!para) return '';
    if (/^<(div|ul|ol|pre|h[1-6])/.test(para)) return para;
    return `<p class="md-p">${para.replace(/\n/g, '<br>')}</p>`;
  }).join('');

  // 8. Restore code blocks
  s = s.replace(/\x00B(\d+)\x00/g, (_, i) => blocks[+i]);

  return s;
}

function _esc(s) {
  return String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}

// ── Helpers ────────────────────────────────────────────────────
function escRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// ── Boot ───────────────────────────────────────────────────────
_installNativePwaGuards();
_syncAppViewportHeight();
window.addEventListener('resize', _syncAppViewportHeight, { passive: true });
window.visualViewport?.addEventListener('resize', _syncAppViewportHeight, { passive: true });
window.visualViewport?.addEventListener('scroll', _syncAppViewportHeight, { passive: true });
checkNetwork();
loadProjects();
setInterval(loadProjects, 15000);
setInterval(checkNetwork, 20000);
