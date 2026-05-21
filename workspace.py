import pathlib
import subprocess


def scan_workspaces(cfg, include_hidden=False):
    scan_dir = pathlib.Path(cfg["scan_dir"])
    require_md = cfg.get("require_claude_md", True)
    hidden = set(cfg.get("hidden", []))
    pinned = cfg.get("pinned", [])

    entries = []
    if scan_dir.exists():
        for d in sorted(scan_dir.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            if not include_hidden and d.name in hidden:
                continue
            if require_md and not (d / "CLAUDE.md").exists():
                continue
            mtime = d.stat().st_mtime
            entries.append({
                "name": d.name,
                "path": str(d),
                "mtime": mtime,
                "is_hidden": d.name in hidden,
            })

    entries.sort(key=lambda e: (
        0 if e["name"] in pinned else 1,
        pinned.index(e["name"]) if e["name"] in pinned else -e["mtime"]
    ))
    return entries


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


def start_session(dirname, path):
    name = session_name(dirname)
    subprocess.Popen(
        ["tmux", "new-session", "-d", "-s", name, "-c", path, "claude"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def kill_session(dirname):
    name = session_name(dirname)
    subprocess.run(["tmux", "kill-session", "-t", name], stderr=subprocess.DEVNULL)


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
