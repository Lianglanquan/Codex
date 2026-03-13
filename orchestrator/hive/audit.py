from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class AuditLogger:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.run_dir / "events.ndjson"

    def emit(self, event_type: str, **payload: Any) -> None:
        event = {
            "ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "type": event_type,
            **payload,
        }
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False))
            handle.write("\n")

    def write_json(self, path: Path, payload: BaseModel | dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, BaseModel):
            data = payload.model_dump(mode="json")
        else:
            data = payload
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

