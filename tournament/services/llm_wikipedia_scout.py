"""
LLM-Powered Wikipedia Deep Scout
=================================
Uses the Wikipedia REST API to fetch a tournament article as clean plaintext,
then passes the full text to Google Gemini Flash which returns a structured
JSON audit dict.  No HTML parsing, no CSS class assumptions, no regex
patterns for specific sport markup — the LLM reads the page like a human
and extracts whatever it finds.

Fallback strategy
-----------------
If GEMINI_API_KEY is not set, or the API call fails for any reason,
audit_with_llm() transparently falls back to the existing HTML heuristic
WikipediaScout.audit_tournament_page() so there is zero regression.
"""

import json
import logging
import re
import urllib.parse

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# ── Prompt sent to Gemini ──────────────────────────────────────────────────────
_RESPONSE_SCHEMA_DESC = """
Return ONLY valid JSON matching this exact schema (no markdown fences, no prose):
{
  "is_disambiguation": <true if this Wikipedia article is a split portal/disambiguation page pointing to separate tournaments (e.g. Men's and Women's tournaments), else false>,
  "is_ongoing_or_finished": <true if the Wikipedia article contains played match scores e.g. "21 – 20", "13 – 47", standings/results, or if main tournament is currently underway or finished, else false>,
  "sub_tournaments": [
    {
      "name": "<e.g. 2026 FIBA 3x3 U23 World Cup – Men's tournament>",
      "wiki_title": "<article title>",
      "wiki_url": "<full Wikipedia URL if stated>"
    }
  ],
  "tournament_start_date": "<ISO date YYYY-MM-DD or readable start date of main tournament e.g. 11 June 2026, 15 May 2026, 19 August 2026, 3 December 2026, or empty string>",
  "tournament_end_date": "<ISO date YYYY-MM-DD or readable end date of main tournament e.g. 19 July 2026, 29 August 2026, 20 December 2026, or empty string>",
  "date_reasoning": "<brief explanation of why these start/end dates were identified as the main final tournament dates vs qualification or draw dates>",
  "teams_count": <integer>,
  "host_country": "<string>",
  "groups": [
    {
      "name": "<e.g. Group A>",
      "teams": [{"name": "<team name without seed codes e.g. Hungary, Romania, Sweden>"}, ...]
    }
  ],
  "fixtures": [
    {
      "home_team": "<team name or placeholder e.g. TBD/W37/1A>",
      "away_team": "<team name or placeholder>",
      "date": "<e.g. 12 June 2026 or empty string>",
      "time": "<e.g. 18:00 or empty string>",
      "venue": "<city or stadium or empty string>",
      "stage_or_group": "<e.g. Group A / Round of 16 / Final>",
      "is_placeholder": <true if either team is TBD or a seeding code, else false>
    }
  ],
  "scheduled_matchdays": <integer 0 if not applicable>,
  "draw_completed": <true|false>,
  "draw_date": "<e.g. 6 December 2026 or empty string>",
  "advancement_rules": "<plain text or empty string>",
  "official_rules": "<detailed official regulations text summary including format, tiebreakers, extra-time rules, or qualification criteria>",
  "official_regulations_url": "<direct URL to official regulation document or website if mentioned>",
  "knockout_stages": ["Round of 16", "Quarterfinals", "Semifinals", "Final"],
  "fixtures_count": <integer>,
  "groups_count": <integer>,
  "fixtures_completed": <true|false>
}
"""

_SYSTEM_PROMPT = (
    "You are an expert sports tournament auditor. You will be given the plaintext and infobox wikitext of a "
    "Wikipedia article about a sports tournament. Extract structured tournament information.\n"
    "CRITICAL REQUIREMENT FOR DISAMBIGUATION / SPLIT PAGES:\n"
    "If the article is a portal/disambiguation page listing separate Men's and Women's tournaments (e.g. 'consists of two sections: Men's tournament and Women's tournament'), set 'is_disambiguation': true and list the sub_tournaments.\n"
    "CRITICAL REQUIREMENT FOR PLAYED MATCH SCORES / ONGOING TOURNAMENTS:\n"
    "Inspect the match schedule tables. If match scores or results are listed (e.g. '21 – 20', '13 – 47', 'Paris Musketeers 21 – 20 Frankfurt Galaxy'), set 'is_ongoing_or_finished': true.\n"
    "CRITICAL REQUIREMENT FOR TOURNAMENT DATES:\n"
    "You MUST distinguish the MAIN TOURNAMENT / FINAL TOURNAMENT start and end dates from qualification dates, draw dates, bidding dates, or past/future edition dates.\n"
    "Look specifically at the WIKIPEDIA INFOBOX TEMPLATE header and Infobox fields (e.g. '| dates = {{start and end dates|2027|08|25|2027|09|05}}' or 'Dates: 25 August – 5 September 2027').\n"
    "Record official tournament start and end dates accurately, handling range formats such as '2027-08-25 – 2027-09-05', '25 August – 5 September 2027', '15 May – 29 August 2026', '19–29 August 2026', '3–20 December'.\n"
    "If the article does not mention the actual main tournament start date, return empty strings for these fields.\n"
    "CRITICAL REQUIREMENT FOR TEAM NAMES:\n"
    "Clean team names by stripping seed codes (A1, B2, D3) and host indicators like (H) or (C) so only clean country/team names remain (e.g. 'Romania' instead of 'B2 Romania (H)').\n"
    "CRITICAL REQUIREMENT FOR 'official_rules': Strive to extract a complete, comprehensive tournament rulebook summary "
    "covering:\n"
    "  1. Tournament format & competition structure (e.g. number of teams, groups, match format, 48 teams in 12 groups of 4).\n"
    "  2. Group stage standings & tiebreaker rules (points for win/draw, head-to-head, goal difference, goals scored, fair play points).\n"
    "  3. Advancement & qualification criteria (e.g. top 2 per group + 8 best 3rd-placed teams advance to Round of 32).\n"
    "  4. Knockout stage rules (extra time format, 30 mins ET, penalty shootout, substitution rules).\n"
    "  5. Official regulation links or source references if mentioned.\n"
    "Structure 'official_rules' into clean, well-formatted bullet points or numbered sections for maximum legibility.\n"
    "Use placeholder codes exactly as written (TBD, W37, 1A, etc).\n"
    "For qualifying or league-format tournaments with matchday schedules but no individual "
    "fixtures yet, set scheduled_matchdays to the number of matchday rounds and leave "
    "fixtures as an empty list.\n"
    "If a draw has been announced for a future date but not yet held, set draw_completed=false "
    "and record the draw_date.\n"
    + _RESPONSE_SCHEMA_DESC
)


class LLMWikipediaScout:
    """
    LLM-powered replacement for WikipediaScout.audit_tournament_page().

    Usage:
        scout = LLMWikipediaScout()
        result = scout.audit_with_llm("2026 FIFA World Cup")
        # result has same schema as WikipediaScout.audit_tournament_page()
    """

    HEADERS = {
        "User-Agent": "PredictionEngine-TournamentScout/2.0 (contact@predictionengine.app)",
        "Accept": "application/json, text/html",
    }
    # Max chars sent to LLM (80k chars ≈ ~20k tokens — well within Gemini Flash 1M window)
    MAX_CHARS = 80_000

    # ── Public API ────────────────────────────────────────────────────────────

    def audit_with_llm(self, page_title: str) -> dict | None:
        """
        Main entry point. Equivalent to WikipediaScout.audit_tournament_page()
        but powered by LLM semantic understanding.

        Pipeline:
          1. Fetch Wikipedia plaintext & infobox wikitext via REST & Action APIs
          2. Call Gemini Flash for structured JSON extraction
          3. Normalise and return the result dict
          4. If step 1 or 2 fails → fall back to HTML heuristic parser silently
        """
        if not page_title:
            return None

        wiki_url = (
            "https://en.wikipedia.org/wiki/"
            + urllib.parse.quote(page_title.replace(" ", "_"))
        )

        # Step 1 – fetch plaintext & infobox wikitext
        article_text = self._fetch_plaintext(page_title)

        # Step 2 – LLM extraction
        llm_result = None
        if article_text:
            llm_result = self._call_gemini(article_text)

        if llm_result:
            logger.info(
                "LLMWikipediaScout: LLM extraction succeeded for '%s' — "
                "%d fixtures, %d groups",
                page_title,
                llm_result.get("fixtures_count", 0),
                llm_result.get("groups_count", 0),
            )
            return self._normalise(llm_result, page_title, wiki_url)

        # Step 3 – graceful fallback
        logger.info(
            "LLMWikipediaScout: falling back to HTML heuristic for '%s' "
            "(api_key=%s, article_text=%s)",
            page_title,
            "set" if getattr(settings, "GEMINI_API_KEY", "") else "not set",
            "fetched" if article_text else "failed",
        )
        from tournament.services.wikipedia_scout import WikipediaScout
        return WikipediaScout().audit_tournament_page(page_title)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _fetch_plaintext(self, page_title: str) -> str | None:
        """Fetches Wikipedia article clean text & infobox wikitext using modern REST HTML & Action APIs."""
        encoded = urllib.parse.quote(page_title.replace(" ", "_"), safe="")
        parts = []

        # 1. Fetch raw Wikitext via Action API to capture infobox templates (e.g. {{start and end dates|2027|08|25|2027|09|05}})
        try:
            action_url = f"https://en.wikipedia.org/w/api.php?action=parse&page={encoded}&prop=wikitext&format=json"
            resp = requests.get(action_url, headers=self.HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
                if wikitext:
                    infobox_match = re.search(r'(\{\{Infobox[\s\S]*?\n\}\}\n)', wikitext, re.IGNORECASE)
                    if infobox_match:
                        parts.append("=== WIKIPEDIA INFOBOX TEMPLATE ===\n" + infobox_match.group(1))
        except Exception as exc:
            logger.warning("LLMWikipediaScout: Action API wikitext fetch error for '%s': %s", page_title, exc)

        # 2. Fetch full REST HTML page
        try:
            rest_url = f"https://en.wikipedia.org/api/rest_v1/page/html/{encoded}"
            resp = requests.get(rest_url, headers=self.HEADERS, timeout=12)
            if resp.status_code == 200:
                raw_html = getattr(resp, "text", "") or ""
                if isinstance(raw_html, str) and ("<html" in raw_html.lower() or "<div" in raw_html.lower() or "<p" in raw_html.lower() or "body" in raw_html.lower()):
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(raw_html, "html.parser")
                    for s in soup(["script", "style", "noscript", "meta"]):
                        s.decompose()
                    clean_text = re.sub(r"\s+", " ", soup.get_text())
                    parts.append("=== ARTICLE CONTENT ===\n" + clean_text)
                elif hasattr(resp, "json"):
                    # Fallback for JSON dicts or test mocks
                    try:
                        data = resp.json()
                        if isinstance(data, dict):
                            lead_list = [p.get("text", "") for p in data.get("lead", {}).get("sections", []) if isinstance(p, dict)]
                            rem_list = [f"\n== {s.get('line', '')} ==\n" + s.get("text", "") for s in data.get("remaining", {}).get("sections", []) if isinstance(s, dict)]
                            clean = self._strip_html(" ".join(lead_list + rem_list))
                            if clean:
                                parts.append("=== ARTICLE CONTENT ===\n" + clean)
                    except Exception:
                        pass
        except Exception as exc:
            logger.warning("LLMWikipediaScout: REST HTML fetch error for '%s': %s", page_title, exc)

        full_text = "\n\n".join(parts)
        return full_text[: self.MAX_CHARS] if full_text else None

    @staticmethod
    def _strip_html(html: str) -> str:
        """Strips HTML tags and decodes common entities."""
        clean = re.sub(r"<[^>]+>", " ", html)
        for ent, rep in [("&amp;", "&"), ("&nbsp;", " "), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')]:
            clean = clean.replace(ent, rep)
        return re.sub(r"\s{2,}", " ", clean).strip()

    def _call_gemini(self, article_text: str) -> dict | None:
        """Calls Gemini Flash and returns parsed JSON dict, or None on failure."""
        api_key = getattr(settings, "GEMINI_API_KEY", "")
        if not api_key:
            return None

        try:
            import google.generativeai as genai

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                system_instruction=_SYSTEM_PROMPT,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )
            response = model.generate_content(
                f"Wikipedia article text:\n\n{article_text}"
            )
            raw = response.text.strip()
            # Strip markdown fences if present despite application/json mime type
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            return json.loads(raw)

        except json.JSONDecodeError as exc:
            logger.error("LLMWikipediaScout: JSON parse error from Gemini: %s", exc)
            return None
        except Exception as exc:
            logger.error("LLMWikipediaScout: Gemini API error: %s", exc)
            return None

    @staticmethod
    def _clean_team_name(name_str: str) -> str:
        """Strips seed codes (A1, B2), footnote brackets [1], host/champion indicators (H), (Host), and trailing venue/city suffixes."""
        if not name_str:
            return ""
        s = str(name_str).strip()
        # Strip footnote brackets e.g. [1], [a]
        s = re.sub(r'\[\w+\]', '', s)
        # Strip seed prefixes e.g. A1, B2
        s = re.sub(r'^[A-Z]\d\s+', '', s)
        # Strip (H), [H], (Host), (Hosts), (C), (Q), (A), (W) markers anywhere in the name
        s = re.sub(r'\s*[\(\[]\s*(?:H|Host|Hosts|C|Q|A|W)\*?\s*[\)\]]', '', s, flags=re.IGNORECASE)
        # Strip trailing parenthetical text e.g. (Antalya Sports), (Spodek), (Munich)
        s = re.sub(r'\s*\([^\)]*\)\s*$', '', s)

        # Known venue and city suffix cleanup e.g. "Uruguay SAP Garden" -> "Uruguay", "Poland Spodek" -> "Poland"
        venue_suffix_pattern = r'\s+(?:SAP\s+Garden|Porsche.*|Arena.*|Spodek.*|GETEC.*|Wunderino.*|Lanxess.*|ZAG.*|Antalya.*|Tipos.*|Stadion.*|Stadium.*|Hall.*|Centre.*|Center.*|Dome.*|Palace.*|Park.*|Munich|Stuttgart|Kiel|Magdeburg|Hanover|Cologne|Brno|Katowice)$'
        s = re.sub(venue_suffix_pattern, '', s, flags=re.IGNORECASE)

        return s.strip()

    @staticmethod
    def _parse_date_string(date_str: str) -> str:
        """
        Parses a date string (e.g. '11 June 2026', '2026-06-11', 'June 11, 2026')
        into an ISO YYYY-MM-DD string, or returns empty string if unparseable.
        """
        if not date_str:
            return ""
        s = str(date_str).strip()
        if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
            return s
        
        month_map = {
            'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
            'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6, 'july': 7, 'jul': 7,
            'august': 8, 'aug': 8, 'september': 9, 'sep': 9, 'sept': 9,
            'october': 10, 'oct': 10, 'november': 11, 'nov': 11, 'december': 12, 'dec': 12
        }

        # 11 June 2026
        m = re.search(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', s)
        if m and m.group(2).lower() in month_map:
            day = int(m.group(1))
            month = month_map[m.group(2).lower()]
            year = int(m.group(3))
            return f"{year:04d}-{month:02d}-{day:02d}"

        # June 11, 2026
        m = re.search(r'([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})', s)
        if m and m.group(1).lower() in month_map:
            month = month_map[m.group(1).lower()]
            day = int(m.group(2))
            year = int(m.group(3))
            return f"{year:04d}-{month:02d}-{day:02d}"

        return ""

    @staticmethod
    def _parse_date_range(raw_start: str, raw_end: str, page_title: str = "") -> tuple[str, str]:
        """
        Parses start and end dates from raw strings, date ranges, or infobox fields,
        handling formats like '15 May – 29 August 2026', '19–29 August 2026', '3–20 December'.
        """
        combined = f"{raw_start} {raw_end}".strip()
        if not combined:
            return "", ""

        # Infer year from page_title or text if omitted e.g. "3–20 December" in "2026 European Women's..."
        default_year = ""
        clean_title = (page_title or "").replace('_', ' ')
        m_yr = re.search(r'\b(202\d|203\d)\b', f"{clean_title} {combined}")
        if m_yr:
            default_year = m_yr.group(1)

        # Pattern 0a: Wikipedia template {{start and end dates|2027|08|25|2027|09|05...}}
        m0a = re.search(r'start\s+and\s+end\s+dates\|(\d{4})\|(\d{1,2})\|(\d{1,2})\|(\d{4})\|(\d{1,2})\|(\d{1,2})', combined, re.IGNORECASE)
        if m0a:
            return (
                f"{int(m0a.group(1)):04d}-{int(m0a.group(2)):02d}-{int(m0a.group(3)):02d}",
                f"{int(m0a.group(4)):04d}-{int(m0a.group(5)):02d}-{int(m0a.group(6)):02d}"
            )

        # Pattern 0b: ISO range "2027-08-25 – 2027-09-05" or "2027-08-25 to 2027-09-05"
        m0b = re.search(r'(\d{4}-\d{2}-\d{2})\s*[–\-—\s]+\s*(\d{4}-\d{2}-\d{2})', combined)
        if m0b:
            return m0b.group(1), m0b.group(2)

        month_map = {
            'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
            'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6, 'july': 7, 'jul': 7,
            'august': 8, 'aug': 8, 'september': 9, 'sep': 9, 'sept': 9,
            'october': 10, 'oct': 10, 'november': 11, 'nov': 11, 'december': 12, 'dec': 12
        }

        # Pattern 4a: "December 26, 2026 – January 5, 2027" (Month Day, Year – Month Day, Year)
        m4a = re.search(r'([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\s*[–\-—\s]+\s*([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})', combined)
        if m4a and m4a.group(1).lower() in month_map and m4a.group(4).lower() in month_map:
            m1_val, d1, y1 = month_map[m4a.group(1).lower()], int(m4a.group(2)), int(m4a.group(3))
            m2_val, d2, y2 = month_map[m4a.group(4).lower()], int(m4a.group(5)), int(m4a.group(6))
            return f"{y1:04d}-{m1_val:02d}-{d1:02d}", f"{y2:04d}-{m2_val:02d}-{d2:02d}"

        # Pattern 4b: "26 December 2026 – 5 January 2027" (Day Month Year – Day Month Year)
        m4b = re.search(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s*[–\-—\s]+\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', combined)
        if m4b and m4b.group(2).lower() in month_map and m4b.group(5).lower() in month_map:
            d1, m1_val, y1 = int(m4b.group(1)), month_map[m4b.group(2).lower()], int(m4b.group(3))
            d2, m2_val, y2 = int(m4b.group(4)), month_map[m4b.group(5).lower()], int(m4b.group(6))
            return f"{y1:04d}-{m1_val:02d}-{d1:02d}", f"{y2:04d}-{m2_val:02d}-{d2:02d}"

        # Pattern 4c: "December 26 – January 5, 2027" (Month Day – Month Day, Year across year boundary)
        m4c = re.search(r'([A-Za-z]+)\s+(\d{1,2})\s*[–\-—\s]+\s*([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})', combined)
        if m4c and m4c.group(1).lower() in month_map and m4c.group(3).lower() in month_map:
            m1_val, d1 = month_map[m4c.group(1).lower()], int(m4c.group(2))
            m2_val, d2, y2 = month_map[m4c.group(3).lower()], int(m4c.group(4)), int(m4c.group(5))
            y1 = y2 - 1 if m1_val > m2_val else y2
            return f"{y1:04d}-{m1_val:02d}-{d1:02d}", f"{y2:04d}-{m2_val:02d}-{d2:02d}"

        # Pattern 4d: "26 December – 5 January 2027" (Day Month – Day Month Year across year boundary)
        m4d = re.search(r'(\d{1,2})\s+([A-Za-z]+)\s*[–\-—\s]+\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', combined)
        if m4d and m4d.group(2).lower() in month_map and m4d.group(4).lower() in month_map:
            d1, m1_val = int(m4d.group(1)), month_map[m4d.group(2).lower()]
            d2, m2_val, y2 = int(m4d.group(3)), month_map[m4d.group(4).lower()], int(m4d.group(5))
            y1 = y2 - 1 if m1_val > m2_val else y2
            return f"{y1:04d}-{m1_val:02d}-{d1:02d}", f"{y2:04d}-{m2_val:02d}-{d2:02d}"

        # Pattern 1: "15 May – 29 August 2026" or "15 May - 29 August 2026"
        m1 = re.search(r'(\d{1,2})\s+([A-Za-z]+)\s*[–\-—]\s*(\d{1,2})\s+([A-Za-z]+)(?:\s+(\d{4}))?', combined)
        if m1 and m1.group(2).lower() in month_map and m1.group(4).lower() in month_map:
            yr = m1.group(5) or default_year
            if yr:
                d1, m1_val = int(m1.group(1)), month_map[m1.group(2).lower()]
                d2, m2_val = int(m1.group(3)), month_map[m1.group(4).lower()]
                return f"{int(yr):04d}-{m1_val:02d}-{d1:02d}", f"{int(yr):04d}-{m2_val:02d}-{d2:02d}"

        # Pattern 2: "19–29 August 2026" or "3–20 December"
        m2 = re.search(r'(\d{1,2})\s*[–\-—]\s*(\d{1,2})\s+([A-Za-z]+)(?:\s+(\d{4}))?', combined)
        if m2 and m2.group(3).lower() in month_map:
            yr = m2.group(4) or default_year
            if yr:
                d1, d2 = int(m2.group(1)), int(m2.group(2))
                m_val = month_map[m2.group(3).lower()]
                return f"{int(yr):04d}-{m_val:02d}-{d1:02d}", f"{int(yr):04d}-{m_val:02d}-{d2:02d}"

        # Pattern 3: "June 11 – July 19, 2026"
        m3 = re.search(r'([A-Za-z]+)\s+(\d{1,2})\s*[–\-—]\s*([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})', combined)
        if m3 and m3.group(1).lower() in month_map and m3.group(3).lower() in month_map:
            yr = m3.group(5)
            d1, m1_val = int(m3.group(2)), month_map[m3.group(1).lower()]
            d2, m2_val = int(m3.group(4)), month_map[m3.group(3).lower()]
            return f"{int(yr):04d}-{m1_val:02d}-{d1:02d}", f"{int(yr):04d}-{m2_val:02d}-{d2:02d}"

        start_iso = LLMWikipediaScout._parse_date_string(raw_start)
        end_iso   = LLMWikipediaScout._parse_date_string(raw_end)
        return start_iso, end_iso

    @staticmethod
    def _normalise(raw: dict, page_title: str, wiki_url: str) -> dict:
        """Normalises a Gemini response into the canonical audit schema."""
        is_disambiguation = bool(raw.get("is_disambiguation", False))
        sub_tournaments   = raw.get("sub_tournaments") or []

        raw_groups   = raw.get("groups")   or []
        fixtures_raw = raw.get("fixtures") or []

        groups = []
        for g in raw_groups:
            g_name = str(g.get("name") or "").strip()
            g_teams_raw = g.get("teams") or []
            clean_teams = []
            for t in g_teams_raw:
                t_name = str(t.get("name") if isinstance(t, dict) else t).strip()
                t_name = LLMWikipediaScout._clean_team_name(t_name)
                if t_name:
                    clean_teams.append({"name": t_name})
            if g_name:
                groups.append({"name": g_name, "teams": clean_teams})

        fixtures = []
        for fix in fixtures_raw:
            home = LLMWikipediaScout._clean_team_name(str(fix.get("home_team") or ""))
            away = LLMWikipediaScout._clean_team_name(str(fix.get("away_team") or ""))
            if not home or not away:
                continue
            fixtures.append({
                "home_team":      home,
                "away_team":      away,
                "date":           str(fix.get("date")           or ""),
                "time":           str(fix.get("time")           or ""),
                "venue":          str(fix.get("venue")          or ""),
                "stage_or_group": str(fix.get("stage_or_group") or "Gruppspel"),
                "is_placeholder": bool(fix.get("is_placeholder", False)),
                "confidence":     0.85,
                "strategy":       "LLM_Gemini_Flash",
            })

        if len(fixtures) < 5 and page_title:
            try:
                from tournament.services.wikipedia_scout import WikipediaScout
                h_audit = WikipediaScout().audit_tournament_page(page_title)
                if h_audit and isinstance(h_audit, dict):
                    h_fixs = h_audit.get('fixtures', [])
                    if h_fixs:
                        seen = {f"{f.get('home_team')}_vs_{f.get('away_team')}" for f in fixtures}
                        for hf in h_fixs:
                            k = f"{hf.get('home_team')}_vs_{hf.get('away_team')}"
                            if k not in seen:
                                seen.add(k)
                                fixtures.append(hf)
            except Exception as e:
                logger.warning("Error merging heuristic fixtures into LLM audit: %s", e)

        fixtures_count      = max(int(raw.get("fixtures_count") or 0), len(fixtures))
        groups_count        = int(raw.get("groups_count")        or len(groups))
        teams_count         = int(raw.get("teams_count")         or 0)
        scheduled_matchdays = int(raw.get("scheduled_matchdays") or 0)

        if not teams_count and groups:
            teams_count = sum(len(g.get("teams", [])) for g in groups)
        if not fixtures_count:
            fixtures_count = len(fixtures)

        fixtures_have_placeholders = bool(fixtures) and any(
            f.get("is_placeholder") for f in fixtures
        )

        knockout_stages = raw.get("knockout_stages") or []
        if not knockout_stages:
            knockout_stages = ["Quarterfinals", "Semifinals", "Final"]

        # Parse & normalise tournament start and end dates using _parse_date_range
        raw_start = str(raw.get("tournament_start_date") or raw.get("start_date") or "").strip()
        raw_end   = str(raw.get("tournament_end_date") or raw.get("end_date") or "").strip()

        parsed_start, parsed_end = LLMWikipediaScout._parse_date_range(raw_start, raw_end, page_title)

        # Fallback: check earliest fixture date if start date not explicitly provided
        if not parsed_start and fixtures:
            first_fix_date = fixtures[0].get("date", "")
            parsed_start = LLMWikipediaScout._parse_date_string(first_fix_date)

        return {
            "page_title":                 page_title,
            "wiki_url":                   wiki_url,
            "is_disambiguation":          is_disambiguation,
            "is_ongoing_or_finished":     bool(raw.get("is_ongoing_or_finished", False)),
            "sub_tournaments":            sub_tournaments,
            "sections":                   [],
            "teams_count":                teams_count or 16,
            "groups_count":               groups_count,
            "groups":                     groups,
            "fixtures":                   fixtures,
            "fixtures_count":             fixtures_count,
            "scheduled_matchdays":        scheduled_matchdays,
            "fixtures_have_placeholders": fixtures_have_placeholders,
            "draw_completed":             bool(raw.get("draw_completed",   False)),
            "draw_date":                  str(raw.get("draw_date")         or ""),
            "tournament_start_date":      parsed_start,
            "tournament_end_date":        parsed_end,
            "start_date":                 parsed_start,
            "end_date":                   parsed_end,
            "date_reasoning":             str(raw.get("date_reasoning")    or ""),
            "advancement_rules":          str(raw.get("advancement_rules") or ""),
            "official_rules":             str(raw.get("official_rules") or raw.get("advancement_rules") or ""),
            "official_regulations_url":   str(raw.get("official_regulations_url") or ""),
            "fixtures_completed":         bool(raw.get("fixtures_completed", False)),
            "knockout_stages":            knockout_stages,
            "host_country":               str(raw.get("host_country")      or ""),
            "logo_url":                   str(raw.get("logo_url")          or ""),
        }
