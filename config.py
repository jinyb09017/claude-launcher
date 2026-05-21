import json
import pathlib

CONFIG_PATH = pathlib.Path(__file__).parent / "config.json"


def load_config():
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    cfg["scan_dir"] = str(pathlib.Path(cfg["scan_dir"]).expanduser())
    return cfg


def save_config(cfg):
    save = dict(cfg)
    save["scan_dir"] = cfg["scan_dir"].replace(str(pathlib.Path.home()), "~")
    with open(CONFIG_PATH, "w") as f:
        json.dump(save, f, indent=2, ensure_ascii=False)
