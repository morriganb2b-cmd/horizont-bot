import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

DEFAULT_DATA: Dict[str, Any] = {
    "leaders": {},
    "deputies": {},
    "news": [],
    "settings": {
        "total_commands": 0,
        "last_news_cleanup": None,
        "bot_start_time": None,
    },
}

DATE_FMT = "%d.%m.%Y %H:%M"


def now_str() -> str:
    return datetime.now(timezone.utc).astimezone().strftime(DATE_FMT)


class DataManager:
    def __init__(self, data_path: str, log_path: str):
        self.data_path = data_path
        self.log_path = log_path
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        if not os.path.exists(self.data_path):
            self._write(DEFAULT_DATA)
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w", encoding="utf-8") as f:
                f.write("")

    def _read(self) -> Dict[str, Any]:
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            # Recovery to default if corrupted
            self._write(DEFAULT_DATA)
            return DEFAULT_DATA.copy()

    def _write(self, data: Dict[str, Any]) -> None:
        with open(self.data_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self) -> Dict[str, Any]:
        return self._read()

    def save(self, data: Dict[str, Any]) -> None:
        self._write(data)

    def log(self, message: str) -> None:
        line = f"[{now_str()}] {message}\n"
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line)
        print(line, end="")

    def increment_commands(self) -> None:
        data = self._read()
        data.setdefault("settings", {})
        data["settings"]["total_commands"] = int(data["settings"].get("total_commands", 0)) + 1
        self._write(data)

    def set_start_time(self) -> None:
        data = self._read()
        data.setdefault("settings", {})
        data["settings"]["bot_start_time"] = now_str()
        self._write(data)

    # News helpers
    def add_news(self, text: str, author: str, channel_name: str, channel_id: int) -> None:
        data = self._read()
        data.setdefault("news", [])
        data["news"].insert(0, {
            "text": text,
            "date": now_str(),
            "author": author,
            "channel": channel_name,
            "channel_id": channel_id,
        })
        self._write(data)

    def cleanup_news(self, older_than_minutes: int = 24*60) -> int:
        # Remove news older than given minutes
        data = self._read()
        news = data.get("news", [])
        def parse(d: str) -> Optional[datetime]:
            try:
                return datetime.strptime(d, DATE_FMT)
            except Exception:
                return None
        threshold = datetime.now().astimezone()
        kept = []
        removed = 0
        for item in news:
            dt = parse(item.get("date", ""))
            if not dt:
                continue
            minutes = (threshold - dt).total_seconds() / 60.0
            if minutes <= older_than_minutes:
                kept.append(item)
            else:
                removed += 1
        data["news"] = kept
        data.setdefault("settings", {})
        data["settings"]["last_news_cleanup"] = now_str()
        self._write(data)
        return removed

    # Generic helpers for leaders/deputies
    def get_person(self, category: str, nickname: str) -> Optional[Dict[str, Any]]:
        data = self._read()
        return data.get(category, {}).get(nickname)

    def set_person(self, category: str, nickname: str, payload: Dict[str, Any]) -> None:
        data = self._read()
        data.setdefault(category, {})
        data[category][nickname] = payload
        self._write(data)

    def remove_person(self, category: str, nickname: str) -> bool:
        data = self._read()
        if nickname in data.get(category, {}):
            del data[category][nickname]
            self._write(data)
            return True
        return False

    def add_warning(self, category: str, nickname: str, reason: str, issued_by: str) -> int:
        data = self._read()
        person = data.get(category, {}).get(nickname)
        if not person:
            return 0
        person.setdefault("warnings", [])
        person["warnings"].append({
            "date": now_str(),
            "reason": reason,
            "issued_by": issued_by,
        })
        self._write(data)
        return len(person["warnings"])

    def clear_warnings(self, category: str, nickname: str) -> None:
        data = self._read()
        person = data.get(category, {}).get(nickname)
        if not person:
            return
        person["warnings"] = []
        self._write(data)

    def add_reprimand(self, category: str, nickname: str, reason: str, issued_by: str) -> int:
        data = self._read()
        person = data.get(category, {}).get(nickname)
        if not person:
            return 0
        person.setdefault("reprimands", [])
        number = len(person["reprimands"]) + 1
        person["reprimands"].append({
            "date": now_str(),
            "reason": reason,
            "issued_by": issued_by,
            "number": number,
        })
        self._write(data)
        return number
