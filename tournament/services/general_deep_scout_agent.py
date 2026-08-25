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
    BackdropInfo,
)
from tournament.services.emblem_scout import EmblemScout
from tournament.services.backdrop_scout import BackdropScout
from tournament.services.wikidata_scout import WikidataScout
from tournament.services.official_site_scout import OfficialSiteScout

logger = logging.getLogger(__name__)


class GeneralDeepScoutAgent:
    """
    Agnostic Agent responsible for resolving dates, venues, hosts, high-fidelity emblems, and widescreen backdrops.
    """

    def __init__(self):
        self.emblem_scout = EmblemScout()
        self.backdrop_scout = BackdropScout()
        self.wikidata_scout = WikidataScout()

    def build_general_segment(
        self,
        tournament_name: str,
        audit_data: Optional[Dict[str, Any]] = None,
        wikipedia_title: Optional[str] = None,
        official_url: Optional[str] = None,
        existing_logo_url: Optional[str] = None,
        existing_backdrop_url: Optional[str] = None,
    ) -> GeneralSegment:
        """
        Gathers general tournament metadata across official sites, Wikidata, Wikipedia, and EmblemScout.
        """
        audit = audit_data or {}
        dates_dict = audit.get("dates") or {}

        # 1. Dates resolution
        has_audit_start = ("start_date" in audit) or ("tournament_start_date" in audit) or ("dates" in audit and "start_date" in dates_dict)
        has_audit_end = ("end_date" in audit) or ("tournament_end_date" in audit) or ("dates" in audit and "end_date" in dates_dict)
        start_date = audit.get("start_date") or audit.get("tournament_start_date") or dates_dict.get("start_date") or None
        end_date = audit.get("end_date") or audit.get("tournament_end_date") or dates_dict.get("end_date") or None

        # 2. Location resolution
        host_country = audit.get("host_country") or audit.get("country") or ""
        host_cities = audit.get("host_cities") or []
        venues = audit.get("venues") or []

        if isinstance(host_cities, str):
            host_cities = [c.strip() for c in host_cities.split(",") if c.strip()]
        if isinstance(venues, str):
            venues = [v.strip() for v in venues.split(",") if v.strip()]

        resolved_official_url = official_url or audit.get("official_source_url") or ""
        logo_url = existing_logo_url or audit.get("logo_url") or ""

        # 2.5 Gemini AI General Intelligence Enrichment
        from tournament.services.gemini_scout_service import GeminiScoutService
        if GeminiScoutService.is_available() and tournament_name:
            try:
                gemini_gen = GeminiScoutService.scout_general_details(
                    tournament_name=tournament_name,
                    sport=audit.get("sport", "Football"),
                    wikipedia_context=str(audit.get("raw_text", ""))[:4000],
                ) or {}
                if gemini_gen.get("start_date") and (start_date is None) and not has_audit_start:
                    start_date = gemini_gen.get("start_date")
                if gemini_gen.get("end_date") and (end_date is None) and not has_audit_end:
                    end_date = gemini_gen.get("end_date")
                if gemini_gen.get("host_country") and not host_country:
                    host_country = gemini_gen.get("host_country")
                if gemini_gen.get("host_cities") and not host_cities:
                    host_cities = gemini_gen.get("host_cities")
                if gemini_gen.get("host_venues") and not venues:
                    venues = gemini_gen.get("host_venues")
                if gemini_gen.get("official_website_url") and not resolved_official_url:
                    resolved_official_url = gemini_gen.get("official_website_url")
                if gemini_gen.get("organizer") and not audit.get("organizer"):
                    audit["organizer"] = gemini_gen.get("organizer")
                if gemini_gen.get("logo_url") and not logo_url:
                    logo_url = gemini_gen.get("logo_url")
            except Exception as e:
                logger.warning("GeneralDeepScoutAgent: Gemini enrichment error: %s", e)

        from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
        if start_date:
            s_parsed = LLMWikipediaScout._parse_date_string(str(start_date))
            if s_parsed:
                start_date = s_parsed
        if end_date:
            e_parsed = LLMWikipediaScout._parse_date_string(str(end_date))
            if e_parsed:
                end_date = e_parsed

        from tournament.services.scout_service import normalize_locations
        loc_info = LocationInfo(
            host_country=normalize_locations(str(host_country).strip()),
            host_cities=list(host_cities),
            venues=list(venues),
        )

        # 3. Wikidata & Official Website resolution
        wikidata_qid = audit.get("wikidata_qid")
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
        if not logo_url:
            logo_url = existing_logo_url or audit.get("logo_url") or ""
        if not logo_url:
            logo_url = EmblemScout.discover_official_emblem(
                tournament_name=tournament_name,
                official_url=resolved_official_url,
                wikidata_qid=wikidata_qid,
            ) or ""

        is_vector = bool(logo_url and (".svg" in logo_url.lower()))
        is_transparent = bool(logo_url and (".svg" in logo_url.lower() or ".png" in logo_url.lower()))

        emblem = EmblemInfo(
            logo_url=logo_url,
            is_vector=is_vector,
            is_transparent=is_transparent,
            source="EmblemScout Multi-Channel & Gemini AI",
        )

        # 4.5 Backdrop resolution (Widescreen header backdrop & key visual)
        backdrop_url = existing_backdrop_url or audit.get("backdrop_url") or ""
        if not backdrop_url:
            backdrop_url = BackdropScout.discover_backdrop(
                tournament_name=tournament_name,
                official_url=resolved_official_url,
                sport=audit.get("sport", "Football"),
            ) or ""

        backdrop = BackdropInfo(
            backdrop_url=backdrop_url,
            source="BackdropScout Multi-Source",
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
            backdrop=backdrop,
            organizer=str(organizer).strip(),
            official_website_url=resolved_official_url,
            wikipedia_url=wiki_url,
            wikidata_qid=wikidata_qid,
        )
