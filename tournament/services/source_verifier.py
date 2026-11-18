"""
Multi-Channel Tournament Source Verifier
========================================
Implements the "Wikipedia as Map, Multi-Channel Verifier" pattern:
1. Validates candidate official URLs (rejects 404s, Google search fallbacks, and Wikipedia).
2. Channel A (Direct Structured): Queries Wikidata Special:EntityData JSON and checks HTTP health.
3. Channel B (Search-Grounded): Uses Gemini Google Search Grounding (site:<official_domain>)
   for federation portals that block direct scraping (e.g., 403 Cloudflare on iihf.com, WAF on uefa.com)
   or publish schedules in PDFs/apps (e.g., floorball.sport).
4. Produces per-field provenance (VERIFIED / WIKIPEDIA_ONLY / CONFLICT) so GRADE_A
   is only awarded when core fields are verified by non-Wikipedia sources.
"""

import datetime
import json
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_NON_OFFICIAL_DOMAINS = (
    "wikipedia.org",
    "wikidata.org",
    "wikimedia.org",
    "google.com",
    "youtube.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
)


class TournamentSourceVerifier:
    """Per-field triangulating verifier for tournament metadata, groups, and fixtures."""

    @staticmethod
    def is_valid_official_candidate(url: str) -> bool:
        """Returns True if url is an http(s) URL not pointing to Wikipedia, search engines, or social media."""
        if not url or not isinstance(url, str):
            return False
        u = url.strip()
        if not u.startswith(("http://", "https://")):
            return False
        netloc = urllib.parse.urlparse(u).netloc.lower()
        if not netloc:
            return False
        return not any(bad in netloc for bad in _NON_OFFICIAL_DOMAINS)

    @staticmethod
    def is_news_or_root_url(url: str) -> bool:
        """Detects generic root homepages or news/press-release articles that are poor primary portals."""
        if not url:
            return True
        parsed = urllib.parse.urlparse(url.strip())
        path = (parsed.path or "").strip("/")
        if not path:
            return True
        if re.search(r"/(news|article|story|press-release|blog)/", parsed.path.lower()):
            return True
        return False

    @classmethod
    def validate_url(cls, url: str, timeout: int = 6) -> Tuple[str, int, str]:
        """
        Probes a candidate URL and classifies its reachability:
        - ('OK', status, final_url) for 2xx responses
        - ('WAF_BLOCKED', status, url) for 403/429/timeout on valid official domains
        - ('DEAD', status, url) for 404/410/5xx or invalid URLs
        """
        if not cls.is_valid_official_candidate(url):
            return ("DEAD", 0, "")
        try:
            resp = requests.get(
                url.strip(),
                headers=_BROWSER_HEADERS,
                timeout=timeout,
                allow_redirects=True,
                stream=True,
            )
            code = resp.status_code
            final_url = resp.url or url.strip()
            resp.close()
            if 200 <= code < 300:
                return ("OK", code, final_url)
            if code in (403, 429):
                return ("WAF_BLOCKED", code, url.strip())
            if code in (404, 410) or code >= 500:
                return ("DEAD", code, url.strip())
            return ("WAF_BLOCKED", code, url.strip())
        except requests.Timeout:
            return ("WAF_BLOCKED", 0, url.strip())
        except Exception as exc:
            logger.debug("SourceVerifier: URL probe failed for %s: %s", url, exc)
            return ("DEAD", 0, url.strip())

    @staticmethod
    def fetch_wikidata_claims(wiki_url: str = "", qid: str = "") -> Dict[str, Any]:
        """
        Channel A: Fetches structured claims (P580 start, P582 end, P856 website, P17, P664)
        from Wikidata without consuming Gemini quota.
        """
        result: Dict[str, Any] = {"qid": qid or ""}
        try:
            if not result["qid"] and wiki_url and "wikipedia.org/wiki/" in wiki_url:
                title = urllib.parse.unquote(wiki_url.split("/wiki/", 1)[1].split("#")[0])
                api_url = (
                    "https://en.wikipedia.org/w/api.php?action=query&prop=pageprops"
                    f"&titles={urllib.parse.quote(title)}&format=json"
                )
                r = requests.get(api_url, headers=_BROWSER_HEADERS, timeout=6)
                if r.status_code == 200:
                    pages = (r.json().get("query") or {}).get("pages") or {}
                    for page_obj in pages.values():
                        wd_item = (page_obj.get("pageprops") or {}).get("wikibase_item")
                        if wd_item:
                            result["qid"] = wd_item
                            break

            if not result["qid"]:
                return result

            entity_url = f"https://www.wikidata.org/wiki/Special:EntityData/{result['qid']}.json"
            er = requests.get(entity_url, headers=_BROWSER_HEADERS, timeout=8)
            if er.status_code != 200:
                return result
            entities = er.json().get("entities") or {}
            entity = entities.get(result["qid"]) or (next(iter(entities.values()), {}))
            claims = entity.get("claims") or {}

            def _extract_iso_date(prop_id: str) -> str:
                for stmt in claims.get(prop_id, []):
                    val = (stmt.get("mainsnak") or {}).get("datavalue", {}).get("value")
                    if isinstance(val, dict) and val.get("time"):
                        m = re.search(r"(\d{4}-\d{2}-\d{2})", val["time"])
                        if m:
                            return m.group(1)
                return ""

            result["start_date"] = _extract_iso_date("P580")
            result["end_date"] = _extract_iso_date("P582")

            websites: List[str] = []
            for stmt in claims.get("P856", []):
                val = (stmt.get("mainsnak") or {}).get("datavalue", {}).get("value")
                if isinstance(val, str) and val.startswith(("http://", "https://")):
                    websites.append(val)
            result["official_websites"] = websites
        except Exception as exc:
            logger.debug("SourceVerifier: Wikidata fetch error: %s", exc)
        return result

    @staticmethod
    def _parse_date(date_str: str) -> Optional[datetime.date]:
        if not date_str:
            return None
        try:
            return datetime.date.fromisoformat(str(date_str).strip()[:10])
        except Exception:
            return None

    @classmethod
    def _search_grounded_verify(
        cls,
        tournament_name: str,
        sport: str,
        official_domain: str,
        candidate_map: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Channel B: Uses Gemini Google Search Grounding (constrained to official_domain when known)
        to independently verify dates, groups/teams, and schedule/opener existence.
        """
        api_key = getattr(settings, "GEMINI_API_KEY", "")
        if not api_key:
            return {}

        try:
            from tournament.services.gemini_scout_service import GeminiScoutService
            if not GeminiScoutService.is_available():
                return {}

            domain_hint = f"site:{official_domain} OR " if official_domain else ""
            map_groups = candidate_map.get("groups") or []
            map_groups_summary = [
                {
                    "name": g.get("name"),
                    "teams": [t.get("name") if isinstance(t, dict) else str(t) for t in (g.get("teams") or [])],
                }
                for g in map_groups[:12]
            ]

            prompt = (
                f"Verify the official tournament facts for '{tournament_name}' ({sport}) "
                f"using non-Wikipedia official sources ({domain_hint}official governing body / federation website).\n"
                f"Candidate map to verify:\n"
                f"- start_date: {candidate_map.get('start_date') or 'unknown'}\n"
                f"- end_date: {candidate_map.get('end_date') or 'unknown'}\n"
                f"- groups_and_teams: {json.dumps(map_groups_summary, ensure_ascii=False)}\n\n"
                "Return ONLY valid JSON with these exact keys:\n"
                "{\n"
                '  "official_competition_url": "best official tournament portal URL (not news/homepage if competition page exists)",\n'
                '  "start_date": "YYYY-MM-DD or empty string",\n'
                '  "end_date": "YYYY-MM-DD or empty string",\n'
                '  "dates_verified_by_official": true/false,\n'
                '  "groups_verified_by_official": true/false,\n'
                '  "verified_groups": [{"name": "Group A", "teams": ["Team 1", "Team 2"]}],\n'
                '  "fixtures_verified_by_official": true/false,\n'
                '  "opening_match_summary": "e.g. Sweden vs Finland on 2026-12-26, or empty string",\n'
                '  "verifying_source_name": "e.g. iihf.com / floorball.sport / the-afc.com"\n'
                "}"
            )

            data = GeminiScoutService.generate_json(
                prompt=prompt,
                search_grounding=True,
                temperature=0.0,
                timeout=15.0,
            )
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.warning("SourceVerifier: Grounded verification failed for '%s': %s", tournament_name, exc)
            return {}

    @classmethod
    def verify_map(
        cls,
        tournament_name: str,
        sport: str,
        candidate_map: Dict[str, Any],
        existing_official_url: str = "",
        wiki_url: str = "",
        wikidata_qid: str = "",
        use_grounded_search: bool = True,
    ) -> Dict[str, Any]:
        """
        Triangulates candidate_map fields against URL health, Wikidata (Channel A),
        and Search Grounding (Channel B). Returns verified values and per-field provenance.
        """
        now_iso = timezone.now().isoformat()
        map_start = str(candidate_map.get("start_date") or "")[:10]
        map_end = str(candidate_map.get("end_date") or "")[:10]
        map_groups = candidate_map.get("groups") or []
        map_fixtures = candidate_map.get("fixtures") or []
        has_real_map_teams = bool(candidate_map.get("has_real_teams"))

        # 1. Channel A: Wikidata
        wd = cls.fetch_wikidata_claims(wiki_url=wiki_url, qid=wikidata_qid)
        resolved_qid = wd.get("qid") or wikidata_qid

        # 2. Candidate official URL selection & HTTP validation
        url_candidates: List[str] = []
        for u in [
            existing_official_url,
            candidate_map.get("official_website_url") or "",
            *(wd.get("official_websites") or []),
        ]:
            if u and u not in url_candidates and cls.is_valid_official_candidate(u):
                url_candidates.append(u.strip())

        best_url = ""
        best_url_state = "DEAD"
        for u in url_candidates:
            state, _code, final_u = cls.validate_url(u)
            if state == "OK" and not cls.is_news_or_root_url(final_u):
                best_url = final_u
                best_url_state = "OK"
                break
            if state == "OK" and not best_url:
                best_url = final_u
                best_url_state = "OK"
            elif state == "WAF_BLOCKED" and not best_url:
                best_url = u
                best_url_state = "WAF_BLOCKED"

        official_domain = ""
        if best_url:
            netloc = urllib.parse.urlparse(best_url).netloc.lower()
            official_domain = netloc[4:] if netloc.startswith("www.") else netloc

        # 3. Channel B: Search-Grounded Verification (when needed or WAF/generic URL)
        grounded: Dict[str, Any] = {}
        if use_grounded_search:
            grounded = cls._search_grounded_verify(
                tournament_name=tournament_name,
                sport=sport,
                official_domain=official_domain,
                candidate_map=candidate_map,
            )

        grounded_url = (grounded.get("official_competition_url") or "").strip()
        if grounded_url and cls.is_valid_official_candidate(grounded_url):
            g_state, _gcode, g_final = cls.validate_url(grounded_url)
            if g_state == "OK" and (not best_url or cls.is_news_or_root_url(best_url)):
                best_url = g_final
                best_url_state = "OK"
            elif g_state == "WAF_BLOCKED" and (not best_url or cls.is_news_or_root_url(best_url)):
                best_url = grounded_url
                best_url_state = "WAF_BLOCKED"

        verifying_name = grounded.get("verifying_source_name") or official_domain or "Official Source"

        # 4. Per-Field Triangulation
        fields: Dict[str, Dict[str, Any]] = {}

        # 4a. Official URL field
        if best_url and best_url_state in ("OK", "WAF_BLOCKED") and not cls.is_news_or_root_url(best_url):
            fields["official_url"] = {
                "status": "VERIFIED",
                "source": verifying_name,
                "url": best_url,
                "http_state": best_url_state,
            }
        elif best_url and best_url_state in ("OK", "WAF_BLOCKED"):
            fields["official_url"] = {
                "status": "VERIFIED" if grounded.get("dates_verified_by_official") else "WIKIPEDIA_ONLY",
                "source": verifying_name,
                "url": best_url,
                "http_state": best_url_state,
                "note": "Generic root/news URL",
            }
        else:
            fields["official_url"] = {
                "status": "CONFLICT",
                "source": "None",
                "url": "",
                "note": "No reachable official competition URL found",
            }

        # 4b. Dates field (Map vs Wikidata vs Grounded Search)
        g_start = str(grounded.get("start_date") or "")[:10]
        g_end = str(grounded.get("end_date") or "")[:10]
        wd_start = wd.get("start_date") or ""
        wd_end = wd.get("end_date") or ""

        d_map_s = cls._parse_date(map_start)
        d_g_s = cls._parse_date(g_start)
        d_wd_s = cls._parse_date(wd_start)

        final_start = g_start or map_start or wd_start
        final_end = g_end or map_end or wd_end

        if d_g_s and grounded.get("dates_verified_by_official"):
            # Grounded official source is authoritative over stale Wikidata
            note = ""
            if d_wd_s and abs((d_g_s - d_wd_s).days) > 7:
                note = f"Wikidata stale ({wd_start}); official source confirms {g_start}"
            fields["dates"] = {
                "status": "VERIFIED",
                "source": verifying_name,
                "url": best_url,
                "note": note,
            }
        elif d_map_s and d_wd_s:
            if abs((d_map_s - d_wd_s).days) <= 7:
                fields["dates"] = {
                    "status": "VERIFIED",
                    "source": f"Wikidata ({resolved_qid})",
                    "url": f"https://www.wikidata.org/wiki/{resolved_qid}" if resolved_qid else "",
                }
            else:
                fields["dates"] = {
                    "status": "CONFLICT",
                    "source": "Wikipedia vs Wikidata",
                    "url": wiki_url,
                    "note": f"Map {map_start} differs from Wikidata {wd_start}",
                }
        elif final_start:
            fields["dates"] = {
                "status": "WIKIPEDIA_ONLY",
                "source": "Wikipedia",
                "url": wiki_url,
            }
        else:
            fields["dates"] = {
                "status": "CONFLICT",
                "source": "None",
                "url": "",
                "note": "Start date missing",
            }

        # 4c. Groups & Teams field
        g_groups = grounded.get("verified_groups") or []
        if grounded.get("groups_verified_by_official") and (len(g_groups) >= 2 or has_real_map_teams):
            fields["groups_teams"] = {
                "status": "VERIFIED",
                "source": verifying_name,
                "url": best_url,
            }
        elif has_real_map_teams and len(map_groups) >= 2:
            fields["groups_teams"] = {
                "status": "WIKIPEDIA_ONLY",
                "source": "Wikipedia",
                "url": wiki_url,
            }
        else:
            fields["groups_teams"] = {
                "status": "WIKIPEDIA_ONLY",
                "source": "Pending draw",
                "url": wiki_url or best_url,
            }

        # 4d. Fixtures field
        if grounded.get("fixtures_verified_by_official") and len(map_fixtures) >= 4:
            fields["fixtures"] = {
                "status": "VERIFIED",
                "source": verifying_name,
                "url": best_url,
                "note": grounded.get("opening_match_summary") or "",
            }
        elif len(map_fixtures) >= 4:
            fields["fixtures"] = {
                "status": "WIKIPEDIA_ONLY",
                "source": "Wikipedia",
                "url": wiki_url,
                "note": "Fixtures parsed from Wikipedia; official schedule not directly verified",
            }
        else:
            fields["fixtures"] = {
                "status": "WIKIPEDIA_ONLY",
                "source": "Pending schedule",
                "url": wiki_url or best_url,
            }

        core_keys = ("dates", "official_url", "groups_teams", "fixtures")
        all_core_verified = all(fields[k]["status"] == "VERIFIED" for k in core_keys)
        has_conflict = any(fields[k]["status"] == "CONFLICT" for k in core_keys)

        return {
            "official_source_url": best_url,
            "start_date": final_start,
            "end_date": final_end,
            "wikidata_qid": resolved_qid,
            "fields": fields,
            "all_core_verified": all_core_verified,
            "has_conflict": has_conflict,
            "grounded_groups": g_groups,
            "verifying_source_name": verifying_name,
            "checked_at": now_iso,
        }
