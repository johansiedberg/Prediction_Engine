"""
Gemini Scout Service
====================
Core AI Intelligence engine powering all scouting sub-agents.
Capitalizes on Google Gemini AI and Google Search Grounding to extract authoritative
tournament data, official regulations, draw dates, group matrices, and fixtures schedules.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class GeminiScoutService:
    """
    Central Gemini AI Client for Prediction Engine sub-agents.
    Provides structured JSON generation, Google Search Grounding, and model cascades.
    """

    SUPPORTED_MODELS = [
        "gemini-flash-lite-latest",
        "gemini-3.5-flash-lite",
    ]

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    @classmethod
    def get_api_key(cls) -> str:
        """Retrieves the active GEMINI_API_KEY from settings or environment."""
        key = getattr(settings, "GEMINI_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
        return key.strip()

    @classmethod
    def is_available(cls) -> bool:
        """Checks whether Gemini API key is configured."""
        return bool(cls.get_api_key())

    @classmethod
    def generate_json(
        cls,
        prompt: str,
        system_instruction: Optional[str] = None,
        search_grounding: bool = False,
        temperature: float = 0.1,
    ) -> Optional[Dict[str, Any]]:
        """
        Executes a Gemini generation call and parses the response as a JSON dictionary.
        Handles markdown fence stripping and fallback cascades across models.
        """
        api_key = cls.get_api_key()
        if not api_key:
            logger.warning("GeminiScoutService: GEMINI_API_KEY is not configured.")
            return None

        headers = {"Content-Type": "application/json"}

        contents = []
        if system_instruction:
            contents.append({
                "role": "user",
                "parts": [{"text": f"System Guidelines:\n{system_instruction}\n\nTask:\n{prompt}"}]
            })
        else:
            contents.append({
                "role": "user",
                "parts": [{"text": prompt}]
            })

        from tournament.services.gemini_rate_limiter import GeminiRateLimiter

        for model_name in cls.SUPPORTED_MODELS:
            url = f"{cls.BASE_URL}/{model_name}:generateContent?key={api_key}"

            # Attempt 1: with search grounding if requested
            payload: Dict[str, Any] = {
                "contents": contents,
                "generationConfig": {
                    "temperature": temperature,
                }
            }

            if search_grounding:
                payload["tools"] = [{"googleSearch": {}}]
            else:
                payload["generationConfig"]["response_mime_type"] = "application/json"

            try:
                if not GeminiRateLimiter.acquire():
                    logger.warning("GeminiScoutService: Rate limiter acquire timed out for model %s", model_name)
                    return None

                res = requests.post(url, headers=headers, json=payload, timeout=60)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            raw_text = parts[0].get("text", "").strip()
                            clean_json = cls._extract_json_block(raw_text)
                            if clean_json:
                                return json.loads(clean_json)
                elif res.status_code == 429:
                    logger.warning("GeminiScoutService: Gemini model %s returned 429 Quota Exceeded. Enforcing backoff.", model_name)
                    GeminiRateLimiter.record_429()
                    break
                else:
                    logger.debug("Gemini model %s returned status %d: %s", model_name, res.status_code, res.text[:150])
                    # If search grounding failed with schema, retry without search grounding
                    if search_grounding:
                        payload.pop("tools", None)
                        payload["generationConfig"]["response_mime_type"] = "application/json"
                        if not GeminiRateLimiter.acquire():
                            return None
                        retry_res = requests.post(url, headers=headers, json=payload, timeout=60)
                        if retry_res.status_code == 200:
                            data = retry_res.json()
                            candidates = data.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                if parts:
                                    raw_text = parts[0].get("text", "").strip()
                                    clean_json = cls._extract_json_block(raw_text)
                                    if clean_json:
                                        return json.loads(clean_json)
                        elif retry_res.status_code == 429:
                            logger.warning("GeminiScoutService: Retry for %s returned 429 Quota Exceeded.", model_name)
                            GeminiRateLimiter.record_429()
                            break

            except Exception as exc:
                logger.warning("GeminiScoutService: Error calling %s: %s", model_name, exc)

        return None

    @classmethod
    def _extract_json_block(cls, text: str) -> Optional[str]:
        """Extracts JSON string from markdown code blocks or raw text."""
        if not text:
            return None
        text = text.strip()
        # Look for ```json ... ``` or ``` ... ```
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        # Look for { ... }
        match_brace = re.search(r"(\{.*\})", text, re.DOTALL)
        if match_brace:
            return match_brace.group(1).strip()
        return text

    # =========================================================================
    # Specialized Sub-Agent AI Methods
    # =========================================================================

    @classmethod
    def scout_general_details(
        cls,
        tournament_name: str,
        sport: str = "Football",
        wikipedia_context: str = "",
    ) -> Dict[str, Any]:
        """
        AI Sub-Agent for General Information & Emblem.
        Discovers official start/end dates, host country, host cities, venues,
        organizer, official regulation website URL, and logo / vector emblem URL.
        """
        prompt = f"""
You are an expert sports intelligence agent for Prediction Engine.
Research the sports tournament "{tournament_name}" (Sport: {sport}).

Context from Wikipedia (if available):
{wikipedia_context[:4000] if wikipedia_context else "None provided."}

Return ONLY valid JSON matching this schema:
{{
  "start_date": "<ISO YYYY-MM-DD or readable start date e.g. 2026-06-11>",
  "end_date": "<ISO YYYY-MM-DD or readable end date e.g. 2026-07-19>",
  "host_country": "<Host country name(s), separated by ' / ' if multiple, e.g. USA / Canada / Mexico>",
  "host_cities": ["<Host city 1>", "<Host city 2>"],
  "host_venues": ["<Stadium/Arena 1>", "<Stadium/Arena 2>"],
  "organizer": "<Governing body e.g. FIFA, UEFA, CONCACAF, IIHF, FIBA, IOC>",
  "official_website_url": "<Official tournament or confederation website URL>",
  "logo_url": "<URL to official logo / SVG emblem / Wikimedia Commons image>",
  "tournament_summary": "<2-sentence overview of the tournament edition>"
}}
"""
        result = cls.generate_json(prompt, search_grounding=True)
        return result or {}

    @classmethod
    def scout_structure_and_rules(
        cls,
        tournament_name: str,
        sport: str = "Football",
        teams_count: Optional[int] = None,
        wikipedia_context: str = "",
    ) -> Dict[str, Any]:
        """
        AI Sub-Agent for Structure & Rules.
        Extracts official points system, tiebreakers hierarchy, group structure,
        qualifying tables (best 3rds count, ranking rules, runners-up rules, host guarantees),
        and knockout stage format.
        """
        prompt = f"""
You are an expert sports competition auditor.
Audit the official rules, regulations, and tournament structure for "{tournament_name}" (Sport: {sport}, Teams: {teams_count or 'Unknown'}).

Context:
{wikipedia_context[:5000] if wikipedia_context else "None provided."}

Extract the complete structural and regulation specifications. Return ONLY valid JSON:
{{
  "draw_date": "<ISO YYYY-MM-DD or readable date when official lottery/draw takes place e.g. 2025-12-05, or null if unknown>",
  "draw_completed": <true if the official group draw has already happened and real teams are assigned to groups, else false>,
  "seeding_elements": ["<Pot 1 info>", "<Pot 2 info>"],
  "host_guarantees": "<e.g. Co-hosts automatically assigned to Group A1, E1, I1, or null>",
  "points_system": {{
    "win": <integer e.g. 3>,
    "draw": <integer e.g. 1>,
    "loss": <integer e.g. 0>
  }},
  "tiebreakers": [
    "<1st tiebreaker e.g. Inbördes möten (Poäng) / Head-to-head points>",
    "<2nd tiebreaker e.g. Inbördes målskillnad / Head-to-head goal difference>",
    "<3rd tiebreaker e.g. Total målskillnad / Overall goal difference>",
    "<4th tiebreaker e.g. Gjorda mål totalt / Overall goals scored>",
    "<5th tiebreaker e.g. Fair Play disciplinpoäng>",
    "<6th tiebreaker e.g. Lottning>"
  ],
  "advancement_logic": {{
    "teams_per_group_advancing": <integer e.g. 2 direct advancing per group>,
    "has_best_thirds_table": <true if best 3rd-placed teams advance (e.g. 8 out of 12 third-placed teams in 48-team World Cup or 4 in 24-team Euros), else false>,
    "best_third_placed_advancing": <integer e.g. 8 or 4, or 0 if none>,
    "has_runners_up_table": <true if a secondary table of 2nd-placed teams is used across groups, else false>,
    "runners_up_advancing": <integer or 0>,
    "qualifying_table_ranking_criteria": ["Poäng", "Målskillnad", "Gjorda mål", "Disciplinpoäng"],
    "description": "<Concise Swedish/English summary e.g. De 2 bästa per grupp + de 8 bästa 3:orna avancerar till Round of 32.>"
  }},
  "knockout_rules": {{
    "starting_round": "<e.g. Round of 32, Round of 16, or Quarterfinals>",
    "total_rounds": <integer e.g. 5>,
    "regular_time_minutes": <integer e.g. 90 or 60>,
    "extra_time_minutes": <integer e.g. 30 or 10, or 0 if no extra time>,
    "has_penalties": <true if penalty shootout / straffar occurs on draw, else false>,
    "tiebreaker_description": "<e.g. Förlängning (2x15 min) följt av Straffsparksläggning vid oavgjort.>"
  }},
  "official_rules_summary": "<Comprehensive 3-5 paragraph rulebook summary including group stage format, qualifying table math, and knockout progression>"
}}
"""
        result = cls.generate_json(prompt, search_grounding=True)
        return result or {}

    @classmethod
    def scout_groups_and_teams(
        cls,
        tournament_name: str,
        sport: str = "Football",
        wikipedia_context: str = "",
    ) -> Dict[str, Any]:
        """
        AI Sub-Agent for Groups & Teams.
        Extracts group allocation matrix, real teams vs placeholders, seedings, and flag emojis.
        """
        prompt = f"""
You are an expert sports data analyst.
Extract the official groups and participating teams for "{tournament_name}" (Sport: {sport}).

Context:
{wikipedia_context[:5000] if wikipedia_context else "None provided."}

CRITICAL RULES:
1. If the official draw HAS NOT taken place yet, set "draw_completed": false, provide the "draw_date" if known, and generate standard skeleton placeholders (e.g. Group A: ["A1 (TBD)", "A2 (TBD)", "A3 (TBD)", "A4 (TBD)"]).
2. If real teams are known, extract each team with clean names (strip seeds like A1, B2 and host markers like (H)).
3. Mark "is_placeholder": true for any unconfirmed team (e.g. "Play-off Winner A", "UEFA Path A", "TBD").

Return ONLY valid JSON:
{{
  "draw_completed": <true|false>,
  "draw_date": "<ISO YYYY-MM-DD or null>",
  "has_real_teams": <true if real qualified teams are assigned to groups, else false>,
  "groups": [
    {{
      "name": "Group A",
      "teams": [
        {{"name": "Mexico", "code": "MEX", "flag_emoji": "🇲🇽", "is_placeholder": false}},
        {{"name": "South Africa", "code": "RSA", "flag_emoji": "🇿🇦", "is_placeholder": false}},
        {{"name": "A3 (TBD)", "code": "A3", "flag_emoji": "", "is_placeholder": true}},
        {{"name": "A4 (TBD)", "code": "A4", "flag_emoji": "", "is_placeholder": true}}
      ]
    }}
  ]
}}
"""
        result = cls.generate_json(prompt, search_grounding=True)
        return result or {}

    @classmethod
    def scout_matches_and_knockout(
        cls,
        tournament_name: str,
        sport: str = "Football",
        groups_data: Optional[List[Dict[str, Any]]] = None,
        wikipedia_context: str = "",
    ) -> Dict[str, Any]:
        """
        AI Sub-Agent for Matches & Knockout Bracket Tree.
        Extracts round-robin group fixtures and multi-stage knockout progression trees.
        """
        groups_summary = json.dumps(groups_data)[:2000] if groups_data else "Groups to be deduced."
        prompt = f"""
You are an expert sports competition architect.
Generate the full match timetable and knockout bracket tree for "{tournament_name}" (Sport: {sport}).

Groups Context:
{groups_summary}

Wikipedia / Web Context:
{wikipedia_context[:4000] if wikipedia_context else "None provided."}

Return ONLY valid JSON:
{{
  "fixtures_completed": <true if full match schedule with dates/times is confirmed, else false>,
  "fixtures": [
    {{
      "match_number": 1,
      "stage_or_group": "Group A",
      "home_team": "Mexico",
      "away_team": "South Africa",
      "date": "2026-06-11",
      "time": "15:00",
      "venue": "Estadio Azteca, Mexico City",
      "is_placeholder": false
    }}
  ],
  "knockout_stages": [
    {{
      "stage_name": "Round of 32",
      "round_order": 1,
      "matches": [
        {{"match_code": "R32_M73", "home_team": "1A", "away_team": "3C/E/F", "venue": "Boston"}},
        {{"match_code": "R32_M74", "home_team": "2A", "away_team": "2B", "venue": "Los Angeles"}}
      ]
    }},
    {{
      "stage_name": "Round of 16",
      "round_order": 2,
      "matches": [
        {{"match_code": "R16_M89", "home_team": "W73", "away_team": "W74"}}
      ]
    }},
    {{
      "stage_name": "Quarterfinals",
      "round_order": 3,
      "matches": []
    }},
    {{
      "stage_name": "Semifinals",
      "round_order": 4,
      "matches": []
    }},
    {{
      "stage_name": "Final",
      "round_order": 5,
      "matches": []
    }}
  ]
}}
"""
        result = cls.generate_json(prompt, search_grounding=True)
        return result or {}

    @classmethod
    def discover_upcoming_tournaments(
        cls,
        min_days_ahead: int = 30,
        count: int = 15,
        custom_query: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        AI Web Scout Engine:
        Searches the live web and Wikipedia using Google Search Grounding to discover
        major upcoming head-to-head team sports tournaments across 3 pillars:
        1. Major Continental Club Tournaments (Champions League, EuroLeague, CHL, Copa Libertadores, etc.)
        2. Continental & Global Qualifiers (Euro Qualifiers, World Cup Qualifiers, EHF Qualifiers, etc.)
        3. Major National Team Finals (World Cups, Euros, World Championships)
        """
        import datetime
        today = datetime.date.today()
        cutoff_date = today + datetime.timedelta(days=min_days_ahead)
        cutoff_str = cutoff_date.isoformat()
        current_year = today.year

        system_instruction = f"""You are an autonomous sports intelligence scout for Prediction Engine.
Your mission: Search the live web and Wikipedia to discover upcoming international and continental HEAD-TO-HEAD TEAM sports tournaments.

COVERAGE SCOPE:
1. Premier Continental Club Tournaments (e.g. UEFA Champions League, Champions Hockey League, EuroLeague Basketball, Copa Libertadores, UEFA Europa League, UEFA Conference League, EHF Champions League, IFF Champions Cup).
2. Major Continental & Global Qualifying Stages for all tournaments (e.g. UEFA Euro qualifying, AFC Asian Cup qualification, Africa Cup of Nations qualification, EHF Euro qualification, World Cup qualification).
3. Major National Team World & Continental Championships (e.g. World Floorball Championships, IIHF World Championship, FIFA Women's World Cup, UEFA Euro, FIBA Basketball World Cup, Africa Cup of Nations, CONCACAF Gold Cup).

STRICT RULES:
1. Only Head-to-Head (H2H) team sports with tournament/group/knockout format. Exclude individual sports (Tennis, Golf, Chess, etc.) and standalone domestic leagues.
2. 30-Day Runway Rule: Strictly exclude all tournaments or qualifying phases starting before {cutoff_str} (must start strictly after {cutoff_str}).
3. Dates: "start_date" and "end_date" MUST be in strict ISO format YYYY-MM-DD. If exact day is unconfirmed, normalize to the 1st of the month (YYYY-MM-01). Never output null, TBD, or empty strings.
4. Return clean, authoritative Wikipedia URLs and official tournament website URLs."""

        query_context = f" Focused on: {custom_query}" if custom_query else ""
        prompt = f"""Discover {count} upcoming major international sports tournaments, continental qualifiers, and premier club tournaments scheduled for {current_year}, {current_year + 1}, and {current_year + 2} that start strictly after {cutoff_str}.{query_context}

You MUST return a balanced tri-pillar mix containing:
1. Major Continental Club Tournaments
2. Major Qualifying Stages for international tournaments
3. Premier National Team Final Tournaments

Return ONLY valid JSON matching this schema:
{{
  "tournaments": [
    {{
      "name": "<Official tournament or qualifier name with year e.g. 2026–27 UEFA Champions League>",
      "sport": "<Sport e.g. Football, Ice Hockey, Basketball, Handball, Floorball, Volleyball>",
      "organizer": "<Governing body e.g. UEFA, FIFA, IIHF, FIBA, EHF, IFF, CONMEBOL, CAF, CONCACAF>",
      "host_country": "<Host country name(s), separated by / if multiple>",
      "start_date": "<Strict ISO YYYY-MM-DD>",
      "end_date": "<Strict ISO YYYY-MM-DD>",
      "total_teams": <Integer team count e.g. 16, 24, 32, 36, 48>,
      "official_website_url": "<Official tournament or federation website URL>",
      "wikipedia_url": "<Wikipedia article URL>"
    }}
  ]
}}"""

        res = cls.generate_json(prompt, system_instruction=system_instruction, search_grounding=True)
        if isinstance(res, dict) and isinstance(res.get("tournaments"), list):
            return res["tournaments"]
        return []

