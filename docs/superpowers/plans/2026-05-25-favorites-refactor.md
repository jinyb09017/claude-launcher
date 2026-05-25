# Favorites Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify favorites and all-projects under a single `_projects` data source, with pin/unpin in both tabs and a simplified manage panel.

**Architecture:** Backend injects `pinned` field into `/api/projects`; frontend favorites tab filters `_projects` by `pinned`, reusing `projectCardHTML`; all tab swipe exposes two actions (pin + delete); manage panel keeps only pin button.

**Tech Stack:** Python (backend), vanilla JS + HTML + CSS (frontend), no build step.

---

## Task 1: Backend — inject `pinned` into `/api/projects`

**Files:**
- Modify: `api.py:148-170`

- [ ] **Step 1: Add `pinned` field to each project in `_api_projects`**

In `api.py`, replace the `_api_projects` method body so it reads config and injects `pinned`:

```python
def _api_projects(self):
    with _lock:
        cfg = load_config()
    pinned_set = set(cfg.get('pinned', []))
    projects = scan_claude_projects()
    active_tmux = set(_load_session_map().values())
    from datetime import datetime
    now = datetime.now().timestamp()
    result = []
    for p in projects:
        path_base = _path_base(p['path']) if p['path'] else None
        running = bool(path_base and any(
            s == path_base or s.startswith(path_base + '_')
            for s in active_tmux
        ))
        age_days = (now - p['last_mtime']) / 86400
        result.append({
            'encoded': p['encoded'],
            'path': p['path'],
            'display_name': p['display_name'],
            'session_count': p['session_count'],
            'last_mtime': p['last_mtime'],
            'recent': age_days < 7,
            'running': running,
            'pinned': p['display_name'] in pinned_set,
        })
    self._send(200, "application/json", json.dumps({'projects': result}).encode())
```

- [ ] **Step 2: Verify backend response**

Start the server and check the response:

```bash
python3 server.py &
sleep 1
curl -s http://localhost:8765/api/projects | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['projects'][0].keys())"
kill %1
```

Expected output includes `pinned` in the keys list.

- [ ] **Step 3: Commit**

```bash
git add api.py
git commit -m "feat: inject pinned field into /api/projects response"
```

---

## Task 2: i18n — add new translation keys

**Files:**
- Modify: `static/i18n.js`

- [ ] **Step 1: Add keys to both `zh` and `en` translation objects**

In `static/i18n.js`, add the following keys to the `zh` block (after `btn_hide`):

```js
btn_unfavorite: '取消收藏',
btn_favorite: '收藏',
empty_favorites: '暂无收藏\n前往「全部」左滑项目即可收藏',
ws_panel_hint_new: '置顶收藏的项目，在收藏 tab 快速访问',
```

Add to the `en` block (after `btn_hide`):

```js
btn_unfavorite: 'Unpin',
btn_favorite: 'Pin',
empty_favorites: 'No favorites yet\nSwipe left on any project in All tab to pin',
ws_panel_hint_new: 'Pin projects to access them quickly in Favorites',
```

- [ ] **Step 2: Commit**

```bash
git add static/i18n.js
git commit -m "feat: add pin/unpin i18n keys"
```

---

## Task 3: CSS — update swipe styles for two-button all tab and favorites unpin button

**Files:**
- Modify: `static/app.css`

The all tab will now have two swipe buttons (pin + delete). Each button is 88px wide, total 176px. The card shifts `-176px`.

The favorites tab has one swipe button (unpin), same single-button style as existing delete.

- [ ] **Step 1: Replace the project swipe CSS block**

Find and replace the existing swipe block (lines ~133–154 in app.css). Replace:

```css
.project-swipe-wrap {
  position: relative; overflow: hidden;
  border-radius: var(--radius); margin-bottom: 9px;
}
.project-swipe-wrap .card { margin-bottom: 0; }
.project-del-btn {
  position: absolute; right: 0; top: 0; bottom: 0; width: 88px;
  border: none; background: var(--red); color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600; font-family: inherit;
  border-radius: 0 var(--radius) var(--radius) 0;
  opacity: 0; visibility: hidden; pointer-events: none;
}
.project-swipe-wrap.swiped-open .project-del-btn {
  opacity: 1; visibility: visible; pointer-events: auto;
}
.project-card {
  position: relative; will-change: transform;
  transition: border-color .15s, opacity .15s, transform .2s ease;
}
.project-card.swiped { transform: translateX(-88px); border-color: rgba(218,54,51,.45); }
.project-card.deleting { opacity: .45; cursor: wait; }
```

With:

```css
.project-swipe-wrap {
  position: relative; overflow: hidden;
  border-radius: var(--radius); margin-bottom: 9px;
}
.project-swipe-wrap .card { margin-bottom: 0; }

/* Two-button swipe area (all tab: pin + delete) */
.project-swipe-actions {
  position: absolute; right: 0; top: 0; bottom: 0; width: 176px;
  display: flex; opacity: 0; visibility: hidden; pointer-events: none;
}
.project-swipe-wrap.swiped-open .project-swipe-actions {
  opacity: 1; visibility: visible; pointer-events: auto;
}
.project-pin-btn {
  flex: 1; border: none; background: var(--accent); color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600; font-family: inherit;
}
.project-del-btn {
  flex: 1; border: none; background: var(--red); color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600; font-family: inherit;
  border-radius: 0 var(--radius) var(--radius) 0;
}
.project-card.swiped { transform: translateX(-176px); border-color: rgba(218,54,51,.45); }

/* Single-button swipe area (favorites tab: unpin) */
.project-unpin-btn {
  position: absolute; right: 0; top: 0; bottom: 0; width: 88px;
  border: none; background: var(--sub); color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600; font-family: inherit;
  border-radius: 0 var(--radius) var(--radius) 0;
  opacity: 0; visibility: hidden; pointer-events: none;
}
.project-swipe-wrap.swiped-open .project-unpin-btn {
  opacity: 1; visibility: visible; pointer-events: auto;
}
.project-card.swiped-single { transform: translateX(-88px); border-color: rgba(120,120,140,.45); }

.project-card {
  position: relative; will-change: transform;
  transition: border-color .15s, opacity .15s, transform .2s ease;
}
.project-card.deleting { opacity: .45; cursor: wait; }
```

- [ ] **Step 2: Also remove the `hidden-item` ws-item style** (hidden concept removed from manage panel)

Find in app.css:
```css
.ws-item.hidden-item .ws-item-name { color: var(--sub); text-decoration: line-through; }
```
Delete that line.

Find:
```css
.tag-btn.active-hide { border-color: var(--red); color: var(--red); }
```
Delete that line.

- [ ] **Step 3: Commit**

```bash
git add static/app.css
git commit -m "feat: update project swipe CSS for two-button (pin+delete) and single unpin"
```

---

## Task 4: app.js — favorites tab renders pinned projects

**Files:**
- Modify: `static/app.js`

This is the largest change. We'll work section by section.

### 4a: Remove old workspace globals and render functions

- [ ] **Step 1: Remove the `workspaces` and `loadingCards` globals and `render`/`load`/`cardHTML` functions**

At the top of `app.js`, remove line 2: `let workspaces = [];`
Remove line 4: `const loadingCards = new Set();`

Delete the entire `load()` function (lines ~180–191):
```js
async function load() { ... }
```

Delete the entire `render()` function (lines ~193–233):
```js
function render() { ... }
```

Delete the `cardHTML()` function (lines ~235–250):
```js
function cardHTML(w) { ... }
```

Delete the click handler on `#main` that calls `tap()` (lines ~252–258):
```js
document.getElementById('main').addEventListener('click', e => { ... tap(name) ... });
```

Delete the `tap()`, `closeModal()`, `doReuse()`, `doNew()`, `doStart()`, `doStop()`, `waitForSession()`, `setLoading()` functions (lines ~260–328).

Delete only the four modal-specific wiring lines (do NOT delete the settings-list/settings-overlay handlers — those are updated in Task 6):
```js
document.getElementById('btn-reuse').addEventListener('click', doReuse);
document.getElementById('btn-new').addEventListener('click', doNew);
document.getElementById('btn-cancel-modal').addEventListener('click', closeModal);
document.getElementById('modal').addEventListener('click',
  e => { if (e.target.id === 'modal') closeModal(); });
```

- [ ] **Step 2: Verify no syntax errors**

```bash
node --check static/app.js 2>&1
```

Expected: no output (no syntax errors).

### 4b: Add `loadFavorites` and `renderFavorites`

- [ ] **Step 3: Add favorites tab functions after the `// ── Tab switching` comment (around line 405)**

Insert before `function switchTab(tab)`:

```js
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
        <div class="card-meta">最近：${age}</div>
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
    let startX = 0, startY = 0, dragging = false, moved = false, swiping = false, verticalGesture = false;

    card.addEventListener('touchstart', e => {
      startX = e.touches[0].clientX;
      startY = e.touches[0].clientY;
      dragging = true; moved = false; swiping = false; verticalGesture = false;
    }, { passive: true });

    card.addEventListener('touchmove', e => {
      if (!dragging) return;
      const dx = e.touches[0].clientX - startX;
      const dy = e.touches[0].clientY - startY;
      moved = Math.abs(dx) > 4 || Math.abs(dy) > 4;
      if (Math.abs(dy) > 10) verticalGesture = true;
      if (verticalGesture) { _closeAllSwipeRows(); return; }
      if (!swiping && (dx >= 0 || Math.abs(dx) < 72 || Math.abs(dy) > 8)) return;
      swiping = true;
    }, { passive: true });

    card.addEventListener('touchend', e => {
      if (!dragging) return;
      dragging = false;
      const dx = e.changedTouches[0].clientX - startX;
      const dy = e.changedTouches[0].clientY - startY;
      if (swiping && !verticalGesture && Math.abs(dy) <= 8 && dx < -72) {
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
      renderProjects();
      showToast(t('btn_unfavorite'), 'info');
    });
  });

  container.addEventListener('touchstart', e => {
    if (swipedWrap && !swipedWrap.contains(e.target)) closeSwipe();
  }, { passive: true });
}
```

- [ ] **Step 4: Verify no syntax errors**

```bash
node --check static/app.js 2>&1
```

Expected: no output.

### 4c: Update `switchTab` and initial load

- [ ] **Step 5: Update `_closeAllSwipeRows` to also clear `swiped-single`**

Find `_closeAllSwipeRows` (near top of app.js):
```js
function _closeAllSwipeRows() {
  document.querySelectorAll('.project-card.swiped, .sess-item.swiped').forEach(el => {
    el.classList.remove('swiped');
    el.style.transform = '';
  });
  document.querySelectorAll('.project-swipe-wrap.swiped-open, .sess-swipe-wrap.swiped-open').forEach(el => {
    el.classList.remove('swiped-open');
  });
}
```

Replace with:
```js
function _closeAllSwipeRows() {
  document.querySelectorAll('.project-card.swiped, .project-card.swiped-single, .sess-item.swiped').forEach(el => {
    el.classList.remove('swiped', 'swiped-single');
    el.style.transform = '';
  });
  document.querySelectorAll('.project-swipe-wrap.swiped-open, .sess-swipe-wrap.swiped-open').forEach(el => {
    el.classList.remove('swiped-open');
  });
}
```

- [ ] **Step 6: Update `switchTab` to call `renderFavorites` when switching to favorites**

Find the `switchTab` function:
```js
function switchTab(tab) {
  _currentTab = tab;
  document.getElementById('main').style.display = tab === 'favorites' ? '' : 'none';
  document.getElementById('projects-view').style.display = tab === 'all' ? '' : 'none';
  document.querySelectorAll('.tab-item').forEach(el => {
    el.classList.toggle('active', el.dataset.tab === tab);
  });
  if (tab === 'all' && _projects.length === 0) loadProjects();
}
```

Replace with:
```js
function switchTab(tab) {
  _currentTab = tab;
  document.getElementById('main').style.display = tab === 'favorites' ? '' : 'none';
  document.getElementById('projects-view').style.display = tab === 'all' ? '' : 'none';
  document.querySelectorAll('.tab-item').forEach(el => {
    el.classList.toggle('active', el.dataset.tab === tab);
  });
  if (tab === 'favorites') renderFavorites();
  if (tab === 'all' && _projects.length === 0) loadProjects();
}
```

- [ ] **Step 7: Update `loadProjects` to call `renderFavorites` after loading**

Find `loadProjects`:
```js
async function loadProjects() {
  try {
    const res = await fetch('/api/projects');
    const data = await res.json();
    _projects = data.projects;
    renderProjects();
  } catch { /* ignore */ }
}
```

Replace with:
```js
async function loadProjects() {
  try {
    const res = await fetch('/api/projects');
    const data = await res.json();
    _projects = data.projects;
    renderFavorites();
    if (_currentTab === 'all') renderProjects();
  } catch { /* ignore */ }
}
```

- [ ] **Step 8: Replace the initial startup call**

Find at the bottom of app.js the `load()` call (inside `DOMContentLoaded` or standalone). It was previously `load()`. Now the app should call `loadProjects()` on startup.

Search for:
```js
load();
```
Or the DOMContentLoaded block. Replace `load()` with `loadProjects()`. If it appears inside an event listener:
```js
document.addEventListener('DOMContentLoaded', () => {
  loadProjects();
  ...
});
```

Also check for any `setInterval` or poll that calls `load()` and replace with `loadProjects()`.

- [ ] **Step 8: Verify no syntax errors**

```bash
node --check static/app.js 2>&1
```

Expected: no output.

---

## Task 5: app.js — all tab swipe adds pin button

**Files:**
- Modify: `static/app.js:565-600` (`projectCardHTML` and `_bindProjectSwipe`)

- [ ] **Step 1: Update `projectCardHTML` to use two-button swipe structure**

Find `projectCardHTML` function. Replace the return template:

```js
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
```

- [ ] **Step 2: Update `_bindProjectSwipe` to wire up pin button and fix swipe offset**

In `_bindProjectSwipe`, the `delBtn` selector and the swipe threshold need updating.

Find:
```js
    const delBtn = wrap.querySelector('.project-del-btn');
```
Replace with:
```js
    const delBtn = wrap.querySelector('.project-del-btn');
    const pinBtn = wrap.querySelector('.project-pin-btn');
```

The swiped class is already `swiped` which now maps to `translateX(-176px)` via CSS. The threshold for triggering swipe is `dx < -72` — keep this (user swipes past 72px → reveal both buttons). No JS change needed for distance; CSS handles the actual translation.

Add pin button wiring inside the `container.querySelectorAll` loop, after `delBtn.addEventListener('click', ...)`:

```js
    pinBtn.addEventListener('click', async () => {
      const encoded = card.dataset.encoded;
      const proj = _projects.find(p => p.encoded === encoded);
      if (!proj) return;
      await post('/api/config/toggle', { key: 'pinned', name: proj.display_name });
      proj.pinned = !proj.pinned;
      renderProjects();
      renderFavorites();
      showToast(proj.pinned ? t('btn_favorite') : t('btn_unfavorite'), 'info');
    });
```

- [ ] **Step 3: Verify no syntax errors**

```bash
node --check static/app.js 2>&1
```

Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add static/app.js
git commit -m "feat: favorites tab uses projects data; all tab swipe adds pin action"
```

---

## Task 6: app.js — manage panel removes hide button

**Files:**
- Modify: `static/app.js:330-378` (`openWsPanel` function)

- [ ] **Step 1: Update `openWsPanel` to remove hide button**

Find the `openWsPanel` function. Replace the inner `html` template string:

```js
  const html = data.workspaces.map(w => {
    const isPinned = cfg.pinned.includes(w.name);
    return `<div class="ws-item">
      <span class="ws-item-name">${escHTML(w.name)}</span>
      <div>
        <button class="tag-btn ${isPinned ? 'active-pin' : ''}"
          data-action="pin" data-name="${escAttr(w.name)}">${t('btn_pin')}</button>
      </div>
    </div>`;
  }).join('');
```

(Removed `isHidden`, `hidden-item` class, and the hide button entirely.)

- [ ] **Step 2: Update the click handler on `#settings-list` to only handle pin**

Find:
```js
document.getElementById('settings-list').addEventListener('click', async e => {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  await post('/api/config/toggle', {
    key: btn.dataset.action === 'pin' ? 'pinned' : 'hidden',
    name: btn.dataset.name,
  });
  openWsPanel();
});
```

Replace with:
```js
document.getElementById('settings-list').addEventListener('click', async e => {
  const btn = e.target.closest('[data-action="pin"]');
  if (!btn) return;
  await post('/api/config/toggle', { key: 'pinned', name: btn.dataset.name });
  openWsPanel();
});
```

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat: manage panel — remove hide button, pin only"
```

---

## Task 7: index.html — update manage panel hint text

**Files:**
- Modify: `static/index.html:102-103`

- [ ] **Step 1: Update the hint paragraph to use a new i18n key**

Find:
```html
    <p style="font-size:13px;color:var(--sub);margin-bottom:16px"
       data-i18n="ws_panel_hint">置顶常用项目，隐藏不需要显示的目录</p>
```

Replace with:
```html
    <p style="font-size:13px;color:var(--sub);margin-bottom:16px"
       data-i18n="ws_panel_hint_new">置顶收藏的项目，在收藏 tab 快速访问</p>
```

- [ ] **Step 2: Remove the old start/stop modal from HTML** (it's now dead code)

Delete the entire modal block:
```html
<!-- Session conflict modal -->
<div class="overlay" id="modal">
  <div class="modal">
    ...
  </div>
</div>
```

- [ ] **Step 3: Commit**

```bash
git add static/index.html
git commit -m "chore: update manage panel hint; remove dead modal HTML"
```

---

## Task 8: Manual verification

- [ ] **Step 1: Start server**

```bash
python3 server.py
```

- [ ] **Step 2: Open browser at `http://localhost:8765` and verify:**

1. **Favorites tab** — shows only pinned projects; if none pinned, shows empty state message
2. **Favorites tab swipe** — left swipe reveals "取消收藏" button; tap it → project disappears from favorites, appears unpinned in all tab
3. **All tab swipe** — left swipe reveals "收藏" + "删除" two buttons side by side
4. **All tab pin** — tap "收藏" on a project → it appears in favorites tab; button reflects state
5. **Favorites tap** — tapping a card opens the session panel (not old start/stop modal)
6. **Manage panel** — open settings → 管理工作空间 → only "置顶" button visible, no "隐藏" button

- [ ] **Step 3: Final commit if any fixups were needed**

```bash
git add -p
git commit -m "fix: post-verification adjustments"
```
