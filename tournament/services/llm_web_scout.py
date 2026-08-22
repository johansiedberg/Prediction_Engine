import json
import logging
import re
from django.conf import settings
import google.generativeai as genai

logger = logging.getLogger(__name__)

class LLMWebScout:
    """
    Tier 1 Agentic Web Scout.
    Uses Gemini with Google Search Grounding to hunt for official rules.
    """
    def __init__(self):
        api_key = getattr(settings, 'GEMINI_API_KEY', '')
        if api_key:
            genai.configure(api_key=api_key)
        # Initialize model with Google Search Grounding enabled
        # Try models in order of available quota (Flash-Lite has 500 RPD)
        target_models = ['gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-2.0-flash', 'gemini-2.0-flash-lite', 'gemini-1.5-flash']
        self.model = None
        for m in target_models:
            try:
                self.model = genai.GenerativeModel(m, tools='google_search_retrieval')
                break
            except Exception:
                try:
                    self.model = genai.GenerativeModel(m)
                    break
                except Exception:
                    continue
        if self.model is None:
            self.model = genai.GenerativeModel('gemini-2.5-flash-lite')

    def search_official_rules(self, tournament_name: str, whitelisted_domains: list) -> dict:
        """
        Executes a web search to find official rules on the whitelisted domains.
        Returns a dictionary with extracted rules and provenance metadata.
        """
        domains_str = " OR ".join([f"site:{d}" for d in whitelisted_domains]) if whitelisted_domains else ""
        prompt = f"""
You are an expert sports data analyst. Your task is to find the official tiebreaker rules and points system for "{tournament_name}".

You MUST ONLY extract data if you can confirm it comes from one of these official domains: {whitelisted_domains}.
Search the web for the official regulations.

Return a JSON object with this exact structure:
{{
  "official_rules": "Detailed text of the points system and tiebreaker rules...",
  "provenance": {{
    "source_url": "https://uefa.com/...",
    "domain_verified": true,
    "confidence": "high"
  }}
}}
If you cannot find the data on an official domain, set domain_verified to false and confidence to low.
"""
        
        try:
            response = self.model.generate_content(prompt)
            json_str = response.text
            match = re.search(r'```(?:json)?\n(.*?)\n```', json_str, re.DOTALL | re.IGNORECASE)
            if match:
                json_str = match.group(1)
            
            data = json.loads(json_str)
            return data
        except Exception as e:
            logger.error(f"LLMWebScout error: {e}")
            return {
                "official_rules": "",
                "provenance": {
                    "source_url": "",
                    "domain_verified": False,
                    "confidence": "error"
                }
            }
