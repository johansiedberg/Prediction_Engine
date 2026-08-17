import logging
import urllib.parse
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

class AllSportDBClient:
    """
    Python utility client for interacting with AllSportDB API (v3).
    Reads API Key securely from Django settings (ALLSPORTDB_API_KEY).
    """

    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key or getattr(settings, 'ALLSPORTDB_API_KEY', '')
        self.base_url = (base_url or getattr(settings, 'ALLSPORTDB_API_BASE_URL', 'https://api.allsportdb.com/v3')).rstrip('/')
        self.last_error = None

        if not self.api_key:
            self.last_error = "ALLSPORTDB_API_KEY saknas i Django-inställningarna eller miljövariablerna."
            logger.warning(self.last_error)

    def get_headers(self):
        """Constructs API request headers with API key authentication."""
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'PredictionEngine-TournamentScout/1.0',
        }
        if self.api_key:
            headers['Authorization'] = f"Bearer {self.api_key}"
            headers['x-api-key'] = self.api_key
            headers['api_key'] = self.api_key
        return headers

    def get_sports(self):
        """
        Fetches the full list of sports from the AllSportDB /sports endpoint.
        Returns a list of dicts: [{'id': 1, 'name': 'Football'}, ...]
        """
        url = f"{self.base_url}/sports"
        params = {}
        if self.api_key:
            params['api_key'] = self.api_key

        try:
            response = requests.get(url, headers=self.get_headers(), params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return data.get('sports') or data.get('data') or data.get('items') or []
            else:
                self.last_error = f"HTTP {response.status_code}: {response.text[:150]}"
                logger.error(f"AllSportDB /sports failed with {self.last_error}")
        except Exception as e:
            self.last_error = f"Nätverksfel vid /sports: {str(e)}"
            logger.error(self.last_error)
        
        return []

    def get_calendar(self, start_date=None, end_date=None):
        """
        Fetches upcoming sports events from the AllSportDB /calendar endpoint.
        Parameters:
            start_date: YYYY-MM-DD string or datetime.date
            end_date: YYYY-MM-DD string or datetime.date
        Returns list of event dictionaries.
        """
        url = f"{self.base_url}/calendar"
        params = {}
        if self.api_key:
            params['api_key'] = self.api_key
        if start_date:
            params['dateFrom'] = str(start_date)
            params['startDate'] = str(start_date)
        if end_date:
            params['dateTo'] = str(end_date)
            params['endDate'] = str(end_date)


        try:
            response = requests.get(url, headers=self.get_headers(), params=params, timeout=20)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return data.get('events') or data.get('calendar') or data.get('data') or data.get('items') or []
            else:
                self.last_error = f"HTTP {response.status_code}: {response.text[:150]}"
                logger.error(f"AllSportDB /calendar failed with {self.last_error}")
        except Exception as e:
            self.last_error = f"Nätverksfel vid /calendar: {str(e)}"
            logger.error(self.last_error)

        return []

    def fetch_official_regulations_url(self, event_name, official_website=None):
        """
        Agent Fallback Hook:
        If official_website is missing or official rulebook PDF is needed for knockout bracket structure,
        returns an AI search query fallback template.
        """
        if official_website and official_website.lower().endswith('.pdf'):
            return official_website

        encoded_query = urllib.parse.quote_plus(f"{event_name} official tournament regulations format filetype:pdf")
        return f"https://www.google.com/search?q={encoded_query}"
