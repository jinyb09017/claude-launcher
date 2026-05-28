import json
import os
import pathlib
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime

from config import load_config

CLAUDE_DIR = pathlib.Path.home() / '.claude'
LAUNCHER_MAP = CLAUDE_DIR / 'launcher_sessions.json'


def _find_claude() -> str:
    """Locate the claude binary, checking user dirs the server PATH may miss."""
    home = pathlib.Path.home()
    candidates = [
        home / '.local' / 'bin' / 'claude',
        home / 'bin' / 'claude',
        pathlib.Path('/usr/local/bin/claude'),
        pathlib.Path('/opt/homebrew/bin/claude'),
    ]
    for p in candidates:
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return 'claude'  # fallback: hope tmux inherits a usable PATH


CLAUDE_BIN = _find_claude()



def list_tmux_sessions():
    try:
        out = subprocess.check_output(
            ["tmux", "ls", "-F", "#{session_name}"], stderr=subprocess.DEVNULL, text=True
        )
        return set(out.strip().splitlines())
    except subprocess.CalledProcessError:
        return set()


def session_name(dirname):
    return f"claude_{dirname}"



def kill_session(path):
    """Kill all tmux sessions for this workspace path (covers both generic and renamed sessions)."""
    base = _path_base(path)
    for s in list_tmux_sessions():
        if s == base or s.startswith(base + '_'):
            subprocess.run(["tmux", "kill-session", "-t", s], stderr=subprocess.DEVNULL)


def stop_session_by_id(session_id: str) -> bool:
    """Kill the specific tmux session mapped to session_id. Returns True if killed."""
    m = _load_session_map()
    tmux_name = m.get(session_id)
    if not tmux_name:
        return False
    result = subprocess.run(
        ["tmux", "kill-session", "-t", tmux_name], stderr=subprocess.DEVNULL
    )
    return result.returncode == 0


# ── Claude project discovery ───────────────────────────────────

def _decode_project_path(encoded: str):
    """Decode ~/.claude/projects/<encoded> dir name back to a real path.
    Claude encodes by replacing all non-alphanumeric chars with '-'.
    Uses greedy filesystem matching to resolve ambiguous hyphens.
    """
    if not encoded.startswith('-'):
        return None
    home = pathlib.Path.home()
    home_enc = re.sub(r'[^a-zA-Z0-9]', '-', str(home)[1:])
    rest = encoded[1:]
    if not rest.startswith(home_enc):
        return None
    remainder = rest[len(home_enc):]
    return _greedy_path(home, remainder)


def _greedy_path(base, remainder):
    if not remainder:
        return str(base)
    if not remainder.startswith('-'):
        return None
    tail = remainder[1:]
    try:
        entries = sorted(os.listdir(base), key=lambda x: -len(x))
    except (PermissionError, NotADirectoryError, FileNotFoundError):
        return None
    for entry in entries:
        enc = re.sub(r'[^a-zA-Z0-9]', '-', entry)
        if tail.startswith(enc):
            result = _greedy_path(pathlib.Path(base) / entry, tail[len(enc):])
            if result is not None:
                return result
    return None


def _display_name_for_path(path):
    if not path:
        return '—'
    parts = pathlib.Path(path).parts
    return '/'.join(parts[-2:]) if len(parts) >= 2 else parts[-1]


def scan_claude_projects():
    """List all projects from ~/.claude/projects/, sorted by most recent session."""
    projects_dir = CLAUDE_DIR / 'projects'
    if not projects_dir.exists():
        return []
    results = []
    for proj_dir in sorted(projects_dir.iterdir()):
        if not proj_dir.is_dir():
            continue
        jsonl_files = sorted(
            proj_dir.glob('*.jsonl'),
            key=lambda x: x.stat().st_mtime, reverse=True
        )
        if not jsonl_files:
            continue
        real_path = _decode_project_path(proj_dir.name)
        results.append({
            'encoded': proj_dir.name,
            'path': real_path,
            'display_name': _display_name_for_path(real_path),
            'session_count': len(jsonl_files),
            'last_mtime': jsonl_files[0].stat().st_mtime,
        })
    results.sort(key=lambda x: -x['last_mtime'])
    return results


_FILTER_PATTERNS = [
    'git commit message',
    'git diff',
]


def _is_oneshot_session(preview: str) -> bool:
    low = preview.lower()
    return any(p in low for p in _FILTER_PATTERNS)


def delete_session(encoded: str, session_id: str) -> bool:
    """Delete a session JSONL file. Returns True if deleted."""
    f = CLAUDE_DIR / 'projects' / encoded / f'{session_id}.jsonl'
    try:
        f.unlink()
        return True
    except FileNotFoundError:
        return False


def delete_project_logs(encoded: str) -> bool:
    """Delete one Claude project log directory, never the decoded real project path."""
    projects_dir = (CLAUDE_DIR / 'projects').resolve()
    target = (projects_dir / encoded).resolve()
    if projects_dir not in target.parents or target == projects_dir:
        return False
    if not target.exists() or not target.is_dir():
        return False
    shutil.rmtree(target)
    return True


def _read_custom_title(path) -> str:
    """Return the custom-title value from a JSONL session file, or ''."""
    try:
        with open(path) as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    if obj.get('type') == 'custom-title':
                        return obj.get('customTitle', '')
                except Exception:
                    continue
    except Exception:
        pass
    return ''


def get_project_sessions(encoded: str):
    """List all sessions (JSONL files) for one project, filtering one-shot utility sessions."""
    proj_dir = CLAUDE_DIR / 'projects' / encoded
    if not proj_dir.exists():
        return []
    sessions = []
    for f in sorted(proj_dir.glob('*.jsonl'), key=lambda x: x.stat().st_mtime, reverse=True):
        first_user = _first_user_message(f)
        if _is_oneshot_session(first_user):
            continue
        preview = _last_user_message(f) or first_user
        sessions.append({
            'id': f.stem,
            'mtime': f.stat().st_mtime,
            'size': f.stat().st_size,
            'preview': preview,
            'title': _read_custom_title(f),
        })
    return sessions


def get_session_messages(encoded: str, session_id: str):
    """Read all messages from one session JSONL for display."""
    f = CLAUDE_DIR / 'projects' / encoded / f'{session_id}.jsonl'
    if not f.exists():
        return []

    by_id = {}
    ordered = []

    try:
        with open(f) as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get('isSidechain'):
                    continue
                msg = obj.get('message', {})
                role = msg.get('role')
                if role not in ('user', 'assistant'):
                    continue

                content = msg.get('content', '')
                # Skip pure tool-result injections
                if isinstance(content, list) and content and all(
                    isinstance(c, dict) and c.get('type') == 'tool_result'
                    for c in content
                ):
                    continue
                # Skip system XML injections (skill notices, command-name tags)
                if isinstance(content, str) and content.lstrip().startswith('<'):
                    continue

                key = (msg.get('id') or obj.get('promptId') or '')
                text, tools = _extract_content(content, role)
                if not text and not tools:
                    continue

                entry = {'role': role, 'text': text[:600], 'tools': tools[:8]}
                if key:
                    if key not in by_id:
                        by_id[key] = entry
                        ordered.append(key)
                    else:
                        by_id[key] = entry  # keep latest
                else:
                    ordered.append(entry)
    except (IOError, PermissionError):
        pass

    result = []
    seen = set()
    for item in ordered:
        if isinstance(item, str):
            if item not in seen:
                seen.add(item)
                result.append(by_id[item])
        else:
            result.append(item)
    return result


def _extract_content(content, role=''):
    text = ''
    tools = []
    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        for c in content:
            if not isinstance(c, dict):
                continue
            ctype = c.get('type', '')
            if ctype == 'tool_result':
                # Skip tool result injections (they appear as user-role messages)
                continue
            if ctype == 'text':
                t = c.get('text', '').strip()
                # Skip system-injected and skill boilerplate blocks
                if t.startswith('<'):
                    continue
                if t.startswith('Base directory for this skill:'):
                    continue
                text += t
            elif ctype == 'tool_use' and role == 'assistant':
                inp = c.get('input', {})
                name = c.get('name', '')
                desc = _tool_desc(name, inp)
                tools.append({'name': name, 'desc': desc})
    return text.strip(), tools


def _tool_desc(name, inp):
    if name in ('Read', 'Write', 'Edit'):
        return inp.get('file_path', '') or inp.get('path', '')
    if name == 'Bash':
        cmd = inp.get('command', '')
        return (cmd[:80] + '…') if len(cmd) > 80 else cmd
    if name == 'Agent':
        return inp.get('description', '')[:60]
    return ''


def _first_user_message(path):
    try:
        with open(path) as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    if obj.get('isSidechain'):
                        continue
                    msg = obj.get('message', {})
                    if msg.get('role') != 'user':
                        continue
                    content = msg.get('content', '')
                    # skip pure tool-result messages and XML injections
                    if isinstance(content, list) and content and all(
                        isinstance(c, dict) and c.get('type') == 'tool_result'
                        for c in content
                    ):
                        continue
                    if isinstance(content, str):
                        txt = content.strip()
                        if txt and not txt.startswith('<'):
                            return txt[:200]
                    elif isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and c.get('type') == 'text':
                                txt = c.get('text', '').strip()
                                if txt and not txt.startswith('<') and not txt.startswith('Base directory'):
                                    return txt[:200]
                except (json.JSONDecodeError, KeyError):
                    continue
    except (IOError, PermissionError):
        pass
    return ''


def _last_user_message(path):
    last_text = ''
    try:
        with open(path) as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    if obj.get('isSidechain'):
                        continue
                    msg = obj.get('message', {})
                    if msg.get('role') != 'user':
                        continue
                    content = msg.get('content', '')
                    if isinstance(content, list) and content and all(
                        isinstance(c, dict) and c.get('type') == 'tool_result'
                        for c in content
                    ):
                        continue
                    if isinstance(content, str):
                        txt = content.strip()
                        if txt and not txt.startswith('<'):
                            last_text = txt[:200]
                    elif isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and c.get('type') == 'text':
                                txt = c.get('text', '').strip()
                                if txt and not txt.startswith('<') and not txt.startswith('Base directory'):
                                    last_text = txt[:200]
                                    break
                except (json.JSONDecodeError, KeyError):
                    continue
    except (IOError, PermissionError):
        pass
    return last_text


def _path_base(path: str) -> str:
    """last-2-path-components joined with _, tmux-safe."""
    parts = pathlib.Path(path).parts
    last2 = '/'.join(parts[-2:]) if len(parts) >= 2 else (parts[-1] if parts else 'session')
    return re.sub(r'[^a-zA-Z0-9._-]', '_', last2)


def _encode_path(path: str) -> str:
    """Encode a filesystem path to Claude's ~/.claude/projects/<encoded> directory name."""
    return '-' + re.sub(r'[^a-zA-Z0-9]', '-', path[1:])


def _session_name_hhmm(path: str) -> str:
    """Generate a session name: <last2_path>_<HHMM>. Appends counter on conflict."""
    base = _path_base(path)
    hhmm = datetime.now().strftime('%H%M')
    candidate = f"{base}_{hhmm}"
    sessions = list_tmux_sessions()
    if candidate not in sessions:
        return candidate
    for i in range(2, 20):
        c = f"{base}_{hhmm}_{i}"
        if c not in sessions:
            return c
    return candidate  # last resort


# ── Session map: session_id → tmux_name ───────────────────────

def _load_session_map() -> dict:
    try:
        return json.loads(LAUNCHER_MAP.read_text())
    except Exception:
        return {}


def _register_session(session_id: str, tmux_name: str):
    """Record session_id → tmux_name. Prunes stale entries."""
    running = list_tmux_sessions()
    m = {k: v for k, v in _load_session_map().items() if v in running}
    m[session_id] = tmux_name
    try:
        LAUNCHER_MAP.write_text(json.dumps(m))
    except Exception:
        pass


# ── Background tmux monitor ────────────────────────────────────

_monitor_started = False
_monitor_lock = threading.Lock()


def start_tmux_monitor():
    """Start the background monitor (idempotent)."""
    global _monitor_started
    with _monitor_lock:
        if _monitor_started:
            return
        _monitor_started = True
    threading.Thread(target=_monitor_loop, daemon=True).start()


def _list_tmux_sessions_timed() -> dict:
    """Returns {session_name: created_unix_timestamp}."""
    try:
        out = subprocess.check_output(
            ["tmux", "ls", "-F", "#{session_name} #{session_created}"],
            stderr=subprocess.DEVNULL, text=True,
        )
        result = {}
        for line in out.strip().splitlines():
            parts = line.split()
            if len(parts) == 2:
                result[parts[0]] = float(parts[1])
        return result
    except subprocess.CalledProcessError:
        return {}


def _monitor_loop():
    """Reconcile launcher_sessions.json against live tmux every 2 s.

    Map invariant after each cycle:
      - Every launcher-related tmux session has an entry (key=session_id or key=tmux_name
        as placeholder when JSONL not yet written).
      - No entry whose tmux session no longer exists.
    All "is running" checks read from this map; nothing queries tmux directly.
    """
    while True:
        try:
            timed = _list_tmux_sessions_timed()          # {name: created_ts}
            current = set(timed)
            m = _load_session_map()

            new_m: dict = {}

            # 1. Carry over entries whose tmux session is still alive.
            for k, v in m.items():
                if v in current:
                    new_m[k] = v

            # 2. For every active launcher-related tmux session not yet tracked,
            #    add it: session_id → name if JSONL exists, else name → name (placeholder).
            tracked_names = set(new_m.values())
            for sname in current:
                if sname in tracked_names:
                    continue
                path = _path_for_tmux_session(sname)
                if not path:
                    continue
                sid = _find_jsonl_since(path, timed[sname])
                if sid and sid not in new_m:
                    new_m[sid] = sname          # known session_id
                elif not sid:
                    new_m[sname] = sname        # placeholder: no JSONL yet

            # 3. Try to resolve placeholder entries (key == value) now that JSONL may exist.
            for k in list(new_m):
                if k != new_m[k]:
                    continue                    # already a real session_id key
                sname = k
                path = _path_for_tmux_session(sname)
                if not path:
                    continue
                sid = _find_jsonl_since(path, timed.get(sname, 0))
                if sid and sid not in new_m:
                    del new_m[k]
                    new_m[sid] = sname

            if new_m != m:
                try:
                    LAUNCHER_MAP.write_text(json.dumps(new_m))
                except Exception:
                    pass

        except Exception:
            pass
        time.sleep(2)


def _path_for_tmux_session(sname: str):
    """Find the project path whose _path_base is a prefix of the tmux session name."""
    projects_dir = CLAUDE_DIR / 'projects'
    if not projects_dir.exists():
        return None
    for proj_dir in projects_dir.iterdir():
        if not proj_dir.is_dir():
            continue
        path = _decode_project_path(proj_dir.name)
        if not path:
            continue
        base = _path_base(path)
        if sname == base or sname.startswith(base + '_'):
            return path
    return None


def _find_jsonl_since(path: str, since: float):
    """Return session_id of any JSONL written to this project since `since`."""
    proj_dir = CLAUDE_DIR / 'projects' / _encode_path(path)
    if not proj_dir.exists():
        return None
    candidates = [f for f in proj_dir.glob('*.jsonl') if f.stat().st_mtime >= since - 1]
    if not candidates:
        return None
    return max(candidates, key=lambda f: f.stat().st_mtime).stem


def start_session_by_path(path: str, session_id: str = None):
    sname = _session_name_hhmm(path)
    if session_id:
        claude_cmd = [CLAUDE_BIN, '-n', sname, '--remote-control', '--resume', session_id]
    else:
        claude_cmd = [CLAUDE_BIN, '-n', sname, '--remote-control']
    extra_env = load_config().get("claude_env", {})
    # subprocess.Popen env= only affects the tmux client process, not the pane
    # spawned by the tmux server. Use -e flags so vars reach the actual command.
    env_flags = [arg for k, v in extra_env.items() for arg in ('-e', f'{k}={v}')]
    subprocess.Popen(
        ['tmux', 'new-session', '-d', '-s', sname, '-c', path] + env_flags + claude_cmd,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if session_id:
        _register_session(session_id, sname)
    return sname


def find_session_cwd(encoded: str, session_id: str) -> str:
    """Resolve the working directory needed for --resume.
    1. Try decoding the encoded path directly.
    2. Fall back to locating the JSONL file and reading its stored cwd.
    3. Last resort: home directory.
    """
    # Primary: decode encoded path
    path = _decode_project_path(encoded) if encoded else None
    if path and pathlib.Path(path).exists():
        return path

    # Fallback: find the JSONL and look for a stored cwd hint
    if encoded and session_id:
        jsonl = CLAUDE_DIR / 'projects' / encoded / f'{session_id}.jsonl'
        if jsonl.exists():
            try:
                with open(jsonl) as f:
                    for line in f:
                        try:
                            obj = json.loads(line)
                            cwd = obj.get('cwd') or obj.get('workingDirectory')
                            if cwd and pathlib.Path(cwd).exists():
                                return cwd
                        except (json.JSONDecodeError, TypeError):
                            continue
            except (IOError, PermissionError):
                pass
            # JSONL exists but no cwd hint — use its parent dir name as last try
            # The encoded dir IS the project path; resume will work from home if
            # the real path no longer exists (worktrees, deleted dirs, etc.)

    return str(pathlib.Path.home())



def count_jsonl_lines(encoded: str, session_id: str) -> int:
    f = CLAUDE_DIR / 'projects' / encoded / f'{session_id}.jsonl'
    try:
        with open(f) as fh:
            return sum(1 for _ in fh)
    except (IOError, PermissionError, FileNotFoundError):
        return 0


def read_new_jsonl_messages(encoded: str, session_id: str, from_line: int):
    """Read messages from line `from_line` onward. Returns (messages, total_line_count)."""
    f = CLAUDE_DIR / 'projects' / encoded / f'{session_id}.jsonl'
    new_messages = []
    total = from_line
    try:
        with open(f) as fh:
            for i, line in enumerate(fh):
                total = i + 1
                if i < from_line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get('isSidechain'):
                    continue
                msg = obj.get('message', {})
                role = msg.get('role')
                if role not in ('user', 'assistant'):
                    continue
                content = msg.get('content', '')
                if isinstance(content, list) and content and all(
                    isinstance(c, dict) and c.get('type') == 'tool_result' for c in content
                ):
                    continue
                if isinstance(content, str) and content.lstrip().startswith('<'):
                    continue
                text, tools = _extract_content(content, role)
                if not text and not tools:
                    continue
                new_messages.append({'role': role, 'text': text[:600], 'tools': tools[:8]})
    except (IOError, PermissionError, FileNotFoundError):
        pass
    return new_messages, total


def find_tmux_session_for_project(encoded: str, session_id: str):
    """Return running tmux session name for project+session, or None.
    Reads only from launcher_sessions.json — the monitor keeps it current.

    When session_id is given, only an exact match is returned — the path-prefix
    fallback is intentionally skipped so that a running sibling session cannot
    block resuming a specific stopped session.
    """
    m = _load_session_map()

    if session_id:
        # Exact lookup only: monitor prunes stale entries, so presence == running.
        return m.get(session_id)

    # Path-prefix fallback: used only for new sessions (no specific id) to detect
    # whether any session for this project is already running.
    active = set(m.values())
    path = _decode_project_path(encoded) if encoded else None
    if path:
        base = _path_base(path)
        for v in active:
            if v == base or v.startswith(base + '_'):
                return v
    return None


def wait_for_claude_ready(encoded: str, session_id: str,
                          lines_before: int = 0, timeout: float = 15) -> bool:
    """Poll JSONL until Claude appends at least one new line (startup write). False on timeout."""
    import time
    f = CLAUDE_DIR / 'projects' / encoded / f'{session_id}.jsonl'
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            current = sum(1 for _ in open(f))
            if current > lines_before:
                return True
        except (IOError, FileNotFoundError):
            pass
        time.sleep(0.5)
    return False


def send_to_tmux_session(tmux_name: str, message: str) -> bool:
    """Inject a message into a running tmux session. Returns True on success."""
    try:
        subprocess.run(
            ['tmux', 'send-keys', '-t', tmux_name, message, 'Enter'],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return True
    except subprocess.CalledProcessError:
        return False


def short_path(full_path):
    p = pathlib.Path(full_path)
    home = pathlib.Path.home()
    try:
        rel = p.relative_to(home)
        parts = rel.parts
        return "~/" + "/".join(parts[-2:]) if len(parts) >= 2 else "~/" + str(rel)
    except ValueError:
        parts = p.parts
        return "/".join(parts[-2:]) if len(parts) >= 2 else full_path
