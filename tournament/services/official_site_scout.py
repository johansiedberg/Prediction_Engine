import logging
import re
import urllib.parse
import requests
from typing import Optional

logger = logging.getLogger(__name__)


class OfficialSiteScout:
    """
    Automated Finder & Source Ranker for Official Sports Federation Websites & Tournament Portals.
    Discovers authoritative URLs (CAF, CONCACAF, UEFA, FIFA, FIBA, IFF, IIHF, World Aquatics,
    World Curling, IHF, World Rugby, ICC, etc.) using:
    1. Wikidata property P856 & Wikipedia external links
    2. Google Search queries ('[Name] groups', '[Name] draw lottery', '[Name] fixtures', '[Name] rules')
    3. Authority-based multi-tier domain scoring
    """
    HEADERS = {
        'User-Agent': 'PredictionEngine-OfficialScout/1.0 (contact@predictionengine.app)'
    }

    FEDERATION_DOMAINS = [
        'uefa.com', 'fifa.com', 'concacaf.com', 'the-afc.com', 'asiancup2027.sa',
        'cafonline.com', 'fiba.basketball', 'iff.sport', 'iihf.com', 'worldaquatics.com',
        'ihf.info', 'world.rugby', 'icc-cricket.com', 'fivb.com', 'worldathletics.org',
        'worldcurling.org', 'ittf.com', 'bwfbadminton.com', 'worldrowing.com',
        'canoeicf.com', 'worldpadel.org', 'cev.eu', 'conmebol.com', 'ofc.org'
    ]

    TRUSTED_MEDIA_DOMAINS = [
        'bbc.com', 'bbc.co.uk', 'reuters.com', 'espn.com', 'skysports.com',
        'apnews.com', 'flashscore.com', 'sofascore.com'
    ]

    @classmethod
    def rank_source_url(cls, url: str, tournament_name: str = "") -> Dict[str, Any]:
        """
        Computes an authority score (0 to 100) and categorization for any candidate URL.
        """
        if not url or not isinstance(url, str):
            return {"score": 0, "category": "INVALID", "url": ""}

        u_lower = url.lower()
        score = 0
        category = "WEB"

        # Tier 1: Official Federation Portals
        if any(d in u_lower for d in cls.FEDERATION_DOMAINS):
            score = 60
            category = "OFFICIAL_FEDERATION"
            # High boost for dedicated competition hubs, regulations, and draw press releases
            if re.search(r'/(news|press-release|regulations|competitions|standings|draw|qualification|format)/', u_lower):
                score += 25
            if any(k in u_lower for k in ['draw', 'qualifier', 'schedule', 'rules', 'pot', 'groups']):
                score += 10
            if u_lower.endswith('.pdf'):
                score += 5

        # Tier 2: Dedicated Official Tournament Domains (e.g. asiancup2027.sa)
        elif tournament_name and any(slug in u_lower for slug in [
            re.sub(r'[^a-z0-9]', '', tournament_name.lower()),
            re.sub(r'[^a-z0-9]', '-', tournament_name.lower()),
        ]):
            score = 45
            category = "OFFICIAL_TOURNAMENT_SITE"
            if 'official' in u_lower or 'portal' in u_lower:
                score += 15

        # Tier 3: Primary Trusted Sports Media
        elif any(d in u_lower for d in cls.TRUSTED_MEDIA_DOMAINS):
            score = 30
            category = "TRUSTED_MEDIA"
            if any(k in u_lower for k in ['draw', 'groups', 'schedule', 'fixtures', 'format']):
                score += 10

        # Tier 4: Open Encyclopedias & Registries
        elif 'wikipedia.org' in u_lower or 'wikidata.org' in u_lower or 'allsportdb.com' in u_lower:
            score = 20
            category = "OPEN_REGISTRY"
        else:
            score = 10
            category = "GENERAL_WEB"

        return {
            "score": score,
            "category": category,
            "url": url,
        }

    @classmethod
    def discover_official_site(cls, tournament_name: str, wikipedia_title: Optional[str] = None) -> Optional[str]:
        """
        Discovers the official tournament website or press release URL for a given tournament.
        Returns canonical URL or None.
        """
        if not tournament_name:
            return None

        # 1. Resolve Wikipedia title if not provided
        title = wikipedia_title
        if not title:
            try:
                from tournament.services.wikipedia_scout import WikipediaScout
                title = WikipediaScout().search_wikipedia_article(tournament_name)
            except Exception as e:
                logger.warning("OfficialSiteScout: Search title resolution error: %s", e)

        candidate_links = []

        if title:
            # 1a. Check Wikidata property P856
            try:
                from tournament.services.wikidata_scout import WikidataScout
                w_data = WikidataScout.fetch_wikidata_entity(title)
                off_site = w_data.get('official_website_url')
                if off_site and isinstance(off_site, str) and off_site.startswith('http'):
                    candidate_links.append(off_site)
            except Exception as e:
                logger.warning("OfficialSiteScout: Wikidata P856 lookup error: %s", e)

            # 1b. Query Wikipedia external links (prop=extlinks)
            try:
                ext_url = 'https://en.wikipedia.org/w/api.php'
                params = {'action': 'query', 'prop': 'extlinks', 'titles': title, 'format': 'json', 'ellimit': 50}
                r = requests.get(ext_url, params=params, headers=cls.HEADERS, timeout=10)
                if r.status_code == 200:
                    pages = r.json().get('query', {}).get('pages', {})
                    for pid, p in pages.items():
                        if 'extlinks' in p:
                            for l in p['extlinks']:
                                if isinstance(l, dict) and '*' in l:
                                    candidate_links.append(l['*'])
            except Exception as exc:
                logger.warning("OfficialSiteScout: Wikipedia extlinks fetch error for '%s': %s", title, exc)

        # 2. Score and rank all discovered links
        ranked = [cls.rank_source_url(link, tournament_name) for link in candidate_links if link.startswith('http')]
        ranked.sort(key=lambda x: x['score'], reverse=True)

        if ranked and ranked[0]['score'] >= 30:
            return ranked[0]['url']

        # Fallback to first non-wikipedia link if present
        for item in ranked:
            if 'wikipedia.org' not in item['url'] and 'wikimedia.org' not in item['url']:
                return item['url']

        return None

    @classmethod
    def search_and_rank_tournament_sources(cls, tournament_name: str, sport: str = "Football") -> List[Dict[str, Any]]:
        """
        Executes targeted search queries:
        1. "[Tournament Name] groups"
        2. "[Tournament Name] draw lottery date"
        3. "[Tournament Name] fixtures schedule"
        4. "[Tournament Name] rules regulations"
        
        Collects candidates from Google Search Grounding and ranks them by authority.
        """
        if not tournament_name:
            return []

        ranked_sources = []
        seen_urls = set()

        # Check existing official site discovery
        direct_official = cls.discover_official_site(tournament_name)
        if direct_official:
            meta = cls.rank_source_url(direct_official, tournament_name)
            meta['title'] = f"{tournament_name} (Official Federation Portal)"
            ranked_sources.append(meta)
            seen_urls.add(direct_official)

        # Generate targeted search queries
        queries = [
            f'"{tournament_name}" groups draw',
            f'"{tournament_name}" official draw date lottery',
            f'"{tournament_name}" qualification pathway format regulations',
            f'"{tournament_name}" fixtures schedule'
        ]

        from tournament.services.gemini_scout_service import GeminiScoutService
        if GeminiScoutService.is_available():
            try:
                # Query Gemini with Google Search Grounding for ranked sources
                search_prompt = (
                    f"Perform Google Search for the tournament '{tournament_name}' ({sport}) using queries:\n"
                    f"- {queries[0]}\n- {queries[1]}\n- {queries[2]}\n- {queries[3]}\n\n"
                    "Return a JSON list of authoritative web sources with fields: 'url', 'title', 'relevance_summary'."
                )
                grounded_res = GeminiScoutService.generate_json_with_metadata(
                    prompt=search_prompt,
                    search_grounding=True,
                    timeout=8.0
                )
                if grounded_res and "sources" in grounded_res:
                    for src in grounded_res["sources"]:
                        u = src.get("url", "")
                        if u and u.startswith("http") and u not in seen_urls:
                            meta = cls.rank_source_url(u, tournament_name)
                            meta["title"] = src.get("title", "")
                            meta["relevance_summary"] = src.get("relevance_summary", "")
                            ranked_sources.append(meta)
                            seen_urls.add(u)
            except Exception as e:
                logger.debug("OfficialSiteScout: Google search grounding error for '%s': %s", tournament_name, e)

        # Sort all sources by score descending
        ranked_sources.sort(key=lambda x: x["score"], reverse=True)
        return ranked_sources
