import logging
import re
import urllib.parse
import requests
from typing import Optional, Dict, Any

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
        'crowd', 'spectators', 'team_photo', 'roster', '_ball.', '-ball.', '/ball.', 'match_ball', 'official_ball',
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
        'User-Agent': 'PredictionEngineBot/1.0 (https://predictionengine.app; contact@predictionengine.app)'
    }

    CANONICAL_EMBLEM_MAP = {
        'uefa nations league': 'https://upload.wikimedia.org/wikipedia/en/thumb/8/80/UEFA_Nations_League.svg/500px-UEFA_Nations_League.svg.png',
        'concacaf gold cup': 'https://upload.wikimedia.org/wikipedia/commons/thumb/b/b5/Concacaf_Gold_Cup_2021.svg/500px-Concacaf_Gold_Cup_2021.svg.png',
        'gold cup': 'https://upload.wikimedia.org/wikipedia/commons/thumb/b/b5/Concacaf_Gold_Cup_2021.svg/500px-Concacaf_Gold_Cup_2021.svg.png',
        'concacaf nations league': 'https://upload.wikimedia.org/wikipedia/commons/thumb/4/4b/Concacaf_Nations_League_logo.svg/500px-Concacaf_Nations_League_logo.svg.png',
        '2027 afc asian cup': 'https://upload.wikimedia.org/wikipedia/en/thumb/6/62/2027_AFC_Asian_Cup_logo.svg/500px-2027_AFC_Asian_Cup_logo.svg.png',
        'afc asian cup': 'https://upload.wikimedia.org/wikipedia/en/thumb/6/62/2027_AFC_Asian_Cup_logo.svg/500px-2027_AFC_Asian_Cup_logo.svg.png',
        'asian cup': 'https://upload.wikimedia.org/wikipedia/en/thumb/6/62/2027_AFC_Asian_Cup_logo.svg/500px-2027_AFC_Asian_Cup_logo.svg.png',
        'copa américa': 'https://upload.wikimedia.org/wikipedia/commons/thumb/b/b8/Copa_Am%C3%A9rica_logo.svg/500px-Copa_Am%C3%A9rica_logo.svg.png',
        'copa america': 'https://upload.wikimedia.org/wikipedia/commons/thumb/b/b8/Copa_Am%C3%A9rica_logo.svg/500px-Copa_Am%C3%A9rica_logo.svg.png',
        'africa cup of nations': 'https://upload.wikimedia.org/wikipedia/en/c/cf/Africa_Cup_of_Nation_official_logo.png',
        'afcon': 'https://upload.wikimedia.org/wikipedia/en/c/cf/Africa_Cup_of_Nation_official_logo.png',
        'uefa euro 2028': 'https://upload.wikimedia.org/wikipedia/en/thumb/1/1a/UEFA_Euro_2028_Logo.svg/500px-UEFA_Euro_2028_Logo.svg.png',
        '2026 fifa world cup': 'https://upload.wikimedia.org/wikipedia/commons/thumb/c/cb/2026_FIFA_World_Cup_emblem.svg/500px-2026_FIFA_World_Cup_emblem.svg.png',
        'fifa world cup 2026': 'https://upload.wikimedia.org/wikipedia/commons/thumb/c/cb/2026_FIFA_World_Cup_emblem.svg/500px-2026_FIFA_World_Cup_emblem.svg.png',
        'fifa world cup': 'https://upload.wikimedia.org/wikipedia/commons/thumb/c/cb/2026_FIFA_World_Cup_emblem.svg/500px-2026_FIFA_World_Cup_emblem.svg.png',
    }

    @classmethod
    def discover_emblem(cls, tournament_name: str, sport: Optional[str] = None, official_url: Optional[str] = None, wikidata_qid: Optional[str] = None) -> str:
        """Alias for discover_official_emblem."""
        return cls.discover_official_emblem(tournament_name=tournament_name, official_url=official_url, wikidata_qid=wikidata_qid)

    @classmethod
    def discover_official_emblem(cls, tournament_name: str, official_url: Optional[str] = None, wikidata_qid: Optional[str] = None) -> str:
        """
        Discovers the canonical official emblem logo URL for a given tournament name.
        Strips year/season terms to discover brand-level logos if season logos are absent.
        Returns the resolved image URL string or empty string if not found.
        """
        if not tournament_name or not isinstance(tournament_name, str):
            return ""

        clean_name = tournament_name.strip()
        brand_name = re.sub(r'\b(19\d{2}|20\d{2}(?:[–\-]\d{2,4})?)\b', '', clean_name).strip()
        logger.info("EmblemScout: Starting official emblem search for '%s' (Brand: '%s')", clean_name, brand_name)

        # 0. Canonical Emblem Map Fast-Path Override (Checks both exact name and stripped brand name)
        name_lower = clean_name.lower()
        brand_lower = brand_name.lower()
        for key, canonical_url in cls.CANONICAL_EMBLEM_MAP.items():
            if key in name_lower or (brand_lower and key in brand_lower):
                logger.info("EmblemScout: Found canonical emblem override for '%s': %s", clean_name, canonical_url)
                return canonical_url

        # 1. Wikipedia Article Parse & Infobox Images
        logo_url = cls._fetch_from_wikipedia_article_images(clean_name)
        if logo_url and is_valid_tournament_logo(logo_url):
            logger.info("EmblemScout: Resolved emblem from Wikipedia Article Images: %s", logo_url)
            return logo_url

        # 2. Web Search Engine Direct Image Mining (Google / Web Images)
        logo_url = cls._fetch_from_web_search_images(clean_name)
        if logo_url and is_valid_tournament_logo(logo_url):
            logger.info("EmblemScout: Resolved emblem from Web Search Images: %s", logo_url)
            return logo_url

        # 3. Wikidata P154 (Official Emblem) & Parent Entity Fallback
        logo_url = cls._fetch_from_wikidata(clean_name, wikidata_qid)
        if logo_url and is_valid_tournament_logo(logo_url):
            logger.info("EmblemScout: Resolved emblem from Wikidata: %s", logo_url)
            return logo_url

        # 4. Wikimedia Commons Direct Search API
        logo_url = cls._fetch_from_wikimedia_commons(clean_name)
        if logo_url and is_valid_tournament_logo(logo_url):
            logger.info("EmblemScout: Resolved emblem from Wikimedia Commons: %s", logo_url)
            return logo_url

        # 5. Wikipedia PageImages API
        logo_url = cls._fetch_from_wikipedia_pageimages(clean_name)
        if logo_url and is_valid_tournament_logo(logo_url):
            logger.info("EmblemScout: Resolved emblem from Wikipedia PageImages: %s", logo_url)
            return logo_url

        # 6. Official Governing Body Webpage Meta & HTML Logo Tags
        if official_url:
            logo_url = cls._fetch_from_official_webpage(official_url)
            if logo_url and is_valid_tournament_logo(logo_url):
                logger.info("EmblemScout: Resolved emblem from Official Webpage: %s", logo_url)
                return logo_url

        # 7. Gemini AI Search Fallback
        logo_url = cls._fetch_from_gemini_ai(clean_name, official_url)
        if logo_url and is_valid_tournament_logo(logo_url):
            logger.info("EmblemScout: Resolved emblem via Gemini AI Search: %s", logo_url)
            return logo_url

        # 8. Fallback: Strip season year prefixes and retry
        if brand_name and brand_name != clean_name:
            logger.info("EmblemScout: Retrying search with parent brand name '%s'", brand_name)
            parent_logo = cls.discover_official_emblem(brand_name, official_url, wikidata_qid)
            if parent_logo:
                return parent_logo

        logger.warning("EmblemScout: No valid emblem logo found for '%s'", clean_name)
        return ""

    @classmethod
    def _fetch_from_wikipedia_article_images(cls, page_title: str) -> Optional[str]:
        """
        Parses all image files linked in the Wikipedia article (including Infobox logo and fair-use logos)
        and resolves the high-res 500px rendered PNG thumbnail.
        """
        titles_to_try = [page_title]
        brand_name = re.sub(r'\b(19\d{2}|20\d{2}(?:[–\-]\d{2,4})?)\b', '', page_title).strip()
        if brand_name and brand_name not in titles_to_try:
            titles_to_try.append(brand_name)

        try:
            from tournament.services.wikipedia_scout import WikipediaScout
            wiki_search_title = WikipediaScout().search_wikipedia_article(page_title)
            if wiki_search_title and wiki_search_title not in titles_to_try:
                titles_to_try.append(wiki_search_title)
            if brand_name:
                brand_wiki_title = WikipediaScout().search_wikipedia_article(brand_name)
                if brand_wiki_title and brand_wiki_title not in titles_to_try:
                    titles_to_try.append(brand_wiki_title)
        except Exception:
            pass

        clean_base = re.sub(r'\s*\b(qualifying|qualification|qualifiers)\b.*', '', page_title, flags=re.I).strip()
        if clean_base and clean_base not in titles_to_try:
            titles_to_try.append(clean_base)

        # 1a. Fast Infobox Logo Parser on Wikipedia
        for title in titles_to_try:
            try:
                info_url = "https://en.wikipedia.org/w/api.php"
                params = {
                    "action": "query",
                    "titles": title,
                    "prop": "revisions",
                    "rvprop": "content",
                    "rvsection": "0",
                    "format": "json"
                }
                res = requests.get(info_url, params=params, headers=cls.HEADERS, timeout=6)
                if res.status_code == 200:
                    pages = res.json().get("query", {}).get("pages", {})
                    for _, p in pages.items():
                        for rev in p.get("revisions", []):
                            content = rev.get("*", "")
                            logo_match = re.search(r'\|\s*(?:logo|image|emblem|crest)\s*=\s*([^|\n}]+)', content, re.I)
                            if logo_match:
                                logo_file = logo_match.group(1).strip()
                                if not logo_file.lower().startswith("file:"):
                                    logo_file = f"File:{logo_file}"
                                img_res = requests.get("https://en.wikipedia.org/w/api.php", params={
                                    "action": "query",
                                    "titles": logo_file,
                                    "prop": "imageinfo",
                                    "iiprop": "url",
                                    "iiurlwidth": 500,
                                    "format": "json"
                                }, headers=cls.HEADERS, timeout=6)
                                if img_res.status_code == 200:
                                    for _, img_p in img_res.json().get("query", {}).get("pages", {}).items():
                                        for ii in img_p.get("imageinfo", []):
                                            thumb = ii.get("thumburl") or ii.get("url")
                                            if thumb and is_valid_tournament_logo(thumb):
                                                return thumb
            except Exception as exc:
                logger.debug("EmblemScout infobox parse warning for '%s': %s", title, exc)

        # 1b. Full page images fallback
        for title in titles_to_try:
            try:
                wiki_title = title.replace(' ', '_')
                parse_url = f"https://en.wikipedia.org/w/api.php?action=parse&page={urllib.parse.quote(wiki_title)}&prop=images&format=json"
                res = requests.get(parse_url, headers=cls.HEADERS, timeout=6)
                if res.status_code != 200:
                    continue
                data = res.json()
                images = data.get('parse', {}).get('images', [])

                logo_candidates = []
                for img_name in images:
                    img_lower = img_name.lower()
                    if not any(k in img_lower for k in ['map', 'flag', 'stadium', 'trophy', 'medal', 'youtube', 'icon', 'nuvola', 'avatar']) and any(img_lower.endswith(ext) for ext in ['.svg', '.png', '.jpg', '.webp']):
                        if any(k in img_lower for k in ['logo', 'emblem', 'crest', 'badge', 'insignia']) or (brand_name and brand_name.lower() in img_lower):
                            logo_candidates.append(img_name)

                for img_name in logo_candidates:
                    info_url = f"https://en.wikipedia.org/w/api.php?action=query&titles=File:{urllib.parse.quote(img_name)}&prop=imageinfo&iiprop=url&iiurlwidth=500&format=json"
                    i_res = requests.get(info_url, headers=cls.HEADERS, timeout=6)
                    if i_res.status_code == 200:
                        i_data = i_res.json()
                        pages = i_data.get('query', {}).get('pages', {})
                        for _, p in pages.items():
                            ii = p.get('imageinfo', [{}])[0]
                            thumb_url = ii.get('thumburl') or ii.get('url')
                            if thumb_url and is_valid_tournament_logo(thumb_url):
                                return thumb_url
            except Exception as exc:
                logger.warning("EmblemScout article images parse error for '%s': %s", title, exc)
        return None

    @classmethod
    def _fetch_from_web_search_images(cls, tournament_name: str) -> Optional[str]:
        """
        Performs web search image discovery for the tournament emblem/logo.
        """
        clean_base = re.sub(r'\s*\b(qualifying|qualification|qualifiers)\b.*', '', tournament_name, flags=re.I).strip()
        queries = [
            f"{clean_base} official emblem logo",
            f"{tournament_name} emblem logo",
            f"{clean_base} tournament logo",
        ]

        for query in queries:
            try:
                vqd_res = requests.get(
                    f"https://duckduckgo.com/?q={urllib.parse.quote(query)}&t=h_&iax=images&ia=images",
                    headers=cls.HEADERS,
                    timeout=6,
                )
                if not vqd_res or not hasattr(vqd_res, 'text') or not isinstance(vqd_res.text, str):
                    continue
                vqd = re.search(r'vqd=([\d\-]+)', vqd_res.text) or re.search(r'vqd=\"([^\"]+)\"', vqd_res.text)
                if vqd:
                    vqd_val = vqd.group(1)
                    api_url = f"https://duckduckgo.com/i.js?l=us-en&o=json&q={urllib.parse.quote(query)}&vqd={vqd_val}&f=,,,"
                    res = requests.get(api_url, headers=cls.HEADERS, timeout=6)
                    if res.status_code == 200:
                        data = res.json()
                        for r in data.get('results', [])[:10]:
                            cand_url = r.get('image') or r.get('thumbnail')
                            if cand_url and is_valid_tournament_logo(cand_url):
                                cand_lower = cand_url.lower()
                                if any(k in cand_lower for k in ['logo', 'emblem', 'crest', 'badge', 'brand', 'assets', 'upload', 'commons', 'gstatic', 'googleusercontent']):
                                    return cand_url
            except Exception as exc:
                logger.warning("EmblemScout web search images error for query '%s': %s", query, exc)
        return None

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
            try:
                res = requests.get(official_url, headers=cls.HEADERS, timeout=8, verify=True)
            except requests.exceptions.SSLError:
                logger.warning("EmblemScout: SSL error for %s, skipping.", official_url)
                return None
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
