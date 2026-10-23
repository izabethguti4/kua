from datetime import datetime, timedelta
from typing import Tuple

def calculate_sm2(
    grade: int,
    repetitions: int,
    easiness_factor: float,
    interval_days: int
) -> Tuple[int, float, int, str]:
    """
    SuperMemo-2 (SM-2) Spaced Repetition Algorithm.
    
    Args:
        grade: Rating from 1 (forgot completely) to 5 (perfect recall).
        repetitions: Consecutive successful reviews counter.
        easiness_factor: Easiness factor (min 1.3, default 2.5).
        interval_days: Current review interval in days.
        
    Returns:
        (new_repetitions, new_easiness_factor, new_interval_days, next_review_iso)
    """
    # Clamp grade between 1 and 5
    grade = max(1, min(5, grade))
    
    if grade < 3:
        # Failure: reset repetition count and set interval to 1 day
        new_repetitions = 0
        new_interval_days = 1
    else:
        # Success: increment repetitions and compute next interval
        if repetitions == 0:
            new_interval_days = 1
        elif repetitions == 1:
            new_interval_days = 6
        else:
            new_interval_days = max(1, round(interval_days * easiness_factor))
        new_repetitions = repetitions + 1
        
    # Update easiness factor using standard SM-2 formula:
    # EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    diff = 5 - grade
    new_easiness_factor = easiness_factor + (0.1 - diff * (0.08 + diff * 0.02))
    
    # Minimum boundary for EF is 1.3
    if new_easiness_factor < 1.3:
        new_easiness_factor = 1.3
    new_easiness_factor = round(new_easiness_factor, 2)
    
    now = datetime.now()
    next_review_dt = now + timedelta(days=new_interval_days)
    next_review_iso = next_review_dt.isoformat()
    
    return new_repetitions, new_easiness_factor, new_interval_days, next_review_iso
