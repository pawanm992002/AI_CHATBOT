import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

import boto3
from botocore.config import Config
from core.auth import db
from core.config import settings

MAX_TURNS = 20


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

    Design tradeoff:
    - DO Spaces does NOT support true append (no append_object API).
    - Two strategies considered:
      1) Read-modify-write: download the full archive, append new line(s), re-upload.
         Simple but wasteful for large archives (upload cost grows with archive size).
      2) Rolling numbered parts: once a part exceeds ARCHIVE_PART_SIZE bytes,
         start a new part. Each part is immutable once sealed.
         Writes stay small and cheap regardless of total history size.
    - We choose strategy 2 (rolling parts) to keep write costs low and bounded.
      The `archive_part` counter is derived from `archived_turn_count // (MAX_TURNS * 2)`
      where archived_turn_count stores individual message count.
    """

    async def archive_overflow_turns(
        self, conversation_id: str, tenant_id: str
    ) -> None:
        """
        Fire-and-forget: check if conversation has > MAX_TURNS * 2 individual messages.
        If so, pop the oldest messages beyond the most recent MAX_TURNS * 2,
        append to DO Spaces archive, then trim MongoDB messages array.
        MAX_TURNS = 20 means 20 conversation turns = 40 individual messages.
        Compaction (summary builder) runs first; archival is the sole array trimmer.
        """
        try:
            await self._archive_overflow_inner(conversation_id, tenant_id)
        except Exception as e:
            print(f"[ARCHIVAL] Error archiving conversation {conversation_id}: {e}")

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

        archive_part = conv.get("archived_turn_count", 0) // (MAX_TURNS * 2) + 1

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

        key = _archive_key(tenant_id, conversation_id, archive_part)
        client = _get_client()
        body = "\n".join(lines) + "\n"

        client.put_object(
            Bucket=settings.DO_SPACES_BUCKET,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="application/jsonl",
        )

        archived_previously = conv.get("archived_turn_count", 0)
        new_archived_count = archived_previously + len(turns_to_move)

        await db.conversations.update_one(
            {"session_id": conversation_id, "tenant_id": tenant_id},
            {
                "$set": {
                    "messages": turns_to_keep,
                    "archived": True,
                    "archived_turn_count": new_archived_count,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        print(
            f"[ARCHIVAL] Archived {len(turns_to_move)} turns for {conversation_id} "
            f"to {key}. Total archived: {new_archived_count}"
        )

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
        part = 1
        while True:
            key = _archive_key(tenant_id, conversation_id, part)
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
                part += 1
            except client.exceptions.NoSuchKey:
                break
            except Exception as e:
                print(f"[ARCHIVAL] Error reading archive part {key}: {e}")
                break

        conv["full_messages"] = archived_turns + conv.get("messages", [])
        return conv


archival_service = ArchivalService()