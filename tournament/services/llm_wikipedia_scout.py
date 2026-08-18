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
  "teams_count": <integer>,
  "host_country": "<string>",
  "groups": [
    {
      "name": "<e.g. Group A>",
      "teams": [{"name": "<team name>"}, ...]
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
  "knockout_stages": ["Round of 16", "Quarterfinals", "Semifinals", "Final"],
  "fixtures_count": <integer>,
  "groups_count": <integer>,
  "fixtures_completed": <true|false>
}
"""

_SYSTEM_PROMPT = (
    "You are an expert sports data analyst. You will be given the plaintext content of a "
    "Wikipedia article about a sports tournament. Extract the structured tournament information. "
    "Use placeholder codes exactly as written (TBD, W37, 1A, etc). "
    "For qualifying or league-format tournaments with matchday schedules but no individual "
    "fixtures yet, set scheduled_matchdays to the number of matchday rounds and leave "
    "fixtures as an empty list. "
    "If a draw has been announced for a future date but not yet held, set draw_completed=false "
    "and record the draw_date. "
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

    WIKIPEDIA_REST = "https://en.wikipedia.org/api/rest_v1/page/mobile-sections/"
    HEADERS = {
        "User-Agent": "PredictionEngine-TournamentScout/2.0 (contact@predictionengine.app)",
        "Accept": "application/json",
    }
    # Max chars sent to LLM (80k chars ≈ ~20k tokens — well within Gemini Flash 1M window)
    MAX_CHARS = 80_000

    # ── Public API ────────────────────────────────────────────────────────────

    def audit_with_llm(self, page_title: str) -> dict | None:
        """
        Main entry point. Equivalent to WikipediaScout.audit_tournament_page()
        but powered by LLM semantic understanding.

        Pipeline:
          1. Fetch Wikipedia plaintext via REST API
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

        # Step 1 – fetch plaintext
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
        """Fetches Wikipedia article as clean plaintext via the mobile-sections REST API."""
        encoded = urllib.parse.quote(page_title.replace(" ", "_"), safe="")
        url = self.WIKIPEDIA_REST + encoded
        try:
            resp = requests.get(url, headers=self.HEADERS, timeout=15)
            if resp.status_code != 200:
                logger.warning(
                    "LLMWikipediaScout: Wikipedia REST %d for '%s'",
                    resp.status_code, page_title,
                )
                return None

            data = resp.json()
            parts = []

            # Lead section
            for para in data.get("lead", {}).get("sections", []):
                text = para.get("text", "")
                if text:
                    parts.append(self._strip_html(text))

            # Remaining sections
            for section in data.get("remaining", {}).get("sections", []):
                title = section.get("line", "")
                text  = section.get("text", "")
                if title:
                    parts.append(f"\n== {self._strip_html(title)} ==\n")
                if text:
                    parts.append(self._strip_html(text))

            full_text = "\n".join(parts)
            return full_text[: self.MAX_CHARS] if full_text else None

        except Exception as exc:
            logger.error("LLMWikipediaScout: fetch failed for '%s': %s", page_title, exc)
            return None

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
    def _normalise(raw: dict, page_title: str, wiki_url: str) -> dict:
        """Normalises a Gemini response into the canonical audit schema."""
        groups       = raw.get("groups")   or []
        fixtures_raw = raw.get("fixtures") or []

        fixtures = []
        for fix in fixtures_raw:
            home = str(fix.get("home_team") or "").strip()
            away = str(fix.get("away_team") or "").strip()
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

        fixtures_count      = int(raw.get("fixtures_count")      or len(fixtures))
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

        return {
            "page_title":                 page_title,
            "wiki_url":                   wiki_url,
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
            "advancement_rules":          str(raw.get("advancement_rules") or ""),
            "fixtures_completed":         bool(raw.get("fixtures_completed", False)),
            "knockout_stages":            knockout_stages,
            "host_country":               str(raw.get("host_country")      or ""),
        }
