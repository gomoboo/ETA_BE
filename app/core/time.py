from datetime import datetime, timezone


def utcnow() -> datetime:
    """현재 UTC 시각 (DB 저장 형식에 맞춘 timezone 없는 datetime)

    datetime.utcnow()는 Python 3.12부터 지원 중단되어 대신 사용합니다.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
