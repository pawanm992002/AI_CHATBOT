"""Real-time visitor profile classification — inline via the existing LLM rewrite call.

No rules engine, no background sweep, no confidence scores, no audit history.
Classification happens once per visitor on their first substantive message,
piggybacked onto the query rewrite LLM call so there's zero added latency.
"""

from core.auth import db
from repositories.visitor_profile_repository import VisitorProfileRepository

_repo = VisitorProfileRepository()


async def get_enabled_profiles_for_classification(tenant_id: str) -> list[dict]:
    """Fetch enabled profiles (name + description only) for classification."""
    profiles = await _repo.get_enabled_by_tenant(tenant_id)
    return [{"name": p["name"], "description": p.get("description", "")} for p in profiles]


def build_profile_classification_prompt(profiles: list[dict]) -> str:
    """Build the classification portion of the rewrite prompt.

    Returns a string to append to the rewrite system prompt, asking the LLM
    to also pick the best-matching profile name (or NONE).
    """
    if not profiles:
        return ""

    profiles_text = "\n".join(
        f'- "{p["name"]}": {p["description"]}' for p in profiles
    )
    return (
        "\n\nAdditionally, classify the visitor into ONE of the following profiles "
        "based on their message content. Pick the best match, or NONE if none fit.\n"
        f"Available profiles:\n{profiles_text}\n"
        "Return your profile choice on a new line after the rewritten query, "
        "prefixed with 'PROFILE: ' (e.g. 'PROFILE: Parent' or 'PROFILE: NONE')."
    )


def parse_profile_from_rewrite_response(response: str, profiles: list[dict]) -> str | None:
    """Extract the profile name from the LLM rewrite response.

    Returns the matched profile name (case-insensitive) or None.
    """
    profile_names = {p["name"].lower(): p["name"] for p in profiles}

    for line in reversed(response.strip().split("\n")):
        line = line.strip()
        if line.upper().startswith("PROFILE:"):
            value = line[len("PROFILE:"):].strip()
            if value.upper() == "NONE" or not value:
                return None
            # Case-insensitive match against known profiles
            matched = profile_names.get(value.lower())
            if matched:
                return matched
            return None

    return None


async def classify_visitor_inline(
    tenant_id: str,
    visitor_id: str,
    profile_name: str | None,
) -> None:
    """Write the classification result to the visitor document.

    Called inline in the request path (not fire-and-forget) since the result
    needs to affect the current response's system prompt.
    """
    if profile_name:
        profile = await db.visitor_profiles.find_one(
            {"tenant_id": tenant_id, "name": profile_name, "enabled": True}
        )
        if profile:
            await db.visitors.update_one(
                {"visitor_id": visitor_id, "tenant_id": tenant_id},
                {"$set": {
                    "profile_id": profile["profile_id"],
                    "profile_label": profile["name"],
                    "profile_classification_attempted": True,
                }},
            )
            return

    # No match or profile not found — mark as attempted
    await db.visitors.update_one(
        {"visitor_id": visitor_id, "tenant_id": tenant_id},
        {"$set": {"profile_classification_attempted": True}},
    )


async def get_visitor_profile_context(session_id: str, tenant_id: str) -> str:
    """Build the profile context string for the system prompt.

    Returns a string to append to the system prompt if the visitor has a
    profile with response_instructions, or a lighter default otherwise.
    """
    try:
        visitor = await db.visitors.find_one(
            {"visitor_id": session_id, "tenant_id": tenant_id},
            {"profile_id": 1, "profile_label": 1},
        )
        if not visitor or not visitor.get("profile_id"):
            return ""

        profile = await db.visitor_profiles.find_one(
            {"profile_id": visitor["profile_id"], "tenant_id": tenant_id}
        )
        if not profile:
            return ""

        label = profile["name"]
        instructions = profile.get("response_instructions", "")

        if instructions:
            return f"\n\nThis visitor's profile: {label}. {instructions}"
        return f"\n\nThis visitor appears to be: {label}."
    except Exception:
        return ""
