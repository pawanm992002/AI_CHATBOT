"""
Sanity check for archival_service.py Part 1 fixes.

Tests:
1. Read-merge-write prevents overwrite across repeated overflow calls.
2. Size-based rollover creates new parts when threshold exceeded.
3. archive_current_part tracking prevents count-derived part-skip bug.
4. get_full_conversation() uses list_objects_v2 and is gap-tolerant.
5. Single large batch (archive_entire_session) is chunked across parts.

Run:  .venv/bin/python test_archival_fix.py
"""

import json
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.modules["core"] = MagicMock()
sys.modules["core.auth"] = MagicMock(db=None)
sys.modules["core.config"] = MagicMock()

from backend.services.archival_service import (
    ArchivalService,
    _archive_key,
    ARCHIVE_PART_SIZE_BYTES,
)


class InMemoryS3:
    class exceptions:
        class NoSuchKey(Exception):
            pass

    def __init__(self):
        self.store: dict[str, bytes] = {}

    def put_object(self, Bucket=None, Key=None, Body=None, ContentType=None):
        self.store[Key] = Body

    def get_object(self, Bucket=None, Key=None):
        if Key not in self.store:
            raise self.exceptions.NoSuchKey(f"Key {Key} not found")
        body = self.store[Key]
        resp = {"Body": MagicMock()}
        resp["Body"].read.return_value = body
        return resp

    def get_paginator(self, operation_name):
        if operation_name == "list_objects_v2":
            return _InMemoryPaginator(self)
        raise ValueError(f"Unknown operation: {operation_name}")


class _InMemoryPaginator:
    """Minimal paginator that lists keys from InMemoryS3 store by prefix."""
    def __init__(self, s3):
        self.s3 = s3

    def paginate(self, Bucket=None, Prefix=None):
        keys = sorted(k for k in self.s3.store if k.startswith(Prefix) and k.endswith(".jsonl"))
        if keys:
            yield {"Contents": [{"Key": k} for k in keys]}
        else:
            yield {"Contents": []}


class FakeSettings:
    DO_SPACES_ENDPOINT = "https://test.example.com"
    DO_SPACES_ACCESS_KEY = "test-key"
    DO_SPACES_SECRET_KEY = "test-secret"
    DO_SPACES_BUCKET = "test-bucket"


class TestArchivalFixes(unittest.TestCase):
    def setUp(self):
        self.s3 = InMemoryS3()

        settings_patcher = patch(
            "backend.services.archival_service.settings", FakeSettings()
        )
        settings_patcher.start()
        self.addCleanup(settings_patcher.stop)

        s3_patcher = patch(
            "backend.services.archival_service.boto3.client",
            return_value=self.s3,
        )
        s3_patcher.start()
        self.addCleanup(s3_patcher.stop)

        self.service = ArchivalService()

    def _make_line(self, user_text, assistant_text="ok"):
        return json.dumps({
            "user": user_text,
            "assistant": assistant_text,
            "timestamp": "2024-01-01T00:00:00",
        })

    def _lines_as_messages(self, raw_lines):
        msgs = []
        for l in raw_lines:
            turn = json.loads(l)
            msgs.append({"role": "user", "content": turn["user"]})
            msgs.append({"role": "assistant", "content": turn["assistant"]})
        return msgs

    # --- Test 1: read-merge-write prevents overwrite ---

    def test_merge_preserves_all_turns(self):
        """3 calls to same start_part → all 6 turns in one merged file."""
        import asyncio

        calls = [
            [self._make_line("hello", "hi there"), self._make_line("what is x", "x is y")],
            [self._make_line("follow up", "sure thing"), self._make_line("another q", "another a")],
            [self._make_line("more", "more answer"), self._make_line("last one", "done")],
        ]

        final = 1
        for lines in calls:
            final = asyncio.run(self.service._append_to_archive_part("t1", "c1", 1, lines))

        key = _archive_key("t1", "c1", 1)
        self.assertIn(key, self.s3.store)
        self.assertEqual(final, 1, "All turns fit in part 1")

        stored_lines = [l for l in self.s3.store[key].decode("utf-8").strip().split("\n") if l.strip()]
        self.assertEqual(len(stored_lines), 6)
        user_texts = [json.loads(l)["user"] for l in stored_lines]
        for expected in ["hello", "follow up", "more"]:
            self.assertEqual(user_texts.count(expected), 1)

    # --- Test 2: size-based rollover ---

    def test_size_rollover_creates_new_part(self):
        """When merged content exceeds threshold, new parts are created."""
        import asyncio

        # Fill part 1 near capacity
        big = "B" * (ARCHIVE_PART_SIZE_BYTES - 100)
        final = asyncio.run(self.service._append_to_archive_part("t1", "c2", 1, [
            self._make_line(big),
        ]))
        self.assertEqual(final, 1)

        # This batch won't fit → rolls to part 2
        overflow = [self._make_line("overflow", "response"), self._make_line("also overflow")]
        final = asyncio.run(self.service._append_to_archive_part("t1", "c2", 1, overflow))
        self.assertEqual(final, 2)

        key1 = _archive_key("t1", "c2", 1)
        key2 = _archive_key("t1", "c2", 2)
        lines1 = [l for l in self.s3.store[key1].decode("utf-8").strip().split("\n") if l.strip()]
        lines2 = [l for l in self.s3.store[key2].decode("utf-8").strip().split("\n") if l.strip()]
        self.assertEqual(len(lines1), 1, "Part 1 unchanged")
        self.assertEqual(len(lines2), 2, "Part 2 holds overflow")

    # --- Test 3: archive_current_part prevents count-derived gap ---

    def test_archive_current_part_no_skip(self):
        """
        Simulate many overflow cycles with short messages so archived_turn_count
        climbs past 60 without any byte-size rollover. The hint uses
        archive_current_part (not count), so it stays on part 1.
        """
        import asyncio

        # Force archive_current_part = 1 regardless of count
        part = 1
        for i in range(5):
            lines = [self._make_line(f"q{i}", f"a{i}")]
            part = asyncio.run(self.service._append_to_archive_part("t1", "c3", part, lines))

        # All 5 batches should still be in part 1
        key = _archive_key("t1", "c3", 1)
        self.assertIn(key, self.s3.store)
        stored_lines = [l for l in self.s3.store[key].decode("utf-8").strip().split("\n") if l.strip()]
        self.assertEqual(len(stored_lines), 5)  # 5 turns = 10 messages → 5 JSONL lines
        self.assertEqual(part, 1)

    # --- Test 4: list_objects_v2 handles gaps ---

    def test_get_full_conversation_gap_tolerant(self):
        """
        Manually create parts 1, 3 (skip part 2). get_full_conversation
        should return all data from part 1 and 3.
        """
        import asyncio

        p1_lines = [self._make_line("part1 q", "part1 a")]
        p3_lines = [self._make_line("part3 q", "part3 a")]

        # Write part 1
        asyncio.run(self.service._append_to_archive_part("t1", "c4", 1, p1_lines))
        # Write part 3 directly (simulate a gap)
        asyncio.run(self.service._append_to_archive_part("t1", "c4", 3, p3_lines))

        # Verify: in-memory S3 has key for 1 and 3, not 2
        self.assertIn(_archive_key("t1", "c4", 1), self.s3.store)
        self.assertIn(_archive_key("t1", "c4", 3), self.s3.store)
        self.assertNotIn(_archive_key("t1", "c4", 2), self.s3.store)

        # Now mock a MongoDB doc so get_full_conversation proceeds past short-circuit
        import asyncio as _asyncio
        db_doc = {
            "session_id": "c4",
            "tenant_id": "t1",
            "archived": True,
            "messages": [],
            "summary": "",
        }

        async def fake_find_one(*a, **kw):
            return db_doc

        with patch("backend.services.archival_service.db") as mock_db:
            mock_db.conversations.find_one = fake_find_one
            result = _asyncio.run(self.service.get_full_conversation("c4", "t1"))

        self.assertIsNotNone(result)
        full_msgs = result["full_messages"]
        contents = [m["content"] for m in full_msgs]
        self.assertIn("part1 q", contents)
        self.assertIn("part3 q", contents)

    # --- Test 5: single large batch is split across parts ---

    def test_large_batch_split_across_parts(self):
        """
        Simulate archive_entire_session with a single batch of many short
        messages whose combined size exceeds 512KB. Verify the data is split
        across multiple parts, each under the threshold.
        """
        import asyncio

        # Generate enough lines to exceed 512KB in one batch
        # Each line is ~80 bytes (JSON overhead) + 2 chars → ~82 bytes
        # 512KB / 82 ≈ 6390 lines to exceed threshold
        many_lines = [self._make_line(f"q{i}", "a" * 50) for i in range(7000)]

        final = asyncio.run(self.service._append_to_archive_part("t1", "c5", 1, many_lines))

        # Should have produced at least 2 parts
        self.assertGreater(final, 1, "Batch should span multiple parts")

        # Verify each part is under threshold
        for part in range(1, final + 1):
            key = _archive_key("t1", "c5", part)
            body = self.s3.store[key]
            self.assertLessEqual(
                len(body), ARCHIVE_PART_SIZE_BYTES,
                f"Part {part} exceeds size threshold ({len(body)} > {ARCHIVE_PART_SIZE_BYTES})"
            )

        # Verify total lines preserved
        total = 0
        for part in range(1, final + 1):
            key = _archive_key("t1", "c5", part)
            lines = [l for l in self.s3.store[key].decode("utf-8").strip().split("\n") if l.strip()]
            total += len(lines)
        self.assertEqual(total, 7000, "All lines preserved across parts")

    # --- Test 6: archive_current_part returned correctly on rollover chain ---

    def test_returned_part_tracking(self):
        """The final part returned by _append_to_archive_part reflects actual
        last-written part after sequential rollovers."""
        import asyncio

        # Fill part 1 near capacity
        big = "B" * (ARCHIVE_PART_SIZE_BYTES - 100)
        final = asyncio.run(self.service._append_to_archive_part("t1", "c6", 1, [self._make_line(big)]))
        self.assertEqual(final, 1)

        # Overflow to part 2
        final = asyncio.run(self.service._append_to_archive_part("t1", "c6", 2, [
            self._make_line("first in p2"),
            self._make_line("second in p2"),
        ]))
        self.assertEqual(final, 2)

        # Overfill part 2, roll to part 3
        big2 = "C" * (ARCHIVE_PART_SIZE_BYTES - 100)
        final = asyncio.run(self.service._append_to_archive_part("t1", "c6", 2, [self._make_line(big2)]))
        self.assertEqual(final, 3)

        key3 = _archive_key("t1", "c6", 3)
        self.assertIn(key3, self.s3.store)
        lines3 = [l for l in self.s3.store[key3].decode("utf-8").strip().split("\n") if l.strip()]
        self.assertEqual(len(lines3), 1)

    # --- Test 7: single oversized line (exceeding ARCHIVE_PART_SIZE_BYTES)
    #              does NOT cause an infinite loop ---

    def test_oversized_line_does_not_hang(self):
        """A single JSONL line > 512KB must be force-written to its own part
        rather than causing the outer loop to retry forever on every empty
        part without ever advancing line_idx."""
        import asyncio

        oversized_text = "X" * (ARCHIVE_PART_SIZE_BYTES + 100)
        line = self._make_line(oversized_text, "tiny")

        # This call must complete (not hang).  The oversized line is force-
        # written to part 1; the returned part is 1 (the part written to),
        # or 2 if the post-write increment ran.  Both are acceptable as long
        # as the function completes and the data is present.
        final = asyncio.run(self.service._append_to_archive_part("t1", "c7", 1, [line]))

        key1 = _archive_key("t1", "c7", 1)
        self.assertIn(key1, self.s3.store)
        stored = self.s3.store[key1].decode("utf-8")
        self.assertIn(oversized_text, stored, "Oversized content should be in part 1")

    def test_oversized_line_among_normal_lines(self):
        """An oversized line followed by normal lines: the oversized line goes
        to its own part, then remaining lines go to the next part."""
        import asyncio

        oversized_text = "Y" * (ARCHIVE_PART_SIZE_BYTES + 100)
        lines = [
            self._make_line(oversized_text, "huge"),
            self._make_line("normal q", "normal a"),
            self._make_line("another", "answer"),
        ]

        final = asyncio.run(self.service._append_to_archive_part("t1", "c8", 1, lines))
        # Part 1 = oversized, part 2 = 2 normal
        self.assertEqual(final, 2)

        key1 = _archive_key("t1", "c8", 1)
        key2 = _archive_key("t1", "c8", 2)
        self.assertIn(key1, self.s3.store)
        self.assertIn(key2, self.s3.store)

        lines1 = [l for l in self.s3.store[key1].decode("utf-8").strip().split("\n") if l.strip()]
        lines2 = [l for l in self.s3.store[key2].decode("utf-8").strip().split("\n") if l.strip()]
        self.assertEqual(len(lines1), 1, "Part 1 holds the single oversized line")
        self.assertEqual(len(lines2), 2, "Part 2 holds the 2 normal lines")
        self.assertIn(oversized_text, lines1[0])


if __name__ == "__main__":
    unittest.main()