import logging
import re
import urllib.parse
import requests
from typing import Optional

logger = logging.getLogger(__name__)


class OfficialSiteScout:
    """
    Automated Finder Agent for Official Sports Federation Websites & Tournament Portals.
    Discovers authoritative URLs (UEFA, FIFA, CONCACAF, AFC, FIBA, IFF, IIHF, World Aquatics, etc.)
    using Wikipedia external links, Wikidata properties, and domain rules.
    """
    HEADERS = {
        'User-Agent': 'PredictionEngine-OfficialScout/1.0 (contact@predictionengine.app)'
    }

    FEDERATION_DOMAINS = [
        'uefa.com', 'fifa.com', 'concacaf.com', 'the-afc.com', 'asiancup2027.sa',
        'cafonline.com', 'fiba.basketball', 'iff.sport', 'iihf.com', 'worldaquatics.com',
        'ihf.info', 'world.rugby', 'icc-cricket.com', 'fivb.com', 'worldathletics.org'
    ]

    @classmethod
    def discover_official_site(cls, tournament_name: str, wikipedia_title: Optional[str] = None) -> Optional[str]:
        """
        Discovers the official tournament website URL for a given tournament.
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

        if title:
            # 1a. Check Wikidata property P856
            try:
                from tournament.services.wikidata_scout import WikidataScout
                w_data = WikidataScout.fetch_wikidata_entity(title)
                off_site = w_data.get('official_website_url')
                if off_site and isinstance(off_site, str) and off_site.startswith('http'):
                    return off_site
            except Exception as e:
                logger.warning("OfficialSiteScout: Wikidata P856 lookup error: %s", e)

            # 1b. Query Wikipedia external links (prop=extlinks)
            try:
                ext_url = 'https://en.wikipedia.org/w/api.php'
                params = {'action': 'query', 'prop': 'extlinks', 'titles': title, 'format': 'json', 'ellimit': 50}
                r = requests.get(ext_url, params=params, headers=cls.HEADERS, timeout=10)
                if r.status_code == 200:
                    pages = r.json().get('query', {}).get('pages', {})
                    ext_links = []
                    for pid, p in pages.items():
                        if 'extlinks' in p:
                            ext_links = [l['*'] for l in p['extlinks'] if isinstance(l, dict) and '*' in l]

                    # Filter for authoritative sports federation domains
                    matched = []
                    for link in ext_links:
                        l_lower = link.lower()
                        if any(d in l_lower for d in cls.FEDERATION_DOMAINS):
                            score = 10
                            # High score for primary competition hubs & landing pages
                            if re.search(r'/(nationsleague|nations-league|european-qualifiers|euro-?\d+|asian_cup|world-cup|competitions)/?$', l_lower):
                                score += 20
                            elif any(k in l_lower for k in ['schedule', 'regulations', 'format', 'standings', 'competition', 'qualifier']):
                                score += 5
                            if link.endswith('.pdf') or '/editorial/' in l_lower or '/resources/' in l_lower:
                                score -= 5
                            matched.append((score, link))
                        elif 'official' in l_lower or 'site' in l_lower:
                            matched.append((5, link))

                    if matched:
                        matched.sort(key=lambda x: x[0], reverse=True)
                        return matched[0][1]


                    # Fallback to first non-wikipedia link if present
                    for link in ext_links:
                        if 'wikipedia.org' not in link and 'wikimedia.org' not in link:
                            return link
            except Exception as exc:
                logger.warning("OfficialSiteScout: Wikipedia extlinks fetch error for '%s': %s", title, exc)

        return None
