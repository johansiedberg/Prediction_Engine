import logging
import re
import urllib.parse
import urllib3
import requests
from typing import Optional, Dict, Any

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)


def is_valid_tournament_logo(url: str) -> bool:
    """
    Strictly validates whether a candidate image URL is a valid tournament emblem/logo,
    rejecting country flags, location maps, trophy photos, stadium pictures, and non-emblem noise.
    """
    if not url or not isinstance(url, str):
        return False

    url_lower = url.lower().strip()
    if not url_lower.startswith(('http://', 'https://')):
        return False

    # Rejected non-emblem noise keywords
    invalid_keywords = [
        'flag_of', 'flag%20of', 'flag%5fof', 'flag-', 'flag_',
        'bandeira', 'drapeau', 'bandera', 'flagg', 'flag.', 'flag-icon', 'country-flag',
        'stadium', 'arena', 'stade', 'venue', 'map_of', 'location_map', 'carte_de',
        'map.svg', 'map.png', 'map.jpg', 'map.jpeg', '_map', '-map', '%20map', 'associations_map', 'member_associations',
        'trophy', 'pokal', 'trofeo', 'trophe', 'medaille', 'medal',
        'crowd', 'spectators', 'team_photo', 'roster', 'ball', 'pitch',
        'photo-resources', 'photo_resources', 'action-photo', '_vs_', '-vs-', 'vs_', 'vs-',
        'day-1', 'day-2', 'day-3', 'day_1', 'day_2', 'day_3', 'group-a', 'group-b',
        'bg_', 'background', 'banner_bg', 'header_bg', 'hero_bg', 'afc_bg',
        'fallback', 'fallback-image', 'fallback_image',
        'avatar', 'user_icon', 'blank.png', 'spacer.gif', 'favicon'
    ]


    for pattern in invalid_keywords:
        if pattern in url_lower:
            return False

    return True


class EmblemScout:
    """
    Authoritative Multi-Source Emblem Discovery Agent for Sports Tournaments.
    Orchestrates 5 resolution channels:
    1. Wikidata P154 (Official Emblem) with Parent Tournament Fallback
    2. Wikimedia Commons API Search ('[Tournament Name] emblem/logo')
    3. Wikipedia Infobox & PageImages API
    4. Official Webpage Open-Graph & HTML <img> Tags (Event/Tournament Logos)
    5. Gemini Flash AI Search Prompt Fallback
    6. Strict Non-Emblem Filtering Guard
    """

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 PredictionEngine/3.0'
    }

    CANONICAL_EMBLEM_MAP = {
        '2027 afc asian cup': 'https://upload.wikimedia.org/wikipedia/en/5/50/2027_AFC_Asian_Cup_logo.svg',
        'afc asian cup': 'https://commons.wikimedia.org/wiki/Special:FilePath/AFC_Asian_Cup_logo.svg',
        'asian cup': 'https://commons.wikimedia.org/wiki/Special:FilePath/AFC_Asian_Cup_logo.svg',
        'uefa nations league': 'https://commons.wikimedia.org/wiki/Special:FilePath/UEFA_Nations_League_logo.svg',
        'concacaf nations league': 'https://commons.wikimedia.org/wiki/Special:FilePath/Concacaf_Nations_League_logo.svg',
        'copa américa': 'https://commons.wikimedia.org/wiki/Special:FilePath/Copa_Am%C3%A9rica_logo.svg',
        'copa america': 'https://commons.wikimedia.org/wiki/Special:FilePath/Copa_Am%C3%A9rica_logo.svg',
        'africa cup of nations': 'https://commons.wikimedia.org/wiki/Special:FilePath/Africa_Cup_of_Nations_logo.svg',
        'afcon': 'https://commons.wikimedia.org/wiki/Special:FilePath/Africa_Cup_of_Nations_logo.svg',
        'uefa euro 2028': 'https://commons.wikimedia.org/wiki/Special:FilePath/UEFA_Euro_2028_Logo.svg',
        '2026 fifa world cup': 'https://commons.wikimedia.org/wiki/Special:FilePath/2026_FIFA_World_Cup_emblem.svg',
        'fifa world cup 2026': 'https://commons.wikimedia.org/wiki/Special:FilePath/2026_FIFA_World_Cup_emblem.svg',
    }

    @classmethod
    def discover_official_emblem(cls, tournament_name: str, official_url: Optional[str] = None, wikidata_qid: Optional[str] = None) -> str:
        """
        Discovers the canonical official emblem logo URL for a given tournament name.
        Returns the resolved image URL string or empty string if not found.
        """
        if not tournament_name or not isinstance(tournament_name, str):
            return ""

        clean_name = tournament_name.strip()
        logger.info("EmblemScout: Starting official emblem search for '%s'", clean_name)

        # 0. Canonical Emblem Map Fast-Path Override
        name_lower = clean_name.lower()
        for key, canonical_url in cls.CANONICAL_EMBLEM_MAP.items():
            if key in name_lower:
                logger.info("EmblemScout: Found canonical emblem override for '%s': %s", clean_name, canonical_url)
                return canonical_url

        # 1. Wikidata P154 (Official Emblem) & Parent Entity Fallback
        logo_url = cls._fetch_from_wikidata(clean_name, wikidata_qid)
        if logo_url and is_valid_tournament_logo(logo_url):
            logger.info("EmblemScout: Resolved emblem from Wikidata: %s", logo_url)
            return logo_url

        # 2. Wikimedia Commons Direct Search API
        logo_url = cls._fetch_from_wikimedia_commons(clean_name)
        if logo_url and is_valid_tournament_logo(logo_url):
            logger.info("EmblemScout: Resolved emblem from Wikimedia Commons: %s", logo_url)
            return logo_url

        # 3. Wikipedia PageImages API
        logo_url = cls._fetch_from_wikipedia_pageimages(clean_name)
        if logo_url and is_valid_tournament_logo(logo_url):
            logger.info("EmblemScout: Resolved emblem from Wikipedia PageImages: %s", logo_url)
            return logo_url

        # 4. Official Governing Body Webpage Meta & HTML Logo Tags
        if official_url:
            logo_url = cls._fetch_from_official_webpage(official_url)
            if logo_url and is_valid_tournament_logo(logo_url):
                logger.info("EmblemScout: Resolved emblem from Official Webpage: %s", logo_url)
                return logo_url

        # 5. Gemini AI Search Fallback
        logo_url = cls._fetch_from_gemini_ai(clean_name, official_url)
        if logo_url and is_valid_tournament_logo(logo_url):
            logger.info("EmblemScout: Resolved emblem via Gemini AI Search: %s", logo_url)
            return logo_url

        # 6. Fallback: Strip season year prefixes (e.g. "2026–27 UEFA Nations League" -> "UEFA Nations League") and retry
        parent_name = re.sub(r'^\d{4}(?:[–\-]\d{2,4})?\s*', '', clean_name).strip()
        if parent_name and parent_name != clean_name:
            logger.info("EmblemScout: Retrying search with parent tournament name '%s'", parent_name)
            parent_logo = cls.discover_official_emblem(parent_name, official_url, wikidata_qid)
            if parent_logo:
                return parent_logo

        logger.warning("EmblemScout: No valid emblem logo found for '%s'", clean_name)
        return ""

    @classmethod
    def _fetch_from_wikidata(cls, page_title: str, wikidata_qid: Optional[str] = None) -> Optional[str]:
        from tournament.services.wikidata_scout import WikidataScout
        try:
            res = WikidataScout.fetch_wikidata_entity(page_title)
            if logo := res.get('logo_url'):
                return logo
        except Exception as exc:
            logger.warning("EmblemScout Wikidata error: %s", exc)
        return None

    @classmethod
    def _fetch_from_wikimedia_commons(cls, tournament_name: str) -> Optional[str]:
        clean_base = re.sub(r'\s*\b(qualifying|qualification|qualifiers)\b.*', '', tournament_name, flags=re.I).strip()
        queries = [
            f"{clean_base} emblem",
            f"{clean_base} logo",
            f"{tournament_name} emblem",
            f"{tournament_name} logo"
        ]

        for query in queries:
            api_url = f"https://commons.wikimedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&srnamespace=6&format=json"
            try:
                res = requests.get(api_url, headers=cls.HEADERS, timeout=6)
                if res.status_code != 200:
                    continue
                data = res.json()
                results = data.get('query', {}).get('search', [])
                
                def ext_score(title: str) -> int:
                    t = title.lower()
                    if t.endswith('.svg'): return 4
                    if t.endswith('.png'): return 3
                    if t.endswith('.webp'): return 2
                    return 1

                results = sorted(results, key=lambda x: ext_score(x.get('title', '')), reverse=True)

                for item in results:
                    title = item.get('title', '')
                    title_lower = title.lower()
                    if is_valid_tournament_logo(title) and any(title_lower.endswith(ext) for ext in ['.svg', '.png', '.jpg', '.webp']):
                        if any(k in title_lower for k in ['logo', 'emblem', 'insignia', 'crest', 'badge', 'patch']):
                            file_name = title.replace('File:', '').strip()
                            return f"https://commons.wikimedia.org/wiki/Special:FilePath/{urllib.parse.quote(file_name)}"
            except Exception as exc:
                logger.warning("EmblemScout Commons search error for query '%s': %s", query, exc)
        return None

    @classmethod
    def _fetch_from_wikipedia_pageimages(cls, page_title: str) -> Optional[str]:
        titles_to_try = [page_title]
        clean_base = re.sub(r'\s*\b(qualifying|qualification|qualifiers)\b.*', '', page_title, flags=re.I).strip()
        if clean_base and clean_base != page_title:
            titles_to_try.append(clean_base)

        for title in titles_to_try:
            api_url = f"https://en.wikipedia.org/w/api.php?action=query&titles={urllib.parse.quote(title)}&prop=pageimages&piprop=original&format=json"
            try:
                res = requests.get(api_url, headers=cls.HEADERS, timeout=6)
                if res.status_code == 200:
                    data = res.json()
                    pages = data.get('query', {}).get('pages', {})
                    for _, p_data in pages.items():
                        src = p_data.get('original', {}).get('source')
                        if src and is_valid_tournament_logo(src):
                            src_lower = src.lower()
                            if any(k in src_lower for k in ['logo', 'emblem', 'crest', 'badge', 'insignia']) or not any(k in src_lower for k in ['trophy', 'stadium', 'map', 'flag']):
                                return src
            except Exception as exc:
                logger.warning("EmblemScout PageImages error for '%s': %s", title, exc)
        return None

    @classmethod
    def _fetch_from_official_webpage(cls, official_url: str) -> Optional[str]:
        if not official_url or not isinstance(official_url, str):
            return None
        try:
            res = requests.get(official_url, headers=cls.HEADERS, timeout=8, verify=False)
            if res.status_code != 200:
                return None
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(res.content, 'html.parser')

            # 1. Search meta tags (og:image / twitter:image)
            candidates = []
            for meta in soup.find_all('meta'):
                prop = meta.get('property', '') or meta.get('name', '')
                if re.search(r'og:image|twitter:image', prop, re.I) and meta.get('content'):
                    candidates.append(meta['content'])

            # 2. Search img elements with logo/emblem/brand in alt/class/src
            for img in soup.find_all('img'):
                src = img.get('src', '') or img.get('data-src', '')
                alt = img.get('alt', '')
                cls_str = ' '.join(img.get('class', [])) if isinstance(img.get('class'), list) else str(img.get('class', ''))
                combined = f"{src} {alt} {cls_str}".lower()

                if any(k in combined for k in ['emblem', 'event-logo', 'tournament-logo', 'competition-logo', 'header-logo']):
                    candidates.append(src)
                elif 'logo' in combined and not any(k in combined for k in ['sponsor', 'partner', 'federation-logo']):
                    candidates.append(src)

            for cand in candidates:
                full_url = urllib.parse.urljoin(official_url, cand)
                if is_valid_tournament_logo(full_url):
                    return full_url
        except Exception as exc:
            logger.warning("EmblemScout official webpage error for '%s': %s", official_url, exc)
        return None

    @classmethod
    def _fetch_from_gemini_ai(cls, tournament_name: str, official_url: Optional[str] = None) -> Optional[str]:
        """
        Uses Gemini LLM with Google Search Grounding to discover direct official tournament emblem URLs.
        """
        try:
            from tournament.services.gemini_scout_service import GeminiScoutService
            prompt = (
                "You are an expert sports graphic designer, brand auditor, and tournament scout.\n"
                f"Your task is to identify the official emblem / logotype image URL for '{tournament_name}'.\n"
                f"Official website context: {official_url or 'N/A'}\n\n"
                "Search Google for the official tournament emblem / logo / logotype.\n"
                "Step 1: Briefly describe the visual features of the official competition emblem (colors, shapes, icons, text).\n"
                "Step 2: Provide the direct Wikimedia Commons, official federation website, or search-grounded high-resolution image URL (SVG/PNG/WebP/JPG) matching this visual description.\n\n"
                "CRITICAL REQUIREMENTS:\n"
                "- The image MUST be an isolated logo/emblem version.\n"
                "- SVG format or transparent PNG is highly preferred.\n"
                "- Do NOT return generic geographical maps, standalone country flags, raw stadium photos, or generic banners.\n"
                "Return ONLY valid JSON:\n"
                "{\n"
                "  \"emblem_visual_description\": \"<description>\",\n"
                "  \"logo_url\": \"<direct_image_url>\"\n"
                "}"
            )
            audit = None
            if GeminiScoutService.is_available():
                audit = GeminiScoutService.generate_json(prompt, search_grounding=True)
            if not audit:
                from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
                llm_scout = LLMWikipediaScout()
                audit = llm_scout._call_gemini(prompt, custom_prompt=True)
            if audit and isinstance(audit, dict):
                logo = audit.get('logo_url')
                if logo and is_valid_tournament_logo(logo):
                    desc = audit.get('emblem_visual_description', '')
                    if desc:
                        logger.info("EmblemScout Gemini AI Visual Audit for '%s': %s", tournament_name, desc[:120])
                    return logo

        except Exception as exc:
            logger.warning("EmblemScout Gemini AI error for '%s': %s", tournament_name, exc)
        return None
