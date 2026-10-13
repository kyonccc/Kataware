"""User settings and application paths."""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_NAME = "Kataware"
APP_ID = "io.github.kyonccc.kataware"

log = logging.getLogger(__name__)


def app_dir() -> Path:
    override = os.environ.get("KATAWARE_HOME")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def log_path() -> Path:
    return app_dir() / "kataware.log"


def setup_logging(verbose: bool = False) -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s")
    fh = logging.handlers.RotatingFileHandler(log_path(), maxBytes=512_000, backupCount=2, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if sys.stderr is not None:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)


@dataclass
class Settings:
    poll_minutes: int = 5
    low_threshold: int = 20  # 0 disables notifications
    icon_style: str = "numbers"  # "numbers" or "bars"
    icon_device: str = ""  # device_id shown in the tray icon; "" = auto
    central_side: dict[str, str] = field(default_factory=dict)  # device_id -> "left"/"right"
    welcomed: bool = False  # first-launch "where is the icon" notification shown


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path or (app_dir() / "config.json")
        self._lock = threading.Lock()
        self.settings = self._load()

    def _load(self) -> Settings:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            known = {k: v for k, v in data.items() if k in Settings.__dataclass_fields__}
            s = Settings(**known)
            if s.icon_style not in ("numbers", "bars"):
                s.icon_style = "numbers"
            s.poll_minutes = max(1, int(s.poll_minutes))
            s.low_threshold = max(0, min(100, int(s.low_threshold)))
            if not isinstance(s.central_side, dict):
                s.central_side = {}
            return s
        except FileNotFoundError:
            return Settings()
        except Exception:  # corrupt file: start fresh rather than crash
            log.exception("設定ファイルを読み込めませんでした。既定値を使用します")
            return Settings()

    def save(self) -> None:
        with self._lock:
            try:
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(asdict(self.settings), ensure_ascii=False, indent=2), encoding="utf-8")
                os.replace(tmp, self.path)
            except Exception:
                log.exception("設定ファイルを保存できませんでした")
