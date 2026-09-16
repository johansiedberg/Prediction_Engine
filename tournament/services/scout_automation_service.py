import datetime
import logging
from typing import Dict, Any, List, Optional
from django.utils import timezone
from tournament.models import ScannedTournament
from tournament.services.scout_scan_logger import ScoutScanLogger

logger = logging.getLogger(__name__)


class ScoutAutomationService:
    """
    Orchestration service for automated Scout scans:
    1. Monthly General Scan (Webscan + Deepscan on the 1st of every month to discover new tournaments).
    2. Weekly Deepscan for tournaments set to 'Under Survey' (WATCHLIST), respecting each tournament's
       specific survey_start_date.
    3. Outputs tree-structured reports to logs/scout_scans.log via ScoutScanLogger.
    """

    @classmethod
    def run_monthly_general_scan(cls, custom_query: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes the monthly general webscan and deepscan across all pillars:
        - AllSportDB, Wikipedia, and Google Gemini AI Search Grounding.
        - Deep-scans newly discovered and active non-converted prospects.
        - Generates a tree-structured entry in logs/scout_scans.log.
        """
        today = timezone.localdate()
        logger.info(f"Starting Monthly General Scout Scan for {today}...")

        from tournament.services.web_crawl_agent import WebCrawlAgent
        from tournament.services.modular_deep_scout import ModularDeepScout
        from tournament.services.official_regulations_verifier import OfficialRegulationsVerifier
        from tournament.services.wikipedia_scout import WikipediaScout

        accepted_items: List[Dict[str, Any]] = []
        rejected_items: List[Dict[str, Any]] = []

        # 1. Run Web Discovery & Ingestion
        agent = WebCrawlAgent()
        created_cnt, updated_cnt, ingested_prospects = agent.discover_and_ingest(custom_query=custom_query)

        # 2. Deep-scan all candidate prospects (newly discovered or not yet GRADE_A)
        wiki_scout = WikipediaScout()
        off_verifier = OfficialRegulationsVerifier()
        modular_scout = ModularDeepScout()
        modular_scout.wiki_scout = wiki_scout
        modular_scout.off_verifier = off_verifier

        # Focus deepscan on non-converted prospects discovered or active
        target_prospects = list(
            ScannedTournament.objects.exclude(status='CONVERTED').order_by('-created_at')[:30]
        )

        for p in target_prospects:
            try:
                res = modular_scout.deep_scan_prospect(p)
                p.refresh_from_db()
                if res.get('ok'):
                    details_parts = []
                    if res.get('fixtures_count'):
                        details_parts.append(f"{res['fixtures_count']} matcher")
                    if res.get('teams_count'):
                        details_parts.append(f"{res['teams_count']} lag")
                    if res.get('draw_completed') is False:
                        details_parts.append("lottning ej klar")
                    else:
                        details_parts.append("lottning klar")

                    details_str = ", ".join(details_parts) if details_parts else (p.grade_reason or "Godkänd")
                    accepted_items.append({
                        "name": p.name,
                        "sport": p.sport,
                        "grade": p.completeness_grade,
                        "status": p.status,
                        "details": details_str,
                    })
                else:
                    err = res.get('error', 'Okänt fel vid djupscanning')
                    rejected_items.append({
                        "name": p.name,
                        "sport": p.sport,
                        "status": "REJECTED",
                        "details": err,
                    })
            except Exception as e:
                logger.error(f"Error deep-scanning prospect {p.id} ({p.name}) in monthly scan: {e}")
                rejected_items.append({
                    "name": p.name,
                    "sport": p.sport,
                    "status": "ERROR",
                    "details": str(e),
                })

        total_found = len(accepted_items) + len(rejected_items)
        
        # 3. Write tree-structured log entry
        log_text = ScoutScanLogger.log_scan(
            scan_type="Månatlig allmän scanning (Webb- & Djupscanning)",
            total_found=total_found,
            accepted_items=accepted_items,
            rejected_items=rejected_items,
        )

        return {
            "ok": True,
            "scan_type": "monthly",
            "created_count": created_cnt,
            "updated_count": updated_cnt,
            "scanned_count": len(accepted_items),
            "rejected_count": len(rejected_items),
            "total_found": total_found,
            "log_text": log_text,
        }

    @classmethod
    def run_weekly_survey_scan(cls) -> Dict[str, Any]:
        """
        Executes weekly deepscan of all tournaments set to 'Under Survey' (WATCHLIST),
        respecting the specific survey_start_date configured per tournament:
        - If today < survey_start_date: Item is held as PENDING (not yet scanned).
        - If survey_start_date is None or survey_start_date <= today: Item is deep-scanned.
        - Updates next_rescan_date to today + 7 days.
        - Generates a tree-structured entry in logs/scout_scans.log.
        """
        today = timezone.localdate()
        logger.info(f"Starting Weekly Survey Deepscan for {today}...")

        from tournament.services.modular_deep_scout import ModularDeepScout
        from tournament.services.official_regulations_verifier import OfficialRegulationsVerifier
        from tournament.services.wikipedia_scout import WikipediaScout

        survey_prospects = list(ScannedTournament.objects.filter(status='WATCHLIST'))
        total_found = len(survey_prospects)

        accepted_items: List[Dict[str, Any]] = []
        pending_items: List[Dict[str, Any]] = []
        rejected_items: List[Dict[str, Any]] = []

        wiki_scout = WikipediaScout()
        off_verifier = OfficialRegulationsVerifier()
        modular_scout = ModularDeepScout()
        modular_scout.wiki_scout = wiki_scout
        modular_scout.off_verifier = off_verifier

        for p in survey_prospects:
            s_date = p.survey_start_date
            # Check per-tournament specific start date logic
            if s_date and s_date > today:
                pending_items.append({
                    "name": p.name,
                    "sport": p.sport,
                    "status": "PENDING",
                    "details": f"Veckoscanning startar {s_date.strftime('%Y-%m-%d')} (om {(s_date - today).days} dagar)",
                })
                continue

            # Due for weekly deepscan
            try:
                res = modular_scout.deep_scan_prospect(p)
                p.refresh_from_db()
                next_weekly = today + datetime.timedelta(days=7)

                # Update next rescan in payload
                payload = p.payload or {}
                audit = payload.setdefault('scouting_audit', {})
                audit['next_rescan_date'] = next_weekly.strftime('%Y-%m-%d')
                p.payload = payload
                p.save(update_fields=['payload', 'completeness_grade', 'grade_reason'])

                if res.get('ok'):
                    # Check if draw is completed and upgraded to Grade A
                    extra = []
                    if p.completeness_grade == 'GRADE_A':
                        extra.append("100% redo / lottning klar")
                    else:
                        extra.append(f"betyg {p.completeness_grade}")
                    extra.append(f"nästa veckoscanning {next_weekly.strftime('%Y-%m-%d')}")

                    accepted_items.append({
                        "name": p.name,
                        "sport": p.sport,
                        "grade": p.completeness_grade,
                        "status": "SURVEY_SCANNED",
                        "details": ", ".join(extra),
                    })
                else:
                    err = res.get('error', 'Ej redo')
                    rejected_items.append({
                        "name": p.name,
                        "sport": p.sport,
                        "status": "SURVEY_INCOMPLETE",
                        "details": f"{err} (omprövas {next_weekly.strftime('%Y-%m-%d')})",
                    })

            except Exception as e:
                logger.error(f"Weekly survey deepscan failed for prospect {p.id} ({p.name}): {e}", exc_info=True)
                rejected_items.append({
                    "name": p.name,
                    "sport": p.sport,
                    "status": "ERROR",
                    "details": str(e),
                })

        # Write tree-structured log entry
        log_text = ScoutScanLogger.log_scan(
            scan_type="Veckovis djupscanning (Under Survey)",
            total_found=total_found,
            accepted_items=accepted_items,
            rejected_items=rejected_items,
            pending_items=pending_items,
        )

        return {
            "ok": True,
            "scan_type": "weekly",
            "total_found": total_found,
            "scanned_count": len(accepted_items),
            "pending_count": len(pending_items),
            "rejected_count": len(rejected_items),
            "log_text": log_text,
        }
