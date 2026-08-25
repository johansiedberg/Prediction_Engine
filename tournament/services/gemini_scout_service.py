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
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-flash-lite-latest",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash",
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
        timeout: float = 10.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Executes a Gemini generation call and parses the response as a JSON dictionary.
        Includes a strict timeout circuit breaker (default: 10.0s) to guarantee the
        scouting pipeline never hangs or gets stuck in a loop.
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
                if not GeminiRateLimiter.acquire(timeout=6.0):
                    logger.warning("GeminiScoutService: Rate limiter acquire timed out for model %s. Aborting search.", model_name)
                    return None

                res = requests.post(url, headers=headers, json=payload, timeout=timeout)
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

            except requests.Timeout:
                logger.warning("GeminiScoutService: Query to %s timed out after %.1fs. Abandoning search to keep pipeline moving.", model_name, timeout)
                return None
            except Exception as exc:
                logger.warning("GeminiScoutService: Error calling %s: %s", model_name, exc)
                return None

        return None

    @classmethod
    def generate_json_with_metadata(
        cls,
        prompt: str,
        system_instruction: Optional[str] = None,
        search_grounding: bool = True,
        temperature: float = 0.1,
        timeout: float = 10.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Executes a Gemini generation call with Google Search Grounding, parses the JSON response,
        and extracts all grounded web source URLs and executed search queries.
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
                if not GeminiRateLimiter.acquire(timeout=6.0):
                    logger.warning("GeminiScoutService: Rate limiter acquire timed out for model %s.", model_name)
                    return None

                res = requests.post(url, headers=headers, json=payload, timeout=timeout)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        cand = candidates[0]
                        parts = cand.get("content", {}).get("parts", [])
                        raw_text = parts[0].get("text", "").strip() if parts else ""
                        clean_json = cls._extract_json_block(raw_text)
                        parsed_dict = json.loads(clean_json) if clean_json else {}

                        # Extract grounding chunks / sources
                        grounding_meta = cand.get("groundingMetadata", {})
                        grounding_chunks = grounding_meta.get("groundingChunks", [])
                        queries = grounding_meta.get("webSearchQueries", [])
                        sources = []
                        for chunk in grounding_chunks:
                            web = chunk.get("web", {})
                            if web and web.get("uri"):
                                sources.append({
                                    "url": web.get("uri"),
                                    "title": web.get("title", ""),
                                })

                        return {
                            "data": parsed_dict,
                            "sources": sources,
                            "search_queries": queries,
                        }
                elif res.status_code == 429:
                    logger.warning("GeminiScoutService: Gemini model %s returned 429 Quota Exceeded. Enforcing backoff.", model_name)
                    GeminiRateLimiter.record_429()
                    break

            except requests.Timeout:
                logger.warning("GeminiScoutService: Query to %s timed out after %.1fs.", model_name, timeout)
                return None
            except Exception as exc:
                logger.warning("GeminiScoutService: Error calling %s: %s", model_name, exc)
                return None

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
        tournament_meta: Optional[Dict[str, Any]] = None,
        organizer: str = "",
        host_country: str = "",
        start_date: str = "",
        end_date: str = "",
        total_teams: int = 0,
        official_website_url: str = "",
        wikipedia_url: str = "",
    ) -> Dict[str, Any]:
        """
        AI Sub-Agent for Matches & Knockout Bracket Tree (Google AI Studio Enhanced).
        Extracts round-robin group fixtures and multi-stage knockout progression trees
        from structured tournament metadata and search grounded context.
        """
        meta = dict(tournament_meta or {})
        t_name = meta.get("name") or tournament_name
        t_sport = meta.get("sport") or sport or "Sports"
        t_organizer = meta.get("organizer") or organizer or "Official Organizer"
        t_host = meta.get("host_country") or host_country or "Worldwide"
        t_start = meta.get("start_date") or start_date or ""
        t_end = meta.get("end_date") or end_date or ""
        t_teams = meta.get("total_teams") or total_teams or 16
        t_official = meta.get("official_website_url") or official_website_url or ""
        t_wiki = meta.get("wikipedia_url") or wikipedia_url or ""

        groups_summary = json.dumps(groups_data, ensure_ascii=False)[:3000] if groups_data else "Groups to be deduced from tournament format."

        meta_input = {
            "name": t_name,
            "sport": t_sport,
            "organizer": t_organizer,
            "host_country": t_host,
            "start_date": t_start,
            "end_date": t_end,
            "total_teams": t_teams,
            "official_website_url": t_official,
            "wikipedia_url": t_wiki,
        }

        prompt = f"""You are an expert Sports Tournament Scheduling & Knockout Bracket Intelligence Agent.
The user has provided the following tournament metadata as starting point:

```json
{json.dumps(meta_input, indent=2, ensure_ascii=False)}
```

Groups Context:
{groups_summary}

Wikipedia / Web Context:
{wikipedia_context[:4000] if wikipedia_context else "None provided."}

YOUR TASK:
Find and generate the complete, realistic tournament fixtures and knockout bracket phases for "{t_name}" ({t_sport}, organized by {t_organizer}, host: {t_host}, {t_teams} teams).
Search the web / official references / Wikipedia ({t_wiki or t_official}) to find:
1. Tournament structure (League phase / Round-Robin / Group stages like Groups A, B, C... or Regular Season Rounds, plus Play-in / advancement if applicable).
2. For Club tournaments (e.g. EuroLeague basketball, UEFA Champions League), list the participating clubs, their authentic stadiums/arenas (venues) across Europe/host regions, accurate calendar dates matching start_date "{t_start}" to end_date "{t_end}".
3. For National team tournaments (e.g. AFC Asian Cup, FIFA World Cup, EuroBasket), find official groups (e.g. Groups A through F), 2-letter ISO country codes in lowercase (e.g. "sa", "es", "gr", "fr", "de", "us", "jp", "kr") for flagcdn URLs `https://flagcdn.com/w40/{{code}}.png`, real venues and cities, and correct dates.
4. Knockout Phases: Round of 16 / Play-in / Quarter-finals / Semi-finals / 3rd Place / Final with:
   - `match_code`: e.g. "R16_1", "R16_2", "QF_1", "QF_2", "SF_1", "SF_2", "FINAL"
   - `stage_name`: e.g. "Play-in", "Round of 16", "Quarterfinals" (or "Quarter-finals"), "Semifinals" (or "Semi-finals"), "Final"
   - `round_order`: 1, 2, 3, 4 ...
   - `home_team` and `away_team`: placeholder rules (e.g., "1A", "2B", "Winner Match 37", "Winner QF_1", "Seed 1", "Seed 8") or confirmed teams if known.
   - `winner_to`: e.g. "QF_1", "SF_1", "FINAL", "Champion / Winner"
   - `date_time` and `venue`
5. In `group_matches`, list the individual matches with sequential `match_number` (1, 2, 3, ...), `stage_or_group` (e.g. "Group A", "Round 1", etc.), `home_team`, `away_team`, `home_team_code`, `home_team_flag_url`, `home_team_emblem_url`, `away_team_code`, `away_team_flag_url`, `away_team_emblem_url`, `date_time`, `venue`, and `is_placeholder` (true/false).
6. In `advancement_fixtures`, list advancement rules (e.g. match_code: "R16_1", stage_name: "Round of 16", source_home: "Winner Group A", source_away: "Runner-up Group B").
7. Calculate `total_matches` accurately.

YOU MUST STRICTLY RETURN A SINGLE VALID JSON OBJECT matching this exact schema:

{{
  "matches_and_knockout_segment": {{
    "total_matches": 66,
    "fixtures_completed": false,
    "group_matches": [
      {{
        "match_number": 1,
        "stage_or_group": "Group A",
        "home_team": "Team A",
        "away_team": "Team B",
        "home_team_code": "code",
        "home_team_flag_url": "https://flagcdn.com/w40/code.png",
        "home_team_emblem_url": "",
        "away_team_code": "code2",
        "away_team_flag_url": "https://flagcdn.com/w40/code2.png",
        "away_team_emblem_url": "",
        "date_time": "YYYY-MM-DD",
        "venue": "Stadium/Arena Name, City",
        "is_placeholder": false
      }}
    ],
    "advancement_fixtures": [
      {{
        "match_code": "R16_1",
        "stage_name": "Round of 16",
        "source_home": "Winner Group A",
        "source_away": "Runner-up Group B"
      }}
    ],
    "knockout_bracket": [
      {{
        "stage_name": "Round of 16",
        "round_order": 1,
        "matches": [
          {{
            "match_code": "R16_1",
            "stage_name": "Round of 16",
            "home_team": "1A",
            "away_team": "2B",
            "home_team_code": "",
            "home_team_flag_url": "",
            "home_team_emblem_url": "",
            "away_team_code": "",
            "away_team_flag_url": "",
            "away_team_emblem_url": "",
            "winner_to": "QF_1",
            "date_time": "YYYY-MM-DD",
            "venue": "Stadium/Arena, City"
          }}
        ]
      }},
      {{
        "stage_name": "Quarterfinals",
        "round_order": 2,
        "matches": [
          {{
            "match_code": "QF_1",
            "stage_name": "Quarterfinals",
            "home_team": "Winner R16_1",
            "away_team": "Winner R16_2",
            "home_team_code": "",
            "home_team_flag_url": "",
            "home_team_emblem_url": "",
            "away_team_code": "",
            "away_team_flag_url": "",
            "away_team_emblem_url": "",
            "winner_to": "SF_1",
            "date_time": null,
            "venue": ""
          }}
        ]
      }},
      {{
        "stage_name": "Semifinals",
        "round_order": 3,
        "matches": [
          {{
            "match_code": "SF_1",
            "stage_name": "Semifinals",
            "home_team": "Winner QF_1",
            "away_team": "Winner QF_2",
            "home_team_code": "",
            "home_team_flag_url": "",
            "home_team_emblem_url": "",
            "away_team_code": "",
            "away_team_flag_url": "",
            "away_team_emblem_url": "",
            "winner_to": "FINAL",
            "date_time": null,
            "venue": ""
          }}
        ]
      }},
      {{
        "stage_name": "Final",
        "round_order": 4,
        "matches": [
          {{
            "match_code": "FINAL",
            "stage_name": "Final",
            "home_team": "Winner SF_1",
            "away_team": "Winner SF_2",
            "home_team_code": "",
            "home_team_flag_url": "",
            "home_team_emblem_url": "",
            "away_team_code": "",
            "away_team_flag_url": "",
            "away_team_emblem_url": "",
            "winner_to": "Champion",
            "date_time": null,
            "venue": ""
          }}
        ]
      }}
    ]
  }}
}}

Do not include any conversational preamble. Output ONLY valid JSON.
"""
        result = cls.generate_json(prompt, search_grounding=True)
        if not result or not isinstance(result, dict):
            return {}

        # Normalize root structure if wrapped under matches_and_knockout_segment
        if "matches_and_knockout_segment" in result and isinstance(result["matches_and_knockout_segment"], dict):
            return result["matches_and_knockout_segment"]
        return result

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

