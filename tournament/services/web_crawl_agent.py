"""
Phase 1: WebCrawl / Ingestion Agent
===================================
Automated discovery agent that scans external sources (AllSportDB API, Web search, custom feeds)
to discover upcoming sports tournaments.

Identifies core metadata:
- Tournament name
- Start & End dates (used to filter & sort COMING TOURNAMENTS)
- General Sport discipline (strictly H2H team sports)
- Organizer & Host Country
- Official source URL

Initializes prospects with:
- Initial status: NEW
- Completeness grade: GRADE_C (Shallow)
- Stage: SHALLOW

Rejects / Discards:
- Non-H2H individual sports (Chess, Tennis, Archery, Sailing, etc.)
- Past or ongoing events (start_date < today + 30 days or end_date < today)
"""

import datetime
import logging
from typing import Tuple, List, Dict, Any, Optional

from django.utils import timezone
from tournament.schemas.tournament_prospect_schema import (
    TournamentProspectBlueprint,
    ProspectMetadata,
    ScoutingAudit,
    ScoutingStage,
    CompletenessGrade,
    ProspectStatus,
)
from tournament.services.allsportdb_client import AllSportDBClient
from tournament.services.tournament_filter import (
    is_h2h_team_sport,
    is_championship_or_cup_format,
)
from tournament.models import ScannedTournament, Sport

logger = logging.getLogger(__name__)


class WebCrawlAgent:
    """
    Ingestion Agent for Phase 1 Tournament Discovery.
    """

    def __init__(self, min_days_ahead: int = 0):
        self.min_days_ahead = min_days_ahead

    def discover_and_ingest(self, custom_query: Optional[str] = None) -> Tuple[int, int, List[ScannedTournament]]:
        """
        Runs discovery scan across AllSportDB API, Wikipedia Annual Sports Events (2026 & 2027),
        and Major Continental Competitions. Filters for H2H sports and start_dates in range.
        Returns (created_count, updated_count, list_of_prospects).
        """
        from tournament.services.scout_service import sync_all_scout_prospects
        created_count, updated_count, prospects = sync_all_scout_prospects(custom_query=custom_query)
        return created_count, updated_count, prospects

