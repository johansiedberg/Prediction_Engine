"""
Segment 1: Head Discovery Agent
===============================
Agnostic Discovery Agent that identifies and validates prospective tournament candidates,
extracting the core HeadSegment:
- Tournament Name
- Master Event Code (Slug)
- Sport discipline
- H2H Team Sport eligibility check
- Start Date
- Discovery Source
"""

import re
import logging
from typing import Optional, Dict, Any

from tournament.schemas.tournament_prospect_schema import HeadSegment
from tournament.services.tournament_filter import is_h2h_team_sport, detect_sport_from_title

logger = logging.getLogger(__name__)


class HeadDiscoveryAgent:
    """
    Agnostic Agent responsible for identifying prospective tournaments and populating the HeadSegment.
    """

    @classmethod
    def generate_slug(cls, name: str) -> str:
        """Generates a clean URL/Code slug from a tournament name."""
        s = name.lower().strip()
        s = re.sub(r"[^\w\s-]", "", s)
        s = re.sub(r"[\s_-]+", "-", s)
        return s.strip("-")[:100]

    @classmethod
    def build_head_segment(
        cls,
        name: str,
        sport: str = "Football",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        discovery_source: str = "AllSportDB",
        master_event_code: Optional[str] = None,
    ) -> HeadSegment:
        """
        Validates sport suitability and constructs a validated HeadSegment.
        """
        clean_name = (name or "").strip()
        raw_sport = (sport or "").strip()
        if not raw_sport or raw_sport.lower() in ["sports", "general", "other", ""]:
            clean_sport = detect_sport_from_title(clean_name, default_sport="Football")
        else:
            clean_sport = detect_sport_from_title(clean_name, default_sport=raw_sport)
        clean_slug = master_event_code or cls.generate_slug(clean_name)
        h2h_eligible = is_h2h_team_sport(clean_sport)

        from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
        s_date_iso = LLMWikipediaScout._parse_date_string(str(start_date)) if start_date else None
        e_date_iso = LLMWikipediaScout._parse_date_string(str(end_date)) if end_date else None

        return HeadSegment(
            name=clean_name,
            master_event_code=clean_slug,
            sport=clean_sport,
            is_h2h_team_sport=h2h_eligible,
            start_date=s_date_iso if s_date_iso else (start_date if start_date else None),
            end_date=e_date_iso if e_date_iso else (end_date if end_date else None),
            discovery_source=discovery_source,
        )
