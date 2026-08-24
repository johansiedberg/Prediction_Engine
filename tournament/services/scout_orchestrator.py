import logging
import asyncio
from tournament.models import OfficialDataSource
from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
from tournament.services.llm_web_scout import LLMWebScout

logger = logging.getLogger(__name__)

class DualScoutOrchestrator:
    """
    Coordinates Tier 1 (Agentic Search) and Tier 2 (Wikipedia) extraction.
    Merges the payloads based on strict confidence and provenance hierarchy.
    """
    
    def run_deep_scan(self, tournament_name: str, master_event_code: str = "", known_official_url: str = "") -> dict:
        """
        Executes the dual-source scan sequentially or async if configured.
        Automatically whitelists the known official URL if provided.
        """
        import urllib.parse
        
        # Auto-add known official domain to Master List
        if known_official_url:
            try:
                domain = urllib.parse.urlparse(known_official_url).netloc
                if domain:
                    if domain.startswith("www."):
                        domain = domain[4:]
                    OfficialDataSource.objects.get_or_create(
                        domain=domain,
                        defaults={'name': tournament_name, 'is_verified': True}
                    )
            except Exception as e:
                logger.error(f"Failed to auto-add official domain: {e}")
                
        # Fetch Master List domains
        whitelisted_domains = list(OfficialDataSource.objects.filter(is_verified=True).values_list('domain', flat=True))
        
        # 1. Tier 2: Wikipedia (Structured Fixtures & Brackets)
        wiki_scout = LLMWikipediaScout()
        wiki_payload = wiki_scout.audit_with_llm(tournament_name)
        
        # 2. Tier 1: Agentic Web Search (Official Rules & Tiebreakers)
        web_scout = LLMWebScout()
        web_payload = web_scout.search_official_rules(tournament_name, whitelisted_domains)
        
        # 3. Reconciliation & Merge
        final_payload = self._merge_payloads(web_payload, wiki_payload)
        
        return final_payload
        
    def _merge_payloads(self, web_payload: dict, wiki_payload: dict) -> dict:
        """
        Merges the Tier 1 (web) and Tier 2 (wiki) payloads.
        Rules and Tiebreakers from Tier 1 override Tier 2 if domain is verified.
        """
        merged = wiki_payload.copy() if wiki_payload else {}
        
        # Initialize provenance tracking
        provenance = {
            "official_rules": {
                "source": "Wikipedia (Tier 2 Fallback)",
                "confidence": "low",
                "url": merged.get("wiki_url", "")
            }
        }
        
        web_rules = web_payload.get("official_rules")
        web_prov = web_payload.get("provenance", {})
        
        # If Web Scout found rules on an official domain, override Wikipedia
        if web_rules and web_prov.get("domain_verified"):
            # Store as official rules text, not as points_system (which expects a dict)
            merged["official_rules_text"] = web_rules
            provenance["official_rules"] = {
                "source": "Official Web Agent (Tier 1)",
                "confidence": web_prov.get("confidence", "high"),
                "url": web_prov.get("source_url", "")
            }
            # We can also store the raw web rules in the merged dict
            merged["official_rules"] = web_rules
            
        merged["provenance_metadata"] = provenance
        return merged
