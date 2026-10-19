"""Time helper module for Assurance Expiry Engine.

This is the ONLY module in the codebase allowed to call datetime.now().
"""

from __future__ import annotations

from datetime import datetime, timezone


def resolve_now(arg: str | None = None) -> datetime:
    """Resolve an ISO-8601 string or return current UTC time.

    Args:
        arg: Optional ISO-8601 formatted datetime string.

    Returns:
        A timezone-aware datetime instance representing evaluation time in UTC.
    """
    if arg is None or not arg.strip():
        return datetime.now(timezone.utc)

    normalized = arg.strip()
    if normalized.endswith("Z") or normalized.endswith("z"):
        normalized = f"{normalized[:-1]}+00:00"

    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
