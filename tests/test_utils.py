from datetime import datetime

from health_log.utils import utcnow


def test_utcnow_returns_datetime():
    result = utcnow()
    assert isinstance(result, datetime)


def test_utcnow_returns_naive():
    """tzinfo must be None — all DB columns are naive UTC."""
    result = utcnow()
    assert result.tzinfo is None


def test_utcnow_is_close_to_now():
    import time
    before = datetime.utcnow()
    time.sleep(0.01)
    result = utcnow()
    time.sleep(0.01)
    after = datetime.utcnow()
    assert before <= result <= after
