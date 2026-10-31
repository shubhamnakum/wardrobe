from datetime import UTC, datetime


def utcnow_iso() -> str:
    """UTC timestamp in the same text format as the schema's server defaults."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
