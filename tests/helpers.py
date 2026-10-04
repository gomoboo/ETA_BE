from datetime import datetime, timedelta, timezone


def auth(guest_uuid: str) -> dict:
    return {"X-Guest-UUID": guest_uuid}


def future_iso(**delta) -> str:
    """현재로부터 delta(기본 1일) 뒤의 ISO 시각"""
    return (datetime.now(timezone.utc) + timedelta(**(delta or {"days": 1}))).isoformat()


def utc_naive(**delta) -> datetime:
    """DB 저장 형식(UTC naive)의 현재 + delta 시각"""
    return (datetime.now(timezone.utc) + timedelta(**delta)).replace(tzinfo=None)
