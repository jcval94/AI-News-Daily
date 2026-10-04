from __future__ import annotations

import unittest
from unittest.mock import Mock

from pipeline.gdrive_bridge_io import Drive, SHEET_MIME, candidates, select


def response(body, status=200):
    result = Mock()
    result.json.return_value = body
    result.status_code = status
    return result


def sheet(file_id, suffix, created="2026-10-04T14:37:20Z"):
    return {"id": file_id, "name": "__bridge_inbox_AI-News-Daily__" + suffix, "mimeType": SHEET_MIME, "createdTime": created}


class DriveIOTests(unittest.TestCase):
    def test_daily_on_second_page_not_starved_by_other_lane(self):
        session = Mock()
        session.get.side_effect = [response({"files": [sheet(f"other-{i}", "research-weekly__2026-10-02_080000") for i in range(100)], "nextPageToken": "page-two"}), response({"files": [sheet("daily", "2026-10-04_083640")]})]
        files = Drive("token", session).list_inbox("inbox")
        self.assertEqual(select(files, "daily")["id"], "daily")
        self.assertEqual(session.get.call_args_list[1].kwargs["params"]["pageToken"], "page-two")
        self.assertIn("nextPageToken", session.get.call_args_list[0].kwargs["params"]["fields"])

    def test_empty_page_with_token_is_not_empty_inbox(self):
        session = Mock()
        session.get.side_effect = [response({"files": [], "nextPageToken": "next"}), response({"files": [sheet("daily", "2026-10-04_083640")]})]
        self.assertEqual(len(Drive("token", session).list_inbox("inbox")), 1)

    def test_repeated_token_fails_instead_of_returning_partial(self):
        session = Mock()
        session.get.return_value = response({"files": [], "nextPageToken": "same"})
        with self.assertRaisesRegex(ValueError, "repeated"):
            Drive("token", session).list_inbox("inbox")

    def test_incomplete_search_fails_closed(self):
        session = Mock()
        session.get.return_value = response({"files": [], "incompleteSearch": True})
        with self.assertRaisesRegex(ValueError, "incomplete"):
            Drive("token", session).list_inbox("inbox")

    def test_page_failure_does_not_become_idle(self):
        session = Mock()
        session.get.side_effect = [response({"files": [], "nextPageToken": "next"}), RuntimeError("read failed")]
        with self.assertRaises(RuntimeError):
            Drive("token", session).list_inbox("inbox")

    def test_mixed_lanes_route_exactly(self):
        files = [sheet("daily", "2026-10-04_083640"), sheet("weekly", "research-weekly__2026-10-02_080000"), sheet("narrative", "narrative-memory__2026-10-04_083640"), sheet("near", "2026-10-04_083640_extra")]
        for lane in ("daily", "weekly", "narrative"):
            self.assertEqual(select(files, lane)["id"], lane)
        self.assertEqual(len(candidates(files, "daily")), 1)

    def test_requested_file_never_falls_back_to_unrelated_candidate(self):
        files = [sheet("other", "2026-10-04_083640")]
        self.assertIsNone(select(files, "daily", "already-consumed"))
        self.assertEqual(select(files, "daily", "other")["id"], "other")

    def test_wrong_mime_and_near_weekly_name_rejected(self):
        wrong = {**sheet("wrong", "research-weekly__2026-10-02_080000"), "mimeType": "text/plain"}
        self.assertIsNone(select([wrong, sheet("near", "research-weekly__2026-10-02_080000_extra")], "weekly"))

    def test_raw_daily_compatibility_and_stable_oldest(self):
        raw = {"id": "raw", "name": "ai-news-daily.news.2026-10-04.083640", "mimeType": "text/plain", "createdTime": "2026-10-04T14:37:20Z"}
        files = [raw, sheet("daily", "2026-10-04_083640")]
        self.assertEqual(select(files, "daily")["id"], "daily")
        self.assertIsNone(select([raw], "weekly"))

    def test_verified_same_file_move(self):
        session = Mock()
        session.get.side_effect = [response({"id": "file", "name": "title", "parents": ["inbox"]}), response({"id": "file", "name": "processed__title", "parents": ["processed"]})]
        session.patch.return_value = response({"id": "file", "parents": ["processed"]})
        got = Drive("token", session).move_verified("file", "inbox", "processed", "title", "processed")
        self.assertEqual(got["parents"], ["processed"])
        self.assertEqual(session.get.call_count, 2)
        self.assertEqual(session.patch.call_args.kwargs["params"]["removeParents"], "inbox")
        self.assertEqual(session.patch.call_args.kwargs["params"]["addParents"], "processed")
        self.assertEqual(session.patch.call_count, 1)

    def test_http_success_with_wrong_readback_is_failure(self):
        session = Mock()
        session.get.return_value = response({"id": "file", "name": "title", "parents": ["inbox"]})
        session.patch.return_value = response({"id": "file", "parents": ["processed"]})
        with self.assertRaisesRegex(ValueError, "readback"):
            Drive("token", session).move_verified("file", "inbox", "processed", "title", "processed")
        self.assertEqual(session.patch.call_count, 1)

    def test_multiple_parents_or_changed_name_prevent_move(self):
        for before in [{"id": "file", "name": "title", "parents": ["inbox", "other"]}, {"id": "file", "name": "changed", "parents": ["inbox"]}]:
            session = Mock()
            session.get.return_value = response(before)
            with self.assertRaisesRegex(ValueError, "precondition"):
                Drive("token", session).move_verified("file", "inbox", "processed", "title", "processed")
            session.patch.assert_not_called()

    def test_repeat_after_verified_move_is_read_only(self):
        session = Mock()
        session.get.return_value = response({"id": "file", "name": "processed__title", "parents": ["processed"]})
        Drive("token", session).move_verified("file", "inbox", "processed", "title", "processed")
        session.patch.assert_not_called()

    def test_metadata_identity_mismatch_prevents_move(self):
        session = Mock()
        session.get.return_value = response({"id": "other", "name": "title", "parents": ["inbox"]})
        with self.assertRaisesRegex(ValueError, "identity"):
            Drive("token", session).move_verified("file", "inbox", "processed", "title", "processed")
        session.patch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
