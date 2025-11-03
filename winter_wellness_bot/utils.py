from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any


def human_duration(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    if h and m:
        return f"{h}ש׳ {m}ד׳"
    if h:
        return f"{h}ש׳"
    return f"{m}ד׳"


def infer_sessions(
    samples: List[Tuple[datetime, float]],
    threshold_c: float = 45.0,
    min_duration_min: int = 10,
    gap_minutes: int = 8,
) -> List[Dict[str, Any]]:
    """
    Detect sauna sessions from (datetime, tempC) samples.
    - A session starts when temp >= threshold.
    - It continues as long as subsequent samples either stay >= threshold
      or the gap between samples is < gap_minutes.
    - A session ends when a gap >= gap_minutes occurs while below threshold.
    - Only sessions with duration >= min_duration_min are returned.
    Returns list of dicts: {start, end, max_c, minutes} sorted by time.
    """
    sessions: List[Dict[str, Any]] = []
    active: Dict[str, Any] | None = None
    last_t: datetime | None = None

    for t, temp in samples:
        if temp >= threshold_c:
            if active is None:
                active = {"start": t, "end": t, "max_c": temp}
            else:
                active["end"] = t
                active["max_c"] = max(active["max_c"], temp)
        else:
            if active:
                if last_t and (t - last_t) > timedelta(minutes=gap_minutes):
                    dur = (active["end"] - active["start"]).total_seconds() / 60.0
                    if dur >= min_duration_min:
                        active["minutes"] = int(dur)
                        sessions.append(active)
                    active = None
        last_t = t

    if active:
        dur = (active["end"] - active["start"]).total_seconds() / 60.0
        if dur >= min_duration_min:
            active["minutes"] = int(dur)
            sessions.append(active)

    return sessions

