import logging
import re
import urllib.parse
import requests
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Noise keywords in filenames, paths, or alt text to strictly reject irrelevant/campaign/ad banners
INVALID_KEYWORDS = [
    # Vector / map / badge artifacts
    'flag_of', 'flag%20of', 'flag%5fof', 'flag-', 'flag_', 'flag.', 'country-flag',
    'map_of', 'location_map', 'carte_de', 'map.svg', 'map.png', 'map.jpg',
    'avatar', 'user_icon', 'blank.png', 'spacer.gif', 'favicon', '1x1',
    'headshot', 'portrait', 'podium', 'presentation',
    # Irrelevant campaign / site management / administrative banners
    'competition-manipulation', 'match-fixing', 'integrity', 'safeguarding',
    'anti-doping', 'wada', 'clean-sport', 'anti_doping',
    'academy', 'course', 'elearning', 'e-learning', 'education', 'webinar', 'workshop', 'tutorial',
    'cookie', 'privacy', 'consent', 'gdpr', 'terms', 'policy',
    'sponsor', 'partner', 'advertisement', 'ad-banner', 'commercial', 'subscribe', 'newsletter',
    'ticket', 'tickets', 'booking', 'hospitality',
    'rulebook', 'constitution', 'governance', 'annual-report',
]

# Domains known for hotlink-protection, ephemeral session tokens, or 403 Forbidden responses
INVALID_DOMAINS = [
    'stayhappening.com', 'allevents.in', 'ticketmaster.com', 'eventbrite.com',
    'lookaside.fbsbx.com', 'facebook.com', 'instagram.com', 'pinterest.com',
    'twitter.com', 'x.com',
]


def verify_live_image_url(url: str, min_bytes: int = 8000, timeout: float = 3.5) -> bool:
    """
    Actively checks that candidate image URL is live (HTTP 200/206), returns an actual image
    content-type (JPEG, PNG, WebP, AVIF), and meets a minimum byte threshold.
    """
    if not url or not isinstance(url, str):
        return False
    if not url.lower().startswith(('http://', 'https://')):
        return False
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Range': 'bytes=0-32767',
        }
        res = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True, stream=True)
        if res.status_code not in (200, 206):
            return False

        ct = res.headers.get('Content-Type', '').lower()
        if not (ct.startswith('image/') or 'jpeg' in ct or 'png' in ct or 'webp' in ct or 'avif' in ct):
            return False
        # Reject svg or html masquerading as image for backdrops
        if 'svg' in ct or 'html' in ct or 'xml' in ct or 'json' in ct:
            return False

        # Verify initial chunk size / content length
        chunk = next(res.iter_content(chunk_size=16384), b'')
        content_len_header = int(res.headers.get('Content-Length', 0) or 0)
        if len(chunk) < min_bytes and (content_len_header > 0 and content_len_header < min_bytes):
            return False

        return True
    except Exception as e:
        logger.debug("Backdrop live check failed for '%s': %s", url, e)
        return False


def is_valid_tournament_backdrop(url: str, width: int = 0, height: int = 0, verify_live: bool = False) -> bool:
    """
    Validates whether a candidate image URL is an appropriate landscape tournament backdrop / key visual,
    rejecting portrait images, tiny icons, standalone country flags, campaign noise, and unreachable URLs.
    """
    if not url or not isinstance(url, str):
        return False

    url_lower = url.lower().strip()
    if not url_lower.startswith(('http://', 'https://')):
        return False

    # Reject vector SVG and animated GIF banners for photographic widescreen backdrops
    if any(bad in url_lower for bad in ['.svg', '.gif', 'animated', 'animation', '.apng', '.mp4', '.webm']):
        return False

    # Reject blacklisted domains
    for d in INVALID_DOMAINS:
        if d in url_lower:
            return False

    # Reject noise keywords
    for pattern in INVALID_KEYWORDS:
        if pattern in url_lower:
            return False

    # Check dimensions if provided
    if width > 0 and height > 0:
        # Require landscape aspect ratio (width >= 1.15 * height) and minimum width of 380px
        if width < 380:
            return False
        if width < (height * 1.15):
            return False

    if verify_live:
        return verify_live_image_url(url)

    return True


class BackdropScout:
    """
    Authoritative Multi-Source Backdrop Discovery Agent for Sports Tournaments.
    Discovers landscape key visuals, promotional wallpapers, and hero banners
    optimized for desktop and responsive screens with active reachability verification.
    """

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    # Verified 100% live, high-resolution tournament backdrops
    CANONICAL_BACKDROP_MAP = {
        'uefa euro 2028': 'https://editorial.uefa.com/resources/0297-1d6049863981-8025bce510cc-1000/euro_2028_final.jpeg',
        '2026 fifa world cup': 'https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/MetLife_Stadium_2022.jpg/1280px-MetLife_Stadium_2022.jpg',
        'fifa world cup 2026': 'https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/MetLife_Stadium_2022.jpg/1280px-MetLife_Stadium_2022.jpg',
        'fifa world cup': 'https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/MetLife_Stadium_2022.jpg/1280px-MetLife_Stadium_2022.jpg',
        '2026–27 uefa nations league': 'https://editorial.uefa.com/resources/0253-0d7af33f8f19-fee27dba0414-1000/uefa_nations_league.jpeg',
        'uefa nations league': 'https://editorial.uefa.com/resources/0253-0d7af33f8f19-fee27dba0414-1000/uefa_nations_league.jpeg',
        '2026 men\'s world floorball championships': 'https://freeoflimits.fi/wp-content/uploads/2026/01/54206222740_61559c38a6_k-2.jpg',
        '2027 world men\'s handball championship': 'https://www.lanxess-arena.de/fileadmin/user_upload/Events_und_Tickets/Events/2027/Men__s_IHF_World_Championship_2027/Artwork_Mens__s_IHF_World_Championship_1110x431.jpg',
        '2027 afc asian cup': 'https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEgkWwCDkdys0RjJOLiqJfoNVOeK6r86qZwiZ3506E8_xUQJQJkwwh_yhyphenhyphenMuzLzE7yK4C9caz8pTxH9_sIzZ_B92YzIoJOSqa1mRpNCUbLRGaCsb86EA2NDimDkJ4U6L5zvnzbV85TtPm5ARcq3F0tCHhee7PYWPFYncuklzbn6ByeYHZ4T42pLSAn-S6qOH/s1000/afc-asian-cup-2027-logo%20(3).jpg',
        '2027 africa cup of nations': 'https://www.arunfoot.com/wp-content/uploads/2023/09/2027-Africa-Cup-of-Nations-Tanzania-Uganda-Kenya.jpg',
        '2026 u-23 baseball world cup': 'https://gobaseball.gogoal.com.tw/wp-content/uploads/2024/09/739f1d54-ea47-5bc4-5939-32de2f7184f3-1170x705.jpg',
        '2027 fiba basketball world cup': 'https://dohanews.co/wp-content/uploads/2025/01/image-59-1160x511.png',
        'fiba basketball world cup 2027': 'https://dohanews.co/wp-content/uploads/2025/01/image-59-1160x511.png',
        '2026 european women\'s handball championship': 'https://ehfeuro.eurohandball.com/media/ehta0mwb/weuro26_metaimage_1200.png',
        '2027 world junior ice hockey championships': 'https://cdn.hockeycanada.ca/hockey-canada/Team-Canada/Men/Junior/2027/2027-wjc-hosts-announced.jpg',
        '2027 cricket world cup': 'https://www.icccricketschedule.com/_image/?href=https:%2F%2Fimagedelivery.net%2FOWGbUSC-tY-l6l4K6Rsqpg%2F7040db05-e85f-4bc7-85b9-31668962db00%2Fpublic&w=1200&h=675&q=75&f=webp',
        '2027 netball world cup': 'https://www.bandt.com.au/information/uploads/2025/09/NWC_Brand_Web_900x600_2.jpg.webp',
    }

    # Curated, verified, high-availability landscape sport backdrops (used as thematic fallbacks)
    SPORT_THEMED_BACKDROPS = {
        'football': 'https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/MetLife_Stadium_2022.jpg/1280px-MetLife_Stadium_2022.jpg',
        'soccer': 'https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/MetLife_Stadium_2022.jpg/1280px-MetLife_Stadium_2022.jpg',
        'fotboll': 'https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/MetLife_Stadium_2022.jpg/1280px-MetLife_Stadium_2022.jpg',
        'ice hockey': 'https://images.unsplash.com/photo-1580748141549-71748dbe0bdc?auto=format&fit=crop&w=1600&q=80',
        'hockey': 'https://images.unsplash.com/photo-1580748141549-71748dbe0bdc?auto=format&fit=crop&w=1600&q=80',
        'ishockey': 'https://images.unsplash.com/photo-1580748141549-71748dbe0bdc?auto=format&fit=crop&w=1600&q=80',
        'floorball': 'https://images.unsplash.com/photo-1587280501635-68a0e82cd5ff?auto=format&fit=crop&w=1600&q=80',
        'innebandy': 'https://images.unsplash.com/photo-1587280501635-68a0e82cd5ff?auto=format&fit=crop&w=1600&q=80',
        'basketball': 'https://images.unsplash.com/photo-1546519638-68e109498ffc?auto=format&fit=crop&w=1600&q=80',
        'basket': 'https://images.unsplash.com/photo-1546519638-68e109498ffc?auto=format&fit=crop&w=1600&q=80',
        'handball': 'https://images.unsplash.com/photo-1518091043644-c1d4457512c6?auto=format&fit=crop&w=1600&q=80',
        'handboll': 'https://images.unsplash.com/photo-1518091043644-c1d4457512c6?auto=format&fit=crop&w=1600&q=80',
        'baseball': 'https://images.unsplash.com/photo-1508344928928-7165b67de128?auto=format&fit=crop&w=1600&q=80',
        'baseboll': 'https://images.unsplash.com/photo-1508344928928-7165b67de128?auto=format&fit=crop&w=1600&q=80',
        'volleyball': 'https://images.unsplash.com/photo-1612872087720-bb876e2e67d1?auto=format&fit=crop&w=1600&q=80',
        'volleyboll': 'https://images.unsplash.com/photo-1612872087720-bb876e2e67d1?auto=format&fit=crop&w=1600&q=80',
        'cricket': 'https://images.unsplash.com/photo-1531415074968-036ba1b575da?auto=format&fit=crop&w=1600&q=80',
        'rugby': 'https://images.unsplash.com/photo-1574629810360-7efbbe195018?auto=format&fit=crop&w=1600&q=80',
        'american football': 'https://images.unsplash.com/photo-1574629810360-7efbbe195018?auto=format&fit=crop&w=1600&q=80',
        'default': 'https://images.unsplash.com/photo-1522778119026-d647f0596c20?auto=format&fit=crop&w=1600&q=80',
    }

    @classmethod
    def get_sport_fallback(cls, sport: Optional[str] = None) -> str:
        """
        Returns a verified high-resolution thematic sport backdrop.
        """
        if sport:
            sport_key = str(sport).strip().lower()
            for k, url in cls.SPORT_THEMED_BACKDROPS.items():
                if k in sport_key:
                    return url
        return cls.SPORT_THEMED_BACKDROPS['default']

    @classmethod
    def discover_backdrop(
        cls,
        tournament_name: str,
        official_url: Optional[str] = None,
        sport: Optional[str] = None,
        fallback_to_sport: bool = True
    ) -> str:
        """
        Discovers the optimal tournament backdrop / hero wallpaper image URL with live reachability verification.
        Returns the resolved image URL string or sport fallback.
        """
        if not tournament_name or not isinstance(tournament_name, str):
            return cls.get_sport_fallback(sport) if fallback_to_sport else ""

        clean_name = tournament_name.strip()
        brand_name = re.sub(r'\b(19\d{2}|20\d{2}(?:[–\-]\d{2,4})?)\b', '', clean_name).strip()
        logger.info("BackdropScout: Searching backdrop for '%s' (Sport: '%s')", clean_name, sport)

        # 0. Canonical Map Fast-Path (with live reachability check)
        name_lower = clean_name.lower()
        brand_lower = brand_name.lower()
        for key, canonical_url in cls.CANONICAL_BACKDROP_MAP.items():
            if key in name_lower or (brand_lower and key in brand_lower):
                if is_valid_tournament_backdrop(canonical_url, verify_live=True):
                    logger.info("BackdropScout: Resolved canonical backdrop for '%s': %s", clean_name, canonical_url)
                    return canonical_url

        # 1. Official Webpage Open-Graph & Hero Banner Extraction
        if official_url:
            backdrop = cls._fetch_from_official_webpage(official_url)
            if backdrop and is_valid_tournament_backdrop(backdrop, verify_live=True):
                logger.info("BackdropScout: Resolved backdrop from Official Webpage: %s", backdrop)
                return backdrop

        # 2. Wikimedia Commons Tournament / Stadium Imagery
        backdrop = cls._fetch_from_wikimedia_commons(clean_name, sport)
        if backdrop and is_valid_tournament_backdrop(backdrop, verify_live=True):
            logger.info("BackdropScout: Resolved backdrop from Wikimedia Commons: %s", backdrop)
            return backdrop

        # 3. Web Image Search (DuckDuckGo) with Live Reachability Filter
        backdrop = cls._fetch_from_web_search(clean_name, brand_name, sport)
        if backdrop and is_valid_tournament_backdrop(backdrop, verify_live=True):
            logger.info("BackdropScout: Resolved backdrop from Web Image Search: %s", backdrop)
            return backdrop

        # 4. Gemini AI Search Grounding Fallback
        backdrop = cls._fetch_from_gemini_ai(clean_name, official_url=official_url, sport=sport)
        if backdrop and is_valid_tournament_backdrop(backdrop, verify_live=True):
            logger.info("BackdropScout: Resolved backdrop via Gemini AI: %s", backdrop)
            return backdrop

        if fallback_to_sport:
            sport_fallback = cls.get_sport_fallback(sport)
            logger.info("BackdropScout: Using sport fallback backdrop for '%s' (%s): %s", clean_name, sport, sport_fallback)
            return sport_fallback

        return ""

    @classmethod
    def _fetch_from_wikimedia_commons(cls, tournament_name: str, sport: Optional[str] = None) -> Optional[str]:
        """
        Searches Wikimedia Commons for genuine tournament photographs, stadium visuals, or official key visuals.
        """
        try:
            queries = [
                f"{tournament_name} stadium",
                f"{tournament_name} arena",
                f"{tournament_name} match",
                tournament_name,
            ]
            for query in queries:
                api_url = f"https://commons.wikimedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&srnamespace=6&srlimit=5&format=json"
                res = requests.get(api_url, headers=cls.HEADERS, timeout=4)
                if res.status_code != 200:
                    continue

                data = res.json()
                search_results = data.get('query', {}).get('search', [])
                for item in search_results:
                    title = item.get('title', '')
                    title_lower = title.lower()
                    if any(k in title_lower for k in INVALID_KEYWORDS):
                        continue
                    if not any(ext in title_lower for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                        continue

                    # Fetch imageinfo for dimensions and direct URL
                    info_url = f"https://commons.wikimedia.org/w/api.php?action=query&titles={urllib.parse.quote(title)}&prop=imageinfo&iiprop=url|size|mime&format=json"
                    info_res = requests.get(info_url, headers=cls.HEADERS, timeout=4)
                    if info_res.status_code == 200:
                        pages = info_res.json().get('query', {}).get('pages', {})
                        for pid, p in pages.items():
                            imageinfo = p.get('imageinfo', [{}])[0]
                            img_url = imageinfo.get('url')
                            w = imageinfo.get('width', 0)
                            h = imageinfo.get('height', 0)
                            if img_url and is_valid_tournament_backdrop(img_url, width=w, height=h, verify_live=True):
                                return img_url
        except Exception as exc:
            logger.debug("BackdropScout Wikimedia Commons search error for '%s': %s", tournament_name, exc)
        return None

    @classmethod
    def _fetch_from_official_webpage(cls, official_url: str) -> Optional[str]:
        """
        Extracts high-resolution OpenGraph or Twitter header image from the official tournament site.
        """
        try:
            res = requests.get(official_url, headers=cls.HEADERS, timeout=6, verify=True)
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
                    if not any(k in cand_lower for k in ['logo', 'icon', 'favicon', 'avatar', 'thumb'] + INVALID_KEYWORDS):
                        candidates.append(cand)

            for img in soup.find_all('img'):
                src = img.get('src', '') or img.get('data-src', '')
                alt = img.get('alt', '')
                cls_str = ' '.join(img.get('class', [])) if isinstance(img.get('class'), list) else str(img.get('class', ''))
                combined = f"{src} {alt} {cls_str}".lower()

                if any(k in combined for k in ['hero', 'backdrop', 'key-visual', 'header-bg', 'masthead', 'wallpaper']):
                    if not any(k in combined for k in ['logo', 'icon', 'sponsor', 'partner'] + INVALID_KEYWORDS):
                        candidates.append(src)

            for cand in candidates:
                full_url = urllib.parse.urljoin(official_url, cand)
                if is_valid_tournament_backdrop(full_url, verify_live=True):
                    return full_url

        except Exception as exc:
            logger.debug("BackdropScout official webpage warning for '%s': %s", official_url, exc)
        return None

    @classmethod
    def _fetch_from_web_search(cls, clean_name: str, brand_name: str, sport: Optional[str] = None) -> Optional[str]:
        """
        Executes search queries targeting tournament backdrops, key visuals, and stadium wallpapers.
        Prioritizes '[Tournament name] backdrop' queries and supports high-availability cached thumbnails.
        """
        queries = [
            f"{clean_name} backdrop",
            f"{brand_name} backdrop" if brand_name else "",
            f"{clean_name} key visual",
            f"{clean_name} wallpaper",
            f"{clean_name} tournament stadium",
        ]

        for query in queries:
            if not query:
                continue
            try:
                vqd_res = requests.get(
                    f"https://duckduckgo.com/?q={urllib.parse.quote(query)}&t=h_&iax=images&ia=images",
                    headers=cls.HEADERS,
                    timeout=5,
                )
                if not vqd_res or not hasattr(vqd_res, 'text') or not isinstance(vqd_res.text, str):
                    continue
                vqd = re.search(r'vqd=([\d\-]+)', vqd_res.text) or re.search(r'vqd=\"([^\"]+)\"', vqd_res.text)
                if vqd:
                    vqd_val = vqd.group(1)
                    api_url = f"https://duckduckgo.com/i.js?l=us-en&o=json&q={urllib.parse.quote(query)}&vqd={vqd_val}&f=,,,"
                    res = requests.get(api_url, headers=cls.HEADERS, timeout=5)
                    if res.status_code == 200:
                        data = res.json()
                        for r in data.get('results', [])[:12]:
                            cand_url = r.get('image')
                            thumb_url = r.get('thumbnail')
                            w = r.get('width', 0)
                            h = r.get('height', 0)
                            
                            # 1. Try full resolution image URL with live reachability check
                            if cand_url and is_valid_tournament_backdrop(cand_url, width=w, height=h, verify_live=True):
                                return cand_url
                                
                            # 2. Try high-reliability static cached thumbnail URL with live reachability check
                            if thumb_url and is_valid_tournament_backdrop(thumb_url, verify_live=True):
                                return thumb_url
            except Exception as exc:
                logger.debug("BackdropScout web search warning for query '%s': %s", query, exc)
        return None

    @classmethod
    def _fetch_from_gemini_ai(cls, tournament_name: str, official_url: Optional[str] = None, sport: Optional[str] = None) -> Optional[str]:
        """
        Uses Gemini LLM with Google Search Grounding to identify the official tournament backdrop / key visual wallpaper.
        """
        try:
            from tournament.services.gemini_scout_service import GeminiScoutService
            prompt = (
                "You are an expert sports media designer and tournament visual auditor.\n"
                f"Your task is to identify the official landscape backdrop, hero banner, or key visual wallpaper URL for '{tournament_name}' ({sport or 'Sports'}).\n"
                f"Official website context: {official_url or 'N/A'}\n\n"
                "Search Google for the official tournament backdrop, key visual, or promotional widescreen banner image.\n"
                "REQUIREMENTS:\n"
                "- Must be a wide/landscape photographic or key visual image suitable for a header background.\n"
                "- Must NOT be an anti-doping, integrity, match-fixing, course, ticket, or general organization UI banner.\n"
                "- Return direct high-resolution image URL (JPG, PNG, WebP).\n"
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
                if backdrop and is_valid_tournament_backdrop(backdrop, verify_live=True):
                    return backdrop
        except Exception as exc:
            logger.debug("BackdropScout Gemini AI warning for '%s': %s", tournament_name, exc)
        return None

