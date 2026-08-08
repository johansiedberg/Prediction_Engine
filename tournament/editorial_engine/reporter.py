"""
reporter.py
-----------
Role 1: Reporter for Daily Gazette Editorial Engine.

Responsible for:
1. Scanning database for matchday occurrences (matches, predictions, standings).
2. Detecting candidate InsightEvent records with severity/importance scores.
3. Gathering player personas associated with detected events.
"""

from tournament.models import Tournament, Match, MatchPrediction, InsightEvent
from tournament.editorial_engine.compiler import load_player_personas, find_persona_for_player


class Reporter:
    """
    Reporter component that scans the database and discovers daily events.
    """

    @staticmethod
    def gather_daily_events(tournament: Tournament, matchday_number: int = None) -> dict:
        """
        Scans completed matches and predictions to detect candidate events.

        Returns:
            {
                'events': list of InsightEvent objects sorted by severity score,
                'featured_personas': list of matched player persona dicts,
            }
        """
        personas_list = load_player_personas()

        # Fetch unused events from DB or run detection if needed
        unused_events = list(
            InsightEvent.objects.filter(tournament=tournament, is_used=False).order_by('-importance_score')[:5]
        )

        if not unused_events:
            unused_events = list(
                InsightEvent.objects.filter(tournament=tournament).order_by('-importance_score')[:5]
            )

        featured_personas = []
        for event in unused_events:
            if event.player_name:
                p_match = find_persona_for_player(event.player_name, personas_list)
                if p_match and p_match not in featured_personas:
                    featured_personas.append(p_match)

        return {
            'events': unused_events,
            'featured_personas': featured_personas,
        }
