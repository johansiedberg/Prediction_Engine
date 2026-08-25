"""
Dynamic Team Badge & Flag Resolution Service (TeamBadgeService)
==============================================================
Provides a 4-tier hybrid resolution architecture:
1. Tier 1: Exhaustive Global Multi-Lingual Country & Territory Registry (250+ Nations, FIFA/IOC, Subdivisions).
2. Tier 2: Persistent Database Cache (TeamBadgeCache) for 0ms subsequent lookups.
3. Tier 3: Wikidata & Wikimedia Commons Direct Logo Engine for Club teams and Federations.
4. Tier 4: Gemini AI Team & Club Disambiguation Engine using the active GEMINI_API_KEY.
"""

import logging
import re
import urllib.parse
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import requests

logger = logging.getLogger(__name__)

from tournament.country_registry import GLOBAL_COUNTRY_FLAG_MAP


@dataclass
class TeamBadgeResult:
    team_name: str
    team_type: str            # 'NATIONAL', 'CLUB', 'PLACEHOLDER'
    code: str = ""            # 2-letter FlagCDN code (e.g. 'ht', 'cw', 'se', 'gb-eng')
    flag_url: str = ""        # https://flagcdn.com/w40/{code}.png
    emblem_url: str = ""      # Direct SVG/PNG club badge URL
    canonical_name: str = ""
    is_placeholder: bool = False

    @property
    def badge_url(self) -> str:
        """Returns emblem_url for club teams, or flag_url for national teams."""
        if self.emblem_url:
            return self.emblem_url
        if self.flag_url:
            return self.flag_url
        return ""


class TeamBadgeService:
    """
    Unified Service for resolving team flags and club emblems.
    """

    @classmethod
    def is_placeholder(cls, name_str: str) -> bool:
        """Checks if the team name is a placeholder (e.g. A1, 1A, Pot 1, Playoff Winner, TBD, W73, 3C/E/F)."""
        if not name_str or not isinstance(name_str, str):
            return True
        s = name_str.strip().lower()
        if not s or len(s) < 2 or s in {'tbd', 'total', 'seed', 'team', 'match', 'placeholder', 'null', 'none', '-'}:
            return True
        # Bracket / Slot notation: A1, 1A, B2, 2B, 3C/E/F, 1st, 2nd, 3rd, etc.
        if re.match(r'^(?:[a-z]\d+|\d+[a-z](?:/[a-z]+)*|\d+(?:st|nd|rd|th))\b', s):
            return True
        # Match winners / losers / tokens: W73, L74, M1, QF_1, SF_2, R16_3, etc.
        if re.match(r'^(?:[wml]\d+|qf_\d+|sf_\d+|r16_\d+|r32_\d+|m_\d+)\b', s):
            return True
        # Common text placeholders
        if re.match(r'^(?:group|grupp|lag|team|seed|pot|winner|runner-up|vinnare|förlorare|loser|qf|sf|r16|r32|play-?off|path)\s*[\w\d_#\s\-/]*$', s):
            return True
        if re.search(r'\(\d+:?[ae]?\s+(?:grupp|group)\s+[a-z]\)', s):
            return True
        if any(tok in s for tok in ['vinnare', 'winner', 'mästare', 'guld', 'finalist', 'play-off', 'playoff', 'tbd', 'to be determined']):
            return True
        return False

    @classmethod
    def resolve_national_country_code(cls, name_str: str) -> Optional[str]:
        """
        Tier 1: High-speed resolution of country/territory name or code to FlagCDN ISO code.
        """
        if not name_str or cls.is_placeholder(name_str):
            return None
        
        raw = name_str.strip().lower()
        
        # Direct lookup
        if raw in GLOBAL_COUNTRY_FLAG_MAP:
            return GLOBAL_COUNTRY_FLAG_MAP[raw]
        
        # Clean common national team prefixes / suffixes (e.g. "Sweden Men", "France U21", "National Team Spain")
        cleaned = re.sub(r'\b(?:men|women|u\d+|u-\d+|herrar|damer|national team|landslag|team)\b', '', raw, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r'[\(\)\[\]]', '', cleaned).strip()
        
        if cleaned in GLOBAL_COUNTRY_FLAG_MAP:
            return GLOBAL_COUNTRY_FLAG_MAP[cleaned]
        
        return None

    @classmethod
    def query_wikidata_club_logo(cls, club_name: str, sport: str = "") -> Optional[str]:
        """
        Tier 3: Queries Wikidata REST API for club entity and returns its official logo image URL.
        """
        if not club_name or cls.is_placeholder(club_name):
            return None
            
        try:
            search_url = "https://www.wikidata.org/w/api.php"
            params = {
                "action": "wbsearchentities",
                "search": f"{club_name} {sport}".strip(),
                "language": "en",
                "format": "json",
                "limit": 3
            }
            headers = {"User-Agent": "PredictionEngine/1.0 (info@predictionengine.app)"}
            res = requests.get(search_url, params=params, headers=headers, timeout=4)
            if res.status_code != 200:
                return None
            data = res.json()
            results = data.get("search", [])
            if not results:
                return None

            entity_id = results[0].get("id")
            if not entity_id:
                return None

            # Get entity claims
            entity_url = f"https://www.wikidata.org/wiki/Special:EntityData/{entity_id}.json"
            ent_res = requests.get(entity_url, headers=headers, timeout=4)
            if ent_res.status_code != 200:
                return None
            ent_data = ent_res.json()
            claims = ent_data.get("entities", {}).get(entity_id, {}).get("claims", {})
            
            # P154 is logo image, P41 is flag image, P18 is image
            image_claims = claims.get("P154") or claims.get("P41") or claims.get("P18")
            if image_claims:
                file_name = image_claims[0].get("mainsnak", {}).get("datavalue", {}).get("value")
                if file_name and not any(bad in file_name.lower() for bad in ['.gif', 'animated', 'animation', '.apng']):
                    safe_file = urllib.parse.quote(file_name.replace(' ', '_'))
                    # Wikimedia special filepath direct thumbnail
                    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{safe_file}"
        except Exception as e:
            logger.debug(f"Wikidata club logo query error for '{club_name}': {e}")
            
        return None

    @classmethod
    def query_gemini_team_disambiguation(
        cls, team_name: str, sport: str = "", tournament_name: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        Tier 4: Calls Gemini AI to disambiguate team type and discover official vector logo / country code.
        """
        from tournament.services.gemini_scout_service import GeminiScoutService
        if not GeminiScoutService.is_available():
            return None

        prompt = f"""Identify the sporting entity and return its official flag code or Wikimedia Commons logo URL:
Team Name: {team_name}
Sport: {sport or 'Sports'}
Tournament Context: {tournament_name or 'Championship'}

Return ONLY valid JSON matching this schema:
{{
  "team_type": "NATIONAL" or "CLUB" or "PLACEHOLDER",
  "country_code": "<2-letter ISO or FlagCDN code like 'se', 'gb-eng', 'es', or ''>",
  "canonical_name": "<Official Name of the team/club>",
  "emblem_url": "<Direct Wikimedia Commons SVG or PNG logo URL if club, or ''>",
  "is_placeholder": false
}}"""
        try:
            res = GeminiScoutService.generate_json(prompt)
            if isinstance(res, dict) and res.get("canonical_name"):
                return res
        except Exception as e:
            logger.warning(f"Gemini team disambiguation error for '{team_name}': {e}")

        return None

    @classmethod
    def resolve_team_badge(
        cls,
        team_name: str,
        sport: str = "",
        tournament_name: str = "",
        use_gemini_fallback: bool = True
    ) -> TeamBadgeResult:
        """
        Resolves team flag or club badge across all 4 tiers.
        """
        if not team_name or cls.is_placeholder(team_name):
            return TeamBadgeResult(
                team_name=team_name or "TBD",
                team_type="PLACEHOLDER",
                is_placeholder=True
            )

        name_clean = team_name.strip()

        # ----------------------------------------------------
        # TIER 1: In-Memory Multi-Lingual Country / Territory Map (0ms)
        # ----------------------------------------------------
        country_code = cls.resolve_national_country_code(name_clean)
        if country_code:
            return TeamBadgeResult(
                team_name=name_clean,
                team_type="NATIONAL",
                code=country_code.lower(),
                flag_url=f"https://flagcdn.com/w40/{country_code.lower()}.png",
                canonical_name=name_clean,
                is_placeholder=False
            )

        # ----------------------------------------------------
        # TIER 2: Check Persistent Database Cache
        # ----------------------------------------------------
        try:
            from tournament.models import TeamBadgeCache
            cache_obj = TeamBadgeCache.objects.filter(team_name__iexact=name_clean).first()
            if cache_obj:
                return TeamBadgeResult(
                    team_name=name_clean,
                    team_type=cache_obj.team_type,
                    code=cache_obj.country_code or "",
                    flag_url=f"https://flagcdn.com/w40/{cache_obj.country_code.lower()}.png" if cache_obj.country_code else "",
                    emblem_url=cache_obj.emblem_url or "",
                    canonical_name=cache_obj.canonical_name or name_clean,
                    is_placeholder=cache_obj.team_type == "PLACEHOLDER"
                )
        except Exception:
            pass

        # ----------------------------------------------------
        # TIER 3: Wikidata / Wikimedia Commons Direct Logo Ingestion
        # ----------------------------------------------------
        wiki_logo = cls.query_wikidata_club_logo(name_clean, sport=sport)
        if wiki_logo:
            res_item = TeamBadgeResult(
                team_name=name_clean,
                team_type="CLUB",
                emblem_url=wiki_logo,
                canonical_name=name_clean,
                is_placeholder=False
            )
            cls._save_to_cache(res_item, sport=sport)
            return res_item

        # ----------------------------------------------------
        # TIER 4: Gemini AI Disambiguation Engine
        # ----------------------------------------------------
        if use_gemini_fallback:
            ai_data = cls.query_gemini_team_disambiguation(name_clean, sport=sport, tournament_name=tournament_name)
            if ai_data:
                t_type = ai_data.get("team_type", "CLUB")
                c_code = (ai_data.get("country_code") or "").lower()
                e_url = ai_data.get("emblem_url") or ""
                if e_url and any(bad in e_url.lower() for bad in ['.gif', 'animated', 'animation', '.apng']):
                    e_url = ""
                can_name = ai_data.get("canonical_name") or name_clean
                
                res_item = TeamBadgeResult(
                    team_name=name_clean,
                    team_type=t_type,
                    code=c_code,
                    flag_url=f"https://flagcdn.com/w40/{c_code}.png" if c_code else "",
                    emblem_url=e_url,
                    canonical_name=can_name,
                    is_placeholder=bool(ai_data.get("is_placeholder", False))
                )
                cls._save_to_cache(res_item, sport=sport)
                return res_item

        # Fallback Result
        fallback_item = TeamBadgeResult(
            team_name=name_clean,
            team_type="CLUB",
            canonical_name=name_clean,
            is_placeholder=False
        )
        cls._save_to_cache(fallback_item, sport=sport)
        return fallback_item

    @classmethod
    def _save_to_cache(cls, result: TeamBadgeResult, sport: str = ""):
        """Persists resolved team badge to database cache for instant future retrieval."""
        try:
            from tournament.models import TeamBadgeCache
            TeamBadgeCache.objects.update_or_create(
                team_name=result.team_name,
                defaults={
                    "sport": sport,
                    "team_type": result.team_type,
                    "country_code": result.code,
                    "emblem_url": result.emblem_url,
                    "canonical_name": result.canonical_name or result.team_name,
                }
            )
        except Exception as e:
            logger.debug(f"Failed to cache team badge for '{result.team_name}': {e}")
