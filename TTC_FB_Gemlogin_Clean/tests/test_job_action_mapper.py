# -*- coding: utf-8 -*-
"""Test JobActionMapper — chuẩn hóa job dict thành NormalizedAction."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from action_executors.job_action_mapper import JobActionMapper, NormalizedAction


class TestJobActionMapper:
    def setup_method(self):
        self.mapper = JobActionMapper()

    def test_normalize_full_job_dict(self):
        job = {
            "job_id": "JOB001",
            "action_group": "reaction",
            "link": "https://www.facebook.com/post/123",
            "idpost": "POST_123",
            "reaction_type": "LOVE",
            "comment_text": "",
        }
        result = self.mapper.normalize(job)
        assert result.job_id == "JOB001"
        assert result.action_group == "reaction"
        assert result.target_url == "https://www.facebook.com/post/123"
        assert result.target_id == "POST_123"
        assert result.reaction_type == "LOVE"
        assert result.comment_text == ""
        assert result.raw_job == job

    def test_normalize_comment_job(self):
        job = {
            "id": "JOB_COMMENT",
            "job_type": "ttc_comment",
            "url": "https://fb.com/999",
            "object_id": "OBJ_999",
            "noidung": "Thật tuyệt vời!",
        }
        result = self.mapper.normalize(job)
        assert result.action_group == "ttc_comment"
        assert result.target_url == "https://fb.com/999"
        assert result.target_id == "OBJ_999"
        assert result.comment_text == "Thật tuyệt vời!"

    def test_normalize_reaction_with_camxuc(self):
        job = {
            "id": "777",
            "type": "reaction",
            "link": "https://fb.com/777",
            "idpost": "777",
            "camxuc": "HAHA",
        }
        result = self.mapper.normalize(job)
        assert result.reaction_type == "HAHA"
        assert result.action_group == "reaction"

    def test_normalize_empty_job(self):
        result = self.mapper.normalize({})
        assert result.job_id == ""
        assert result.action_group == ""
        assert result.target_url == ""
        assert result.target_id == ""
        assert isinstance(result, NormalizedAction)

    def test_normalize_action_group_lowercase(self):
        job = {"action_group": "REACTION", "id": "X"}
        result = self.mapper.normalize(job)
        assert result.action_group == "reaction"

    def test_normalize_object_with_raw_data_attr(self):
        class FakeJob:
            buff_id = "BUFF_888"
            raw_data = {
                "action_group": "follow",
                "link": "https://fb.com/user888",
                "idpost": "user888",
            }
        result = self.mapper.normalize(FakeJob())
        assert result.action_group == "follow"
        assert result.target_url == "https://fb.com/user888"
        assert result.job_id == "BUFF_888"


def run_tests():
    t = TestJobActionMapper()
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
    print(f"\nJobActionMapper: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
