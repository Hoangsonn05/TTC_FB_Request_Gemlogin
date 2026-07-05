# -*- coding: utf-8 -*-
import atexit
import json
import os
import re
import shutil
import threading
import time
from datetime import datetime
from urllib.parse import parse_qs, urlparse


DEFAULT_HISTORY_FILE = "interaction_history.json"
DEFAULT_MAX_RECORDS = 3000
DEFAULT_WRITE_INTERVAL_SEC = 45


def _utc_now():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def normalize_object_id(object_id):
    value = str(object_id or "").strip()
    if not value:
        return ""

    parsed = urlparse(value if "://" in value else "https://facebook.com/" + value.lstrip("/"))
    query = parse_qs(parsed.query)
    for key in ("story_fbid", "fbid", "v", "id"):
        if query.get(key):
            return str(query[key][0]).strip()

    path = parsed.path.strip("/")
    if not path:
        return value

    parts = [p for p in path.split("/") if p]
    for marker in ("posts", "videos", "reel", "reels", "permalink"):
        if marker in parts:
            idx = parts.index(marker)
            if idx + 1 < len(parts):
                return parts[idx + 1].split("?")[0].strip()

    numbers = re.findall(r"\d{6,}", path)
    if numbers:
        return numbers[-1]

    return path


class InteractionHistory:
    _instances = {}
    _instances_lock = threading.Lock()

    @classmethod
    def get(cls, path=DEFAULT_HISTORY_FILE, max_records=DEFAULT_MAX_RECORDS):
        abs_path = os.path.abspath(path or DEFAULT_HISTORY_FILE)
        with cls._instances_lock:
            instance = cls._instances.get(abs_path)
            if instance is None:
                instance = cls(abs_path, max_records=max_records)
                cls._instances[abs_path] = instance
            else:
                instance.max_records = max(1, int(max_records or instance.max_records))
            return instance

    def __init__(self, path=DEFAULT_HISTORY_FILE, max_records=DEFAULT_MAX_RECORDS, write_interval_sec=DEFAULT_WRITE_INTERVAL_SEC):
        self.path = os.path.abspath(path or DEFAULT_HISTORY_FILE)
        self.max_records = max(1, int(max_records or DEFAULT_MAX_RECORDS))
        self.write_interval_sec = max(1, int(write_interval_sec or DEFAULT_WRITE_INTERVAL_SEC))
        self._lock = threading.Lock()
        self._records = {}
        self._same_action_index = set()
        self._post_any_index = set()
        self._dirty = False
        self._last_write = 0.0
        self._load_once()
        atexit.register(self.flush)

    def _same_action_key(self, profile_id, normalized_object_id, action_group):
        return (str(profile_id or ""), str(normalized_object_id or ""), str(action_group or ""))

    def _post_any_key(self, profile_id, normalized_object_id):
        return (str(profile_id or ""), str(normalized_object_id or ""))

    def _record_key(self, profile_id, normalized_object_id, action_group):
        return "|".join(self._same_action_key(profile_id, normalized_object_id, action_group))

    def _load_once(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            records = data.get("records") if isinstance(data, dict) else data
            if not isinstance(records, list):
                records = []
        except Exception:
            backup = f"{self.path}.corrupt.{int(time.time())}.bak"
            try:
                shutil.copy2(self.path, backup)
                print(f"[History] Corrupt interaction history backed up: {backup}")
            except Exception as backup_err:
                print(f"[History] Could not backup corrupt history: {backup_err}")
            return

        with self._lock:
            for record in records:
                if not isinstance(record, dict):
                    continue
                profile_id = str(record.get("profile_id") or "")
                normalized = normalize_object_id(record.get("normalized_object_id") or record.get("object_id"))
                action_group = str(record.get("action_group") or "")
                if not profile_id or not normalized or not action_group:
                    continue
                record["profile_id"] = profile_id
                record["normalized_object_id"] = normalized
                record["action_group"] = action_group
                key = self._record_key(profile_id, normalized, action_group)
                self._records[key] = record
                self._same_action_index.add(self._same_action_key(profile_id, normalized, action_group))
                self._post_any_index.add(self._post_any_key(profile_id, normalized))

    def has_interacted(self, profile_id, object_id, action_group=None, mode="same_action"):
        normalized = normalize_object_id(object_id)
        if not profile_id or not normalized:
            return False
        with self._lock:
            if mode == "post_any_action":
                return self._post_any_key(profile_id, normalized) in self._post_any_index
            return self._same_action_key(profile_id, normalized, action_group) in self._same_action_index

    def mark_interacted(self, profile_id, object_id, action_group, reaction_type=None):
        normalized = normalize_object_id(object_id)
        if not profile_id or not normalized or not action_group:
            return
        now = _utc_now()
        should_flush = False
        with self._lock:
            key = self._record_key(profile_id, normalized, action_group)
            record = self._records.get(key)
            if record is None:
                record = {
                    "profile_id": str(profile_id),
                    "object_id": str(object_id or ""),
                    "normalized_object_id": normalized,
                    "action_group": str(action_group),
                    "reaction_type": reaction_type,
                    "first_seen_at": now,
                    "last_seen_at": now,
                    "count": 1,
                }
                self._records[key] = record
            else:
                record["last_seen_at"] = now
                record["count"] = int(record.get("count") or 0) + 1
                if reaction_type:
                    record["reaction_type"] = reaction_type
            self._same_action_index.add(self._same_action_key(profile_id, normalized, action_group))
            self._post_any_index.add(self._post_any_key(profile_id, normalized))
            self._dirty = True
            should_flush = (time.time() - self._last_write) >= self.write_interval_sec
        if should_flush:
            self.flush()

    def prune_history(self, max_records=None):
        limit = max(1, int(max_records or self.max_records))
        with self._lock:
            self._prune_locked(limit)

    def _prune_locked(self, limit):
        if len(self._records) <= limit:
            return
        sorted_items = sorted(
            self._records.items(),
            key=lambda item: str(item[1].get("last_seen_at") or item[1].get("first_seen_at") or ""),
            reverse=True,
        )
        self._records = dict(sorted_items[:limit])
        self._same_action_index = set()
        self._post_any_index = set()
        for record in self._records.values():
            profile_id = str(record.get("profile_id") or "")
            normalized = str(record.get("normalized_object_id") or "")
            action_group = str(record.get("action_group") or "")
            self._same_action_index.add(self._same_action_key(profile_id, normalized, action_group))
            self._post_any_index.add(self._post_any_key(profile_id, normalized))

    def flush(self):
        with self._lock:
            if not self._dirty:
                return
            self._prune_locked(self.max_records)
            records = list(self._records.values())
            self._dirty = False
            self._last_write = time.time()

        payload = {
            "version": 1,
            "updated_at": _utc_now(),
            "records": records,
        }
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp_path = f"{self.path}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.path)
        except Exception as e:
            with self._lock:
                self._dirty = True
            print(f"[History] Could not write interaction history: {e}")


_default_history = None
_default_lock = threading.Lock()


def _get_default_history():
    global _default_history
    with _default_lock:
        if _default_history is None:
            _default_history = InteractionHistory.get()
        return _default_history


def has_interacted(profile_id, object_id, action_group=None, mode="same_action"):
    return _get_default_history().has_interacted(profile_id, object_id, action_group, mode)


def mark_interacted(profile_id, object_id, action_group, reaction_type=None):
    return _get_default_history().mark_interacted(profile_id, object_id, action_group, reaction_type)


def prune_history(max_records=DEFAULT_MAX_RECORDS):
    return _get_default_history().prune_history(max_records)
