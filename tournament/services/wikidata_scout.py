import logging
import requests
import urllib.parse
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class WikidataScout:
    """
    Scouts structured tournament entity data directly from Wikidata APIs.
    Provides canonical metadata:
    - Q-ID entity identifier
    - P580 (Start date) & P581 (End date)
    - P154 / P18 (Official emblem / image file URL via Wikimedia Commons)
    - P856 (Official tournament regulations website URL)
    - P17 / P276 (Host country / venue)
    """

    HEADERS = {
        'User-Agent': 'PredictionEngineScout/3.0 (admin@predictionengine.org)'
    }
    WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"

    @classmethod
    def get_wikidata_entity_id(cls, page_title: str) -> Optional[str]:
        """Resolves a Wikipedia page title to its Wikidata Q-ID."""
        if not page_title:
            return None
        try:
            params = {
                'action': 'query',
                'prop': 'pageprops',
                'ppprop': 'wikibase_item',
                'titles': page_title,
                'format': 'json'
            }
            res = requests.get(cls.WIKIPEDIA_API_URL, headers=cls.HEADERS, params=params, timeout=10)
            if res.status_code != 200:
                return None
            data = res.json()
            pages = data.get('query', {}).get('pages', {})
            for pid, page in pages.items():
                if pid == '-1':
                    continue
                q_id = page.get('pageprops', {}).get('wikibase_item')
                if q_id:
                    return q_id
        except Exception as exc:
            logger.warning("WikidataScout: Error resolving Q-ID for '%s': %s", page_title, exc)
        return None

    @classmethod
    def fetch_wikidata_entity(cls, page_title: str) -> Dict[str, Any]:
        """
        Fetches structured entity claims from Wikidata for a given Wikipedia title.
        Returns a dictionary with extracted attributes.
        """
        result = {
            'wikidata_qid': None,
            'start_date': None,
            'end_date': None,
            'logo_url': None,
            'official_website_url': None,
        }

        q_id = cls.get_wikidata_entity_id(page_title)
        if not q_id:
            return result

        result['wikidata_qid'] = q_id

        try:
            url = f"https://www.wikidata.org/wiki/Special:EntityData/{q_id}.json"
            res = requests.get(url, headers=cls.HEADERS, timeout=10)
            if res.status_code != 200:
                return result

            data = res.json()
            entity = data.get('entities', {}).get(q_id, {})
            claims = entity.get('claims', {})

            # P580 = start time, P581 = end time
            def _extract_time(pid: str) -> Optional[str]:
                p_list = claims.get(pid, [])
                if p_list:
                    time_val = p_list[0].get('mainsnak', {}).get('datavalue', {}).get('value', {}).get('time', '')
                    if time_str := time_val.lstrip('+').split('T')[0]:
                        return time_str
                return None

            def is_valid_tournament_logo(url: str) -> bool:
                if not url or not isinstance(url, str):
                    return False
                url_lower = url.lower()
                flag_patterns = [
                    'flag_of', 'flag%20of', 'flag%5fof', 'flag-', 'flag_',
                    'bandeira', 'drapeau', 'bandera', 'flagg',
                    '/flag', 'flag.', 'flag-icon', 'country-flag'
                ]
                for pattern in flag_patterns:
                    if pattern in url_lower:
                        return False
                return True

            # P154 = logo image, P18 = general image
            def _extract_image(pid: str) -> Optional[str]:
                p_list = claims.get(pid, [])
                for p_item in p_list:
                    img_name = p_item.get('mainsnak', {}).get('datavalue', {}).get('value', '')
                    if img_name:
                        img_url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{urllib.parse.quote(img_name)}"
                        if is_valid_tournament_logo(img_url):
                            return img_url
                return None

            # P856 = official website
            def _extract_string(pid: str) -> Optional[str]:
                p_list = claims.get(pid, [])
                if p_list:
                    val = p_list[0].get('mainsnak', {}).get('datavalue', {}).get('value', '')
                    if val and isinstance(val, str):
                        return val
                return None

            result['start_date'] = _extract_time('P580')
            result['end_date'] = _extract_time('P581')
            result['logo_url'] = _extract_image('P154') or _extract_image('P18')
            result['official_website_url'] = _extract_string('P856')

        except Exception as exc:
            logger.warning("WikidataScout: Error fetching entity data for Q-ID '%s': %s", q_id, exc)

        return result
