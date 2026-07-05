# -*- coding: utf-8 -*-
"""Test ActionResultParser — parse response thành FacebookActionResult."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json

from action_executors.result_parser import ActionResultParser
from action_executors.job_action_mapper import JobActionMapper


def _make_job(action_group="reaction", idpost="POST1"):
    return {
        "action_group": action_group,
        "idpost": idpost,
        "link": f"https://fb.com/{idpost}",
    }


def _make_response(ok=True, status=200, text=""):
    return {
        "ok": ok,
        "status": status,
        "statusText": "OK" if ok else "Error",
        "url": "https://example.com/provider",
        "text": text,
    }


class TestActionResultParser:
    def setup_method(self):
        self.parser = ActionResultParser()
        self.mapper = JobActionMapper()

    def _norm(self, job):
        return self.mapper.normalize(job)

    def test_success_verified_json(self):
        job = _make_job()
        response = _make_response(text=json.dumps({"success": True, "verified": True, "evidence": "ok"}))
        result = self.parser.parse(job=job, normalized=self._norm(job), response=response)
        assert result.success is True
        assert result.verified is True
        assert result.reason == "ACTION_VERIFIED"

    def test_success_but_not_verified(self):
        job = _make_job()
        response = _make_response(text=json.dumps({"success": True, "verified": False}))
        result = self.parser.parse(job=job, normalized=self._norm(job), response=response)
        assert result.success is False
        assert result.verified is False
        assert result.reason == "ACTION_NOT_VERIFIED"

    def test_both_false(self):
        job = _make_job()
        response = _make_response(text=json.dumps({"success": False, "verified": False, "reason": "LIMIT_EXCEEDED"}))
        result = self.parser.parse(job=job, normalized=self._norm(job), response=response)
        assert result.success is False
        assert result.reason == "LIMIT_EXCEEDED"

    def test_http_error_response(self):
        job = _make_job()
        response = _make_response(ok=False, status=500, text="Internal Server Error")
        result = self.parser.parse(job=job, normalized=self._norm(job), response=response)
        assert result.success is False
        assert "status=500" in result.evidence

    def test_plain_text_response_not_verified(self):
        job = _make_job()
        response = _make_response(text="success")  # text thường, không phải JSON
        result = self.parser.parse(job=job, normalized=self._norm(job), response=response)
        assert result.success is False
        assert result.reason == "ACTION_NOT_VERIFIED"

    def test_empty_text_response(self):
        job = _make_job()
        response = _make_response(text="")
        result = self.parser.parse(job=job, normalized=self._norm(job), response=response)
        assert result.success is False

    def test_response_not_dict(self):
        job = _make_job()
        result = self.parser.parse(job=job, normalized=self._norm(job), response="not_a_dict")
        assert result.success is False
        assert "not a dict" in result.evidence.lower()

    def test_verified_with_custom_evidence(self):
        job = _make_job()
        response = _make_response(text=json.dumps({
            "success": True, "verified": True, "evidence": "Post reacted successfully"
        }))
        result = self.parser.parse(job=job, normalized=self._norm(job), response=response)
        assert result.success is True
        assert "Post reacted" in result.evidence


def run_tests():
    t = TestActionResultParser()
    tests = [m for m in dir(t) if m.startswith("test_")]
    passed = 0
    failed = 0
    for name in tests:
        t.setup_method()
        try:
            getattr(t, name)()
            print(f"  PASS  {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1
    print(f"\nActionResultParser: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
