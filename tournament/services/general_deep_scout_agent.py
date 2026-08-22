"""
Segment 2: General DeepScout Agent
==================================
Agnostic Deepscan Agent that extracts tournament general parameters:
- Confirmed start and end dates
- Location details (Host country, host cities, venues)
- Isolated, transparent emblem/logo URL via EmblemScout
- Governing organizer (FIFA, UEFA, IIHF, etc.)
- Official federation website URL & Wikipedia URL
- Wikidata QID
"""

import logging
from typing import Optional, Dict, Any, List

from tournament.schemas.tournament_prospect_schema import (
    GeneralSegment,
    LocationInfo,
    EmblemInfo,
)
from tournament.services.emblem_scout import EmblemScout
from tournament.services.wikidata_scout import WikidataScout
from tournament.services.official_site_scout import OfficialSiteScout

logger = logging.getLogger(__name__)


class GeneralDeepScoutAgent:
    """
    Agnostic Agent responsible for resolving dates, venues, hosts, and high-fidelity emblems.
    """

    def __init__(self):
        self.emblem_scout = EmblemScout()
        self.wikidata_scout = WikidataScout()

    def build_general_segment(
        self,
        tournament_name: str,
        audit_data: Optional[Dict[str, Any]] = None,
        wikipedia_title: Optional[str] = None,
        official_url: Optional[str] = None,
        existing_logo_url: Optional[str] = None,
    ) -> GeneralSegment:
        """
        Gathers general tournament metadata across official sites, Wikidata, Wikipedia, and EmblemScout.
        """
        audit = audit_data or {}
        dates_dict = audit.get("dates") or {}

        # 1. Dates resolution
        start_date = audit.get("start_date") or dates_dict.get("start_date") or None
        end_date = audit.get("end_date") or dates_dict.get("end_date") or None

        # 2. Location resolution
        host_country = audit.get("host_country") or audit.get("country") or ""
        host_cities = audit.get("host_cities") or []
        venues = audit.get("venues") or []

        if isinstance(host_cities, str):
            host_cities = [c.strip() for c in host_cities.split(",") if c.strip()]
        if isinstance(venues, str):
            venues = [v.strip() for v in venues.split(",") if v.strip()]

        loc_info = LocationInfo(
            host_country=str(host_country).strip(),
            host_cities=list(host_cities),
            venues=list(venues),
        )

        # 3. Wikidata & Official Website resolution
        wikidata_qid = audit.get("wikidata_qid")
        resolved_official_url = official_url or audit.get("official_source_url") or ""

        if wikipedia_title and (not wikidata_qid or not resolved_official_url):
            wiki_ent = self.wikidata_scout.fetch_wikidata_entity(wikipedia_title)
            if not wikidata_qid:
                wikidata_qid = wiki_ent.get("wikidata_qid")
            if not resolved_official_url:
                resolved_official_url = wiki_ent.get("official_website_url") or ""

        if not resolved_official_url:
            resolved_official_url = OfficialSiteScout.discover_official_site(
                tournament_name, wikipedia_title=wikipedia_title
            ) or ""

        # 4. Emblem resolution
        logo_url = existing_logo_url or audit.get("logo_url") or ""
        if not logo_url:
            logo_url = self.emblem_scout.fetch_tournament_logo(
                tournament_name=tournament_name,
                wikipedia_title=wikipedia_title,
                official_url=resolved_official_url,
                wikidata_qid=wikidata_qid,
            ) or ""

        is_vector = bool(logo_url and (".svg" in logo_url.lower()))
        is_transparent = bool(logo_url and (".svg" in logo_url.lower() or ".png" in logo_url.lower()))

        emblem = EmblemInfo(
            logo_url=logo_url,
            is_vector=is_vector,
            is_transparent=is_transparent,
            source="EmblemScout Multi-Channel",
        )

        # 5. Organizer & Wiki URL
        organizer = audit.get("organizer") or audit.get("governing_body") or ""
        wiki_url = audit.get("wikipedia_url") or (
            f"https://en.wikipedia.org/wiki/{wikipedia_title.replace(' ', '_')}" if wikipedia_title else ""
        )

        return GeneralSegment(
            start_date=start_date,
            end_date=end_date,
            location=loc_info,
            emblem=emblem,
            organizer=str(organizer).strip(),
            official_website_url=resolved_official_url,
            wikipedia_url=wiki_url,
            wikidata_qid=wikidata_qid,
        )
