from datetime import datetime, timedelta

from health_log.analysis.models import TimeWindow


def resolve_window_range(window: TimeWindow, now: datetime) -> tuple[datetime, datetime]:
    if window == TimeWindow.NIGHT:
        end = now
        start = now - timedelta(hours=12)
        return start, end
    if window == TimeWindow.WEEK:
        end = now
        start = now - timedelta(days=7)
        return start, end
    end = now
    start = now - timedelta(days=30)
    return start, end
