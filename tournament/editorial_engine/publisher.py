"""
publisher.py
------------
Role 4: Publisher for Daily Gazette Editorial Engine.

Responsible for:
1. Receiving candidate events from the Reporter.
2. Allocating slots: HEADLINE (Rank #1 event), EVENT 2 (Rank #2), and EVENT 3 (Rank #3).
3. Selecting layout format (STANDARD_COLUMN, WINNERS_LOSERS, INTERVIEW, PUB_QUOTES).
"""

import random

FORMAT_TYPES = [
    'STANDARD_COLUMN',
    'WINNERS_LOSERS',
    'INTERVIEW',
    'PUB_QUOTES'
]


class Publisher:
    """
    Publisher component that determines layout format and allocates event slots.
    """

    @staticmethod
    def allocate_layout_slots(candidate_events: list, preferred_format: str = None) -> dict:
        """
        Allocates candidate events to HEADLINE, EVENT 2, and EVENT 3 slots.

        Args:
            candidate_events: List of InsightEvent objects sorted by severity score
            preferred_format: Optional forced format type

        Returns:
            Structured layout allocation dictionary.
        """
        headline_event = candidate_events[0] if len(candidate_events) > 0 else None
        event2 = candidate_events[1] if len(candidate_events) > 1 else None
        event3 = candidate_events[2] if len(candidate_events) > 2 else None

        selected_format = preferred_format if preferred_format in FORMAT_TYPES else random.choice(FORMAT_TYPES)

        return {
            'headline_event': headline_event,
            'event2': event2,
            'event3': event3,
            'content_format': selected_format,
            'headline_type': headline_event.type if headline_event else 'DEFAULT',
            'headline_description': headline_event.description if headline_event else "Turneringen rullar vidare med full kraft.",
            'event2_description': event2.description if event2 else "Flera tippare upplevde stolpe ut i omgången.",
            'event3_description': event3.description if event3 else "Många av de säkra tipsen rök på mållinjen.",
        }
