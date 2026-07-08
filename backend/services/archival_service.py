import json
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

import boto3
from botocore.config import Config
from core.auth import db
from core.config import settings

MAX_TURNS = 30
ARCHIVE_PART_SIZE_BYTES = 512_000


_pending: set[str] = set()


def _get_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.DO_SPACES_ENDPOINT,
        aws_access_key_id=settings.DO_SPACES_ACCESS_KEY,
        aws_secret_access_key=settings.DO_SPACES_SECRET_KEY,
        config=Config(s3={"addressing_style": "virtual"}),
    )


def _archive_key(tenant_id: str, conversation_id: str, part: int = 1) -> str:
    return f"conversations/{tenant_id}/{conversation_id}/archive_{part:04d}.jsonl"


class ArchivalService:
    """
    Hot/Cold conversation storage.

    Strategy: read-merge-write with true size-bounded parts.
    - DO Spaces does NOT support atomic append (no append_object API).
    - Before each write, we read any existing content at the target part key,
      append the new JSONL lines, and re-upload the combined body.  This
      read-merge-write approach ensures previously archived turns are never
      silently overwritten.
    - If the merged body exceeds ARCHIVE_PART_SIZE_BYTES (512KB), we roll to
      the next sequential part number instead of overwriting. This bounds
      per-request upload size while preventing silent data loss.
    - The same size check applies even to a fresh (empty) part: if the inbound
      batch is itself larger than 512KB, it is chunked across multiple parts.
    - The current part number is tracked in ``archive_current_part`` (default 1)
      in the conversation document, not derived from message counts.  This
      eliminates the decoupled-count problem where the count-based hint skips
      ahead of the physically written part number, creating unreachable gaps.
    - ``get_full_conversation()`` uses ``list_objects_v2`` with prefix matching
      to enumerate all existing parts, making it resilient to gaps regardless
      of cause.
    """

    async def _append_to_archive_part(
        self, tenant_id: str, conversation_id: str, start_part: int, new_lines: list[str]
    ) -> int:
        """
        Write new JSONL lines to an archive part, merging with existing content.

        Reads any existing content at the target part key, appends new lines,
        and re-uploads the combined body.  If the merged content exceeds
        ARCHIVE_PART_SIZE_BYTES, increments the part number until a suitable
        part is found (either empty or with room to append).

        The size check applies unconditionally — even to a fresh (empty) part.
        If the inbound batch alone exceeds the threshold, it is split across
        sequential parts.

        Returns the final part number written to (may differ from start_part
        due to size rollover or chunking).  Callers must persist this value
        in MongoDB as ``archive_current_part``.
        """
        client = _get_client()
        part = start_part

        line_idx = 0
        while line_idx < len(new_lines):
            key = _archive_key(tenant_id, conversation_id, part)
            existing = b""
            try:
                resp = client.get_object(
                    Bucket=settings.DO_SPACES_BUCKET,
                    Key=key,
                )
                existing = resp["Body"].read()
            except client.exceptions.NoSuchKey:
                pass

            # Collect as many lines as fit under the threshold when combined
            # with existing content.
            batch = []
            batch_size = len(existing)
            while line_idx < len(new_lines):
                line_bytes = (new_lines[line_idx] + "\n").encode("utf-8")
                if batch_size + len(line_bytes) > ARCHIVE_PART_SIZE_BYTES:
                    break
                batch.append(new_lines[line_idx])
                batch_size += len(line_bytes)
                line_idx += 1

            if not batch:
                if existing:
                    # Existing part is already at/near capacity — roll to the
                    # next part without consuming any lines.
                    part += 1
                    continue
                # Fresh (empty) part but the current line alone exceeds the
                # threshold.  Write it anyway to guarantee line_idx always
                # advances — otherwise the outer loop retries the same line
                # on every subsequent part forever, a hard hang.
                body_bytes = (new_lines[line_idx] + "\n").encode("utf-8")
                client.put_object(
                    Bucket=settings.DO_SPACES_BUCKET,
                    Key=key,
                    Body=body_bytes,
                    ContentType="application/jsonl",
                )
                line_idx += 1
                part += 1
                continue

            body_bytes = ("\n".join(batch) + "\n").encode("utf-8")
            body = existing + body_bytes if existing else body_bytes

            client.put_object(
                Bucket=settings.DO_SPACES_BUCKET,
                Key=key,
                Body=body,
                ContentType="application/jsonl",
            )

            if line_idx < len(new_lines):
                part += 1

        return part

    async def archive_overflow_turns(
        self, conversation_id: str, tenant_id: str
    ) -> None:
        """
        Fire-and-forget: check if conversation has > MAX_TURNS * 2 individual messages.
        If so, pop the oldest messages beyond the most recent MAX_TURNS * 2,
        append to DO Spaces archive, then trim MongoDB messages array.
        MAX_TURNS = 30 means 30 conversation turns = 60 individual messages.
        Compaction (summary builder) runs first and trims to 30; archival is a
        safety net that fires only if the array exceeds 60 (e.g. compaction skip).
        """
        key = f"{tenant_id}:{conversation_id}"
        if key in _pending:
            return  # Archival already in progress — skip
        _pending.add(key)
        try:
            await self._archive_overflow_inner(conversation_id, tenant_id)
        except Exception as e:
            print(f"[ARCHIVAL] Error archiving conversation {conversation_id}: {e}")
        finally:
            _pending.discard(key)

    async def _archive_overflow_inner(
        self, conversation_id: str, tenant_id: str
    ) -> None:
        conv = await db.conversations.find_one(
            {"session_id": conversation_id, "tenant_id": tenant_id}
        )
        if not conv:
            return

        messages = conv.get("messages", [])
        turn_count = len(messages)

        if turn_count <= MAX_TURNS * 2:
            return

        turns_to_archive = turn_count - MAX_TURNS * 2
        turns_to_keep = messages[-(MAX_TURNS * 2):]
        turns_to_move = messages[:turns_to_archive]

        lines = []
        for i in range(0, len(turns_to_move), 2):
            if i + 1 < len(turns_to_move):
                turn = {
                    "user": turns_to_move[i].get("content", ""),
                    "assistant": turns_to_move[i + 1].get("content", ""),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                lines.append(json.dumps(turn))

        if not lines:
            return

        archive_part = conv.get("archive_current_part", 1)
        final_part = await self._append_to_archive_part(tenant_id, conversation_id, archive_part, lines)

        archived_previously = conv.get("archived_turn_count", 0)
        new_archived_count = archived_previously + len(turns_to_move)

        set_fields = {
            "messages": turns_to_keep,
            "archived": True,
            "archived_turn_count": new_archived_count,
            "archive_current_part": final_part,
            "updated_at": datetime.now(timezone.utc),
        }

        await db.conversations.update_one(
            {"session_id": conversation_id, "tenant_id": tenant_id},
            {"$set": set_fields},
        )
        print(
            f"[ARCHIVAL] Archived {len(turns_to_move)} turns for {conversation_id} "
            f"(part starting at {archive_part}). Total archived: {new_archived_count}"
        )

    async def archive_entire_session(self, conversation_id: str, tenant_id: str) -> None:
        """
        Archive all messages of a session/conversation to DO Spaces,
        setting messages to [] in MongoDB to free up hot database space.
        """
        key = f"{tenant_id}:{conversation_id}"
        if key in _pending:
            return
        _pending.add(key)
        try:
            conv = await db.conversations.find_one(
                {"session_id": conversation_id, "tenant_id": tenant_id}
            )
            if not conv:
                return
            messages = conv.get("messages", [])
            if not messages:
                return

            lines = []
            for i in range(0, len(messages), 2):
                if i + 1 < len(messages):
                    turn = {
                        "user": messages[i].get("content", ""),
                        "assistant": messages[i + 1].get("content", ""),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    lines.append(json.dumps(turn))
                elif i < len(messages):
                    turn = {
                        "user": messages[i].get("content", ""),
                        "assistant": "",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    lines.append(json.dumps(turn))

            if not lines:
                return

            archive_part = conv.get("archive_current_part", 1)
            final_part = await self._append_to_archive_part(tenant_id, conversation_id, archive_part, lines)

            archived_previously = conv.get("archived_turn_count", 0)
            new_archived_count = archived_previously + len(messages)

            set_fields = {
                "messages": [],
                "archived": True,
                "archived_turn_count": new_archived_count,
                "archive_current_part": final_part,
                "updated_at": datetime.now(timezone.utc),
            }

            await db.conversations.update_one(
                {"session_id": conversation_id, "tenant_id": tenant_id},
                {"$set": set_fields},
            )
            print(f"[ARCHIVAL] Entire session {conversation_id} archived. Total turns: {new_archived_count}")
        except Exception as e:
            print(f"[ARCHIVAL] Error archiving entire session {conversation_id}: {e}")
        finally:
            _pending.discard(key)

    async def get_full_conversation(
        self, conversation_id: str, tenant_id: str
    ) -> Optional[Dict[str, Any]]:
        conv = await db.conversations.find_one(
            {"session_id": conversation_id, "tenant_id": tenant_id},
            {"_id": 0},
        )
        if not conv:
            return None

        if not conv.get("archived"):
            return conv

        archived_turns = []
        client = _get_client()

        # Enumerate all existing archive parts via list_objects_v2 so we are
        # resilient to gaps in part numbering (e.g. if a part was deleted or
        # the old count-derived hint skipped ahead).  Sorting by key is safe
        # because zero-padded part numbers sort lexicographically.
        prefix = f"conversations/{tenant_id}/{conversation_id}/archive_"
        try:
            paginator = client.get_paginator("list_objects_v2")
            page_iter = paginator.paginate(
                Bucket=settings.DO_SPACES_BUCKET,
                Prefix=prefix,
            )
            keys: list[str] = []
            for page in page_iter:
                contents = page.get("Contents", [])
                for obj in contents:
                    key = obj["Key"]
                    if key.endswith(".jsonl"):
                        keys.append(key)
            keys.sort()
        except Exception as e:
            print(f"[ARCHIVAL] Error listing archive parts for {conversation_id}: {e}")
            keys = []

        for key in keys:
            try:
                resp = client.get_object(
                    Bucket=settings.DO_SPACES_BUCKET,
                    Key=key,
                )
                body = resp["Body"].read().decode("utf-8")
                for line in body.strip().split("\n"):
                    if line.strip():
                        turn = json.loads(line)
                        archived_turns.append({
                            "role": "user",
                            "content": turn["user"],
                        })
                        archived_turns.append({
                            "role": "assistant",
                            "content": turn["assistant"],
                        })
            except Exception as e:
                print(f"[ARCHIVAL] Error reading archive part {key}: {e}")

        conv["full_messages"] = archived_turns + conv.get("messages", [])
        return conv


archival_service = ArchivalService()