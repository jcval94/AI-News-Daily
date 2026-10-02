import unittest

from pipeline.tts.release_store import (
    preview_release_tags_to_delete,
)


class ReleaseRetentionTests(unittest.TestCase):
    def test_preview_release_gc_keeps_exact_bound_including_current(self):
        releases = [
            {
                "tagName": "tts-preview-2026-09-28-a",
                "createdAt": "2026-09-28T10:00:00Z",
            },
            {
                "tagName": "tts-preview-2026-09-29-b",
                "createdAt": "2026-09-29T10:00:00Z",
            },
            {
                "tagName": "tts-preview-2026-09-30-c",
                "createdAt": "2026-09-30T10:00:00Z",
            },
            {
                "tagName": "tts-preview-2026-10-01-d",
                "createdAt": "2026-10-01T10:00:00Z",
            },
            {
                "tagName": "not-tts",
                "createdAt": "2026-10-02T10:00:00Z",
            },
        ]
        deleted = preview_release_tags_to_delete(
            releases,
            prefix="tts-preview-",
            keep=3,
            current_tag="tts-preview-2026-10-01-d",
        )
        self.assertEqual(
            deleted,
            ["tts-preview-2026-09-28-a"],
        )

    def test_current_release_counts_toward_bound_even_if_older(self):
        releases = [
            {
                "tagName": "tts-preview-current",
                "createdAt": "2026-01-01T00:00:00Z",
            },
            {
                "tagName": "tts-preview-new",
                "createdAt": "2026-10-01T00:00:00Z",
            },
        ]
        deleted = preview_release_tags_to_delete(
            releases,
            prefix="tts-preview-",
            keep=1,
            current_tag="tts-preview-current",
        )
        self.assertEqual(
            deleted,
            ["tts-preview-new"],
        )

    def test_keep_must_be_positive(self):
        with self.assertRaisesRegex(ValueError, "keep"):
            preview_release_tags_to_delete(
                [],
                prefix="tts-preview-",
                keep=0,
                current_tag="tts-preview-current",
            )


if __name__ == "__main__":
    unittest.main()
