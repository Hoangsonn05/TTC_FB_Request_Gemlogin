# -*- coding: utf-8 -*-
"""Test config migration — normalize_action_executor_config và load/save multi config.

Phản ánh schema mới:
  - Không còn provider_enabled / provider_url
  - Default executor: facebook_graphql_context
  - Migration: unsupported -> facebook_graphql_context
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ttc_config import load_multi_config, save_multi_config, normalize_action_executor_config


# ── test load_multi_config ────────────────────────────────────────────────────

def test_config_migration_adds_action_executor(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"global": {}, "workers": [{"worker_id": "1"}]}), encoding="utf-8")
    data = load_multi_config(str(config_path))
    worker = data["workers"][0]
    # Default executor mới là facebook_graphql_context
    assert worker["facebook_action_executor"] == "facebook_graphql_context"
    assert worker["action_executor"]["name"] == "facebook_graphql_context"
    # provider_enabled và provider_url không còn tồn tại trong config
    assert "provider_enabled" not in worker["action_executor"]
    assert "provider_url" not in worker["action_executor"]


def test_load_no_provider_url_in_schema(tmp_path):
    """Schema mới không có provider_url field."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "global": {},
        "workers": [{"worker_id": "1", "facebook_action_executor": "facebook_graphql_context"}]
    }), encoding="utf-8")
    data = load_multi_config(str(config_path))
    worker = data["workers"][0]
    assert "provider_url" not in worker["action_executor"]
    assert "provider_enabled" not in worker["action_executor"]


def test_load_migrates_unsupported_to_facebook_graphql_context(tmp_path):
    """Worker cũ dùng unsupported được nâng lên facebook_graphql_context."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "global": {},
        "workers": [{"worker_id": "1", "facebook_action_executor": "unsupported"}]
    }), encoding="utf-8")
    data = load_multi_config(str(config_path))
    worker = data["workers"][0]
    assert worker["action_executor"]["name"] == "facebook_graphql_context"


def test_save_preserves_nested_action_executor(tmp_path):
    config_path = tmp_path / "config.json"
    save_multi_config({
        "global": {},
        "workers": [{
            "worker_id": "1",
            "facebook_action_executor": "facebook_graphql_context",
            "action_executor": {"name": "facebook_graphql_context", "timeout_ms": 15000},
            "use_cookie": False,
            "cookie": "secret",
        }],
    }, str(config_path))
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    worker = saved["workers"][0]
    assert worker["facebook_action_executor"] == "facebook_graphql_context"
    assert worker["action_executor"]["name"] == "facebook_graphql_context"
    assert "cookie" not in worker
    # provider fields không được lưu
    assert "provider_enabled" not in worker["action_executor"]
    assert "provider_url" not in worker["action_executor"]


def test_save_removes_old_provider_fields_from_legacy_config(tmp_path):
    """Config cũ có provider_enabled/provider_url phải bị strip khi save."""
    config_path = tmp_path / "config.json"
    save_multi_config({
        "global": {},
        "workers": [{
            "worker_id": "1",
            "facebook_action_executor": "facebook_graphql_context",
            "action_executor": {
                "name": "facebook_graphql_context",
                "provider_enabled": True,
                "provider_url": "https://old-provider.example.com",
            },
        }],
    }, str(config_path))
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    worker = saved["workers"][0]
    assert "provider_enabled" not in worker["action_executor"]
    assert "provider_url" not in worker["action_executor"]


# ── test normalize_action_executor_config ─────────────────────────────────────

def test_normalize_from_legacy_key_only():
    config = {"facebook_action_executor": "facebook_graphql_context"}
    result = normalize_action_executor_config(config)
    assert result["facebook_action_executor"] == "facebook_graphql_context"
    ae = result["action_executor"]
    assert ae["name"] == "facebook_graphql_context"
    assert ae["verify_after_action"] is True
    assert ae["fail_closed"] is True
    assert ae["timeout_ms"] == 15000
    assert ae["max_action_retry"] == 0
    # Không còn provider fields
    assert "provider_enabled" not in ae
    assert "provider_url" not in ae


def test_normalize_empty_config():
    config = {}
    result = normalize_action_executor_config(config)
    # Empty config -> nâng lên facebook_graphql_context
    assert result["facebook_action_executor"] == "facebook_graphql_context"
    assert result["action_executor"]["name"] == "facebook_graphql_context"


def test_normalize_unsupported_migrates_to_facebook_graphql():
    """unsupported executor cũ phải được nâng lên facebook_graphql_context."""
    config = {"facebook_action_executor": "unsupported"}
    result = normalize_action_executor_config(config)
    assert result["action_executor"]["name"] == "facebook_graphql_context"


def test_normalize_dry_run_preserved():
    """dry_run và executor tùy chỉnh khác không bị thay đổi."""
    config = {"facebook_action_executor": "dry_run"}
    result = normalize_action_executor_config(config)
    assert result["action_executor"]["name"] == "dry_run"


def test_normalize_existing_fields_preserved():
    config = {
        "facebook_action_executor": "dry_run",
        "action_executor": {
            "name": "facebook_graphql_context",
            "verify_after_action": False,
            "fail_closed": False,
            "timeout_ms": 5000,
            "max_action_retry": 3,
        }
    }
    result = normalize_action_executor_config(config)
    ae = result["action_executor"]
    assert ae["name"] == "facebook_graphql_context"
    assert ae["verify_after_action"] is False
    assert ae["timeout_ms"] == 5000
    assert ae["max_action_retry"] == 3
    # provider fields đã bị strip
    assert "provider_enabled" not in ae
    assert "provider_url" not in ae


def test_normalize_strips_provider_fields_from_old_config():
    """Config cũ có provider_enabled/provider_url phải bị strip."""
    config = {
        "facebook_action_executor": "browser_context",
        "action_executor": {
            "name": "browser_context",
            "verify_after_action": True,
            "fail_closed": True,
            "timeout_ms": 15000,
            "max_action_retry": 0,
            "provider_enabled": True,
            "provider_url": "https://old.example.com/provider",
        }
    }
    result = normalize_action_executor_config(config)
    ae = result["action_executor"]
    assert "provider_enabled" not in ae
    assert "provider_url" not in ae


def test_normalize_invalid_action_executor_type():
    config = {
        "facebook_action_executor": "facebook_graphql_context",
        "action_executor": "invalid_string",
    }
    result = normalize_action_executor_config(config)
    assert isinstance(result["action_executor"], dict)
    assert result["action_executor"]["name"] == "facebook_graphql_context"


if __name__ == "__main__":
    import sys

    fns = [
        test_normalize_from_legacy_key_only,
        test_normalize_empty_config,
        test_normalize_unsupported_migrates_to_facebook_graphql,
        test_normalize_dry_run_preserved,
        test_normalize_existing_fields_preserved,
        test_normalize_strips_provider_fields_from_old_config,
        test_normalize_invalid_action_executor_type,
    ]
    passed = 0
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {fn.__name__}: {e}")
            failed += 1

    print(f"\nConfigMigration (non-pytest): {passed} passed, {failed} failed")
    print("  (tmp_path tests require pytest)")
    sys.exit(0 if failed == 0 else 1)
