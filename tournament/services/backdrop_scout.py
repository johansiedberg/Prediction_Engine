import logging
import re
import urllib.parse
import requests
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


def is_valid_tournament_backdrop(url: str, width: int = 0, height: int = 0) -> bool:
    """
    Validates whether a candidate image URL is an appropriate landscape tournament backdrop / key visual,
    rejecting portrait images, tiny icons, standalone country flags, and UI noise.
    """
    if not url or not isinstance(url, str):
        return False

    url_lower = url.lower().strip()
    if not url_lower.startswith(('http://', 'https://')):
        return False

    # Rejected noise keywords
    invalid_keywords = [
        'flag_of', 'flag%20of', 'flag%5fof', 'flag-', 'flag_', 'flag.', 'country-flag',
        'map_of', 'location_map', 'carte_de', 'map.svg', 'map.png', 'map.jpg',
        'avatar', 'user_icon', 'blank.png', 'spacer.gif', 'favicon', '1x1',
        'headshot', 'portrait', 'podium', 'presentation',
    ]

    for pattern in invalid_keywords:
        if pattern in url_lower:
            return False

    # Check dimensions if provided
    if width > 0 and height > 0:
        # Require landscape aspect ratio (width >= 1.2 * height) and minimum width of 400px
        if width < 380:
            return False
        if width < (height * 1.15):
            return False

    return True


class BackdropScout:
    """
    Authoritative Multi-Source Backdrop Discovery Agent for Sports Tournaments.
    Discovers landscape key visuals, promotional wallpapers, and hero banners
    optimized for desktop and responsive narrow screens.
    """

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    CANONICAL_BACKDROP_MAP = {
        'uefa euro 2028': 'https://editorial.uefa.com/resources/0297-1d6049863981-8025bce510cc-1000/euro_2028_final.jpeg',
        '2026 fifa world cup': 'https://digitalhub.fifa.com/transform/5c6ee387-9a80-4591-9e2e-1e9bf439775f/FWC26_Brand_Launch_Banner_Desktop',
        'fifa world cup 2026': 'https://digitalhub.fifa.com/transform/5c6ee387-9a80-4591-9e2e-1e9bf439775f/FWC26_Brand_Launch_Banner_Desktop',
        'fifa world cup': 'https://digitalhub.fifa.com/transform/5c6ee387-9a80-4591-9e2e-1e9bf439775f/FWC26_Brand_Launch_Banner_Desktop',
        '2027 fiba basketball world cup': 'https://dohanews.co/wp-content/uploads/2025/01/image-59-1160x511.png',
        'fiba basketball world cup 2027': 'https://dohanews.co/wp-content/uploads/2025/01/image-59-1160x511.png',
        '2026–27 uefa nations league': 'https://editorial.uefa.com/resources/0285-18ff3fae1f2f-4fcb802675d0-1000/unl_keyvisual_2024.jpeg',
        'uefa nations league': 'https://editorial.uefa.com/resources/0285-18ff3fae1f2f-4fcb802675d0-1000/unl_keyvisual_2024.jpeg',
        '2027 afc asian cup': 'https://assets.the-afc.com/Competitions/Asian-Cup/2027/saudi2027-banner.jpg',
        'afc asian cup': 'https://assets.the-afc.com/Competitions/Asian-Cup/2027/saudi2027-banner.jpg',
        'concacaf gold cup': 'https://res.cloudinary.com/concacaf-production/image/upload/v1617812543/Gold_Cup_Header.jpg',
        '2027 africa cup of nations': 'https://images.cafonline.com/image/upload/caf-prd/caf_afcon2027_hero_banner.jpg',
    }

    @classmethod
    def discover_backdrop(cls, tournament_name: str, official_url: Optional[str] = None, sport: Optional[str] = None) -> str:
        """
        Discovers the optimal tournament backdrop / hero wallpaper image URL.
        Returns the resolved image URL string or empty string if not found.
        """
        if not tournament_name or not isinstance(tournament_name, str):
            return ""

        clean_name = tournament_name.strip()
        brand_name = re.sub(r'\b(19\d{2}|20\d{2}(?:[–\-]\d{2,4})?)\b', '', clean_name).strip()
        logger.info("BackdropScout: Searching backdrop for '%s' (Brand: '%s')", clean_name, brand_name)

        # 0. Canonical Map Fast-Path
        name_lower = clean_name.lower()
        brand_lower = brand_name.lower()
        for key, canonical_url in cls.CANONICAL_BACKDROP_MAP.items():
            if key in name_lower or (brand_lower and key in brand_lower):
                logger.info("BackdropScout: Found canonical backdrop override for '%s': %s", clean_name, canonical_url)
                return canonical_url

        # 1. Official Webpage Open-Graph & Hero Banner Extraction
        if official_url:
            backdrop = cls._fetch_from_official_webpage(official_url)
            if backdrop and is_valid_tournament_backdrop(backdrop):
                logger.info("BackdropScout: Resolved backdrop from Official Webpage: %s", backdrop)
                return backdrop

        # 2. Web Image Search (Google / DuckDuckGo)
        backdrop = cls._fetch_from_web_search(clean_name, brand_name)
        if backdrop and is_valid_tournament_backdrop(backdrop):
            logger.info("BackdropScout: Resolved backdrop from Web Image Search: %s", backdrop)
            return backdrop

        # 3. Gemini AI Search Grounding Fallback
        backdrop = cls._fetch_from_gemini_ai(clean_name, official_url=official_url)
        if backdrop and is_valid_tournament_backdrop(backdrop):
            logger.info("BackdropScout: Resolved backdrop via Gemini AI: %s", backdrop)
            return backdrop

        logger.info("BackdropScout: No custom backdrop found for '%s'", clean_name)
        return ""

    @classmethod
    def _fetch_from_official_webpage(cls, official_url: str) -> Optional[str]:
        """
        Extracts high-resolution OpenGraph or Twitter header image from the official site.
        """
        try:
            res = requests.get(official_url, headers=cls.HEADERS, timeout=8, verify=True)
            if res.status_code != 200:
                return None

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(res.content, 'html.parser')

            candidates = []
            for meta in soup.find_all('meta'):
                prop = meta.get('property', '') or meta.get('name', '')
                if re.search(r'og:image|twitter:image|twitter:image:src', prop, re.I) and meta.get('content'):
                    cand = meta['content']
                    cand_lower = cand.lower()
                    if not any(k in cand_lower for k in ['logo', 'icon', 'favicon', 'avatar', 'thumb']):
                        candidates.append(cand)

            # Also search for hero / banner background <img>
            for img in soup.find_all('img'):
                src = img.get('src', '') or img.get('data-src', '')
                alt = img.get('alt', '')
                cls_str = ' '.join(img.get('class', [])) if isinstance(img.get('class'), list) else str(img.get('class', ''))
                combined = f"{src} {alt} {cls_str}".lower()

                if any(k in combined for k in ['hero', 'banner', 'backdrop', 'key-visual', 'header-bg', 'masthead']):
                    if not any(k in combined for k in ['logo', 'icon', 'sponsor', 'partner']):
                        candidates.append(src)

            for cand in candidates:
                full_url = urllib.parse.urljoin(official_url, cand)
                if is_valid_tournament_backdrop(full_url):
                    return full_url

        except Exception as exc:
            logger.debug("BackdropScout official webpage warning for '%s': %s", official_url, exc)
        return None

    @classmethod
    def _fetch_from_web_search(cls, clean_name: str, brand_name: str) -> Optional[str]:
        """
        Executes search queries targeting tournament backdrops, banners, and wallpapers.
        """
        queries = [
            f"{clean_name} backdrop",
            f"{clean_name} key visual banner",
            f"{clean_name} tournament banner wallpaper",
            f"{brand_name} backdrop" if brand_name else "",
        ]

        for query in queries:
            if not query:
                continue
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
                            w = r.get('width', 0)
                            h = r.get('height', 0)
                            if cand_url and is_valid_tournament_backdrop(cand_url, width=w, height=h):
                                return cand_url
            except Exception as exc:
                logger.debug("BackdropScout web search warning for query '%s': %s", query, exc)
        return None

    @classmethod
    def _fetch_from_gemini_ai(cls, tournament_name: str, official_url: Optional[str] = None) -> Optional[str]:
        """
        Uses Gemini LLM with Google Search Grounding to identify the official tournament backdrop / key visual wallpaper.
        """
        try:
            from tournament.services.gemini_scout_service import GeminiScoutService
            prompt = (
                "You are an expert sports media designer and tournament visual auditor.\n"
                f"Your task is to identify the official landscape backdrop, hero banner, or key visual wallpaper URL for '{tournament_name}'.\n"
                f"Official website context: {official_url or 'N/A'}\n\n"
                "Search Google for the official tournament backdrop, key visual, or promotional widescreen banner image.\n"
                "REQUIREMENTS:\n"
                "- Must be a wide/landscape image suitable for a header background across desktop and mobile screens.\n"
                "- Return the direct high-resolution image URL (JPG, PNG, WebP).\n"
                "Return ONLY valid JSON:\n"
                "{\n"
                "  \"backdrop_url\": \"<direct_image_url>\",\n"
                "  \"visual_description\": \"<brief description>\"\n"
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
                backdrop = audit.get('backdrop_url')
                if backdrop and is_valid_tournament_backdrop(backdrop):
                    return backdrop
        except Exception as exc:
            logger.debug("BackdropScout Gemini AI warning for '%s': %s", tournament_name, exc)
        return None
