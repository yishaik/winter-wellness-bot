from datetime import datetime, timedelta

from winter_wellness_bot.utils import infer_sessions, human_duration


def make_series(start: datetime, minutes: int, temp: float, step: int = 1):
    return [(start + timedelta(minutes=i), temp) for i in range(0, minutes, step)]


def test_single_session_detected_min_duration():
    t0 = datetime(2024, 1, 1, 10, 0)
    # 15 minutes at 60C should produce a single session (min 10)
    samples = make_series(t0, 15, 60.0)
    sessions = infer_sessions(samples, threshold_c=45.0, min_duration_min=10, gap_minutes=8)
    assert len(sessions) == 1
    s = sessions[0]
    assert s["minutes"] >= 10
    assert s["max_c"] == 60.0
    assert s["start"] == t0
    assert s["end"] == t0 + timedelta(minutes=14)


def test_gap_breaks_session():
    t0 = datetime(2024, 1, 1, 10, 0)
    # 6 minutes hot, then a 9-minute below-threshold gap, then hot again -> two segments, only first >= 10? No, first is 6 min so filtered out.
    hot1 = make_series(t0, 6, 50.0)
    gap = [(t0 + timedelta(minutes=6 + i), 30.0) for i in range(9)]
    hot2 = make_series(t0 + timedelta(minutes=15), 12, 52.0)
    samples = hot1 + gap + hot2
    sessions = infer_sessions(samples, threshold_c=45.0, min_duration_min=10, gap_minutes=8)
    # first segment < 10 min should be dropped; second is 12 min -> kept
    assert len(sessions) == 1
    assert sessions[0]["minutes"] >= 10
    assert sessions[0]["max_c"] == 52.0


def test_human_duration_formatting():
    assert human_duration(5) == "5ד׳"
    assert human_duration(60) == "1ש׳"
    assert human_duration(75) == "1ש׳ 15ד׳"

