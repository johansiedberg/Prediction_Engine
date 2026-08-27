"""
Phase 2: Modular Deepscan Agent (5-Segment Orchestrator)
========================================================
Tool-Agnostic, Source-Agnostic Deep Scout Orchestrator that coordinates the 5 specialized
segment agents to populate the complete TournamentProspectBlueprint JSON schema:
1. HeadDiscoveryAgent -> HeadSegment
2. GeneralDeepScoutAgent -> GeneralSegment
3. StructureRulesAgent -> StructureAndRulesSegment
4. GroupsTeamsAgent -> GroupsAndTeamsSegment
5. MatchesKnockoutAgent -> MatchesAndKnockoutSegment

Evaluates completeness & assigns readiness grades:
- GRADE_A (Redo / 100% Ready): Confirmed dates, real teams, draw complete, schedule ready.
- GRADE_B (Väntar lottning): Confirmed start date, but draw pending or team placeholders.
- GRADE_C (Ej redo): Missing fixtures, schedule, or dates.
- AUTO-REJECTION / DELETION: Deletes past/ongoing events or events starting < 30 days.
"""

import datetime
import logging
import re
import urllib.parse
from typing import Dict, Any, Optional, List, Tuple

from django.utils import timezone

from tournament.schemas.tournament_prospect_schema import (
    TournamentProspectBlueprint,
    HeadSegment,
    GeneralSegment,
    StructureAndRulesSegment,
    GroupsAndTeamsSegment,
    MatchesAndKnockoutSegment,
    ScoutingAudit,
    ScoutingStage,
    CompletenessGrade,
    ProspectStatus,
)
from tournament.models import ScannedTournament
from tournament.services.wikipedia_scout import WikipediaScout
from tournament.services.wikidata_scout import WikidataScout
from tournament.services.official_regulations_verifier import OfficialRegulationsVerifier
from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
from tournament.services.head_discovery_agent import HeadDiscoveryAgent
from tournament.services.general_deep_scout_agent import GeneralDeepScoutAgent
from tournament.services.structure_rules_agent import StructureRulesAgent
from tournament.services.groups_teams_agent import GroupsTeamsAgent
from tournament.services.matches_knockout_agent import MatchesKnockoutAgent

logger = logging.getLogger(__name__)


class ModularDeepScout:
    """
    Modular 5-Segment Deepscan Orchestrator.
    """

    def __init__(self):
        self.wiki_scout = WikipediaScout()
        self.wikidata_scout = WikidataScout()
        self.off_verifier = OfficialRegulationsVerifier()
        self.llm_scout = LLMWikipediaScout()
        self.head_agent = HeadDiscoveryAgent()
        self.general_agent = GeneralDeepScoutAgent()
        self.structure_agent = StructureRulesAgent()
        self.groups_agent = GroupsTeamsAgent()
        self.matches_agent = MatchesKnockoutAgent()

    def deep_scan_prospect(self, prospect: ScannedTournament) -> Dict[str, Any]:
        """
        Performs a full tool-agnostic Deepscan on a ScannedTournament prospect,
        orchestrating the 5 segment agents and saving the unified 5-segment blueprint.
        """
        payload = prospect.payload or {}
        scouting_audit = payload.get('scouting_audit', {})
        today_date = datetime.date.today()
        active_sources: List[str] = []

        # 0. Early Rejection based on known prospect header dates
        min_upcoming_date = today_date + datetime.timedelta(days=30)
        
        if prospect.start_date and prospect.start_date < min_upcoming_date:
            p_name = prospect.name
            prospect.delete()
            return {
                'ok': False,
                'error': f"Djupscanning avbröts direkt: Turneringen '{p_name}' är pågående eller startar inom 30 dagar (Startdatum: {prospect.start_date}). Endast framtida turneringar accepteras.",
            }
            
        if prospect.end_date and prospect.end_date < today_date:
            p_name = prospect.name
            prospect.delete()
            return {
                'ok': False,
                'error': f"Djupscanning avbröts direkt: Turneringen '{p_name}' har redan avslutats (Slutdatum: {prospect.end_date}).",
            }


        # Fallback early rejection based on tournament year in title (if missing exact dates)
        import re
        if not prospect.start_date:
            year_match = re.search(r'\b(19\d{2}|20\d{2})\b', prospect.name)
            if year_match:
                tournament_year = int(year_match.group(1))
                if tournament_year < today_date.year:
                    p_name = prospect.name
                    prospect.delete()
                    return {
                        'ok': False,
                        'error': f"Djupscanning avbröts direkt: Turneringen '{p_name}' spelades år {tournament_year} vilket är i det förflutna. Endast framtida turneringar accepteras.",
                    }

        # Step 0.5: Generic Umbrella Tournament Auto-Disambiguation & Merging
        # e.g., 'UEFA Nations League' -> '2026–27 UEFA Nations League', 'CONCACAF Gold Cup' -> '2027 CONCACAF Gold Cup'
        has_year = bool(re.search(r'\b(19\d{2}|20\d{2})\b', prospect.name))
        if not has_year:
            from tournament.models import ScannedTournament
            from tournament.services.scout_service import normalize_brand_key
            brand_key = normalize_brand_key(prospect.name)
            
            # Find existing active editions matching this brand
            all_prospects = list(ScannedTournament.objects.exclude(id=prospect.id).exclude(status='ARCHIVED'))
            matching_editions = [
                p for p in all_prospects
                if normalize_brand_key(p.name) == brand_key and re.search(r'\b(20\d{2})\b', p.name)
            ]
            
            if matching_editions:
                # Retain the highest quality edition
                matching_editions.sort(
                    key=lambda p: (
                        p.completeness_grade == 'GRADE_A',
                        p.completeness_grade == 'GRADE_B',
                        len((p.payload or {}).get('matches_and_knockout_segment', {}).get('group_matches', [])),
                        -p.id
                    ),
                    reverse=True
                )
                target = matching_editions[0]
                
                # Merge official URLs if target lacks it
                if prospect.official_source_url and not target.official_source_url:
                    target.official_source_url = prospect.official_source_url
                    target.save()
                    
                target_name = target.name
                target_id = target.id
                target_grade = target.completeness_grade
                target_payload = target.payload or {}
                
                logger.info("Auto-merging generic umbrella prospect '%s' (ID %d) into concrete edition '%s' (ID %d)", prospect.name, prospect.id, target_name, target_id)
                prospect.delete()
                
                return {
                    'ok': True,
                    'merged_into': target_id,
                    'target_name': target_name,
                    'grade': target_grade,
                    'grade_reason': f"Automatiskt sammanfogad med den officiella säsongsupplagan '{target_name}'.",
                    'fixtures_count': len(target_payload.get('matches_and_knockout_segment', {}).get('group_matches', [])),
                    'groups_count': len(target_payload.get('groups_and_teams_segment', {}).get('groups', [])),
                    'draw_completed': bool(target_payload.get('structure_and_rules_segment', {}).get('general_setup', {}).get('draw_completed')),
                    'draw_date': target_payload.get('structure_and_rules_segment', {}).get('general_setup', {}).get('draw_date', ''),
                    'scheduled_matchdays': len(target_payload.get('matches_and_knockout_segment', {}).get('group_matches', [])),
                }
            else:
                # Look up the upcoming concrete edition name on Wikipedia/Search
                upcoming_title = self.wiki_scout.search_wikipedia_article(f"{today_date.year} {prospect.name}") or self.wiki_scout.search_wikipedia_article(f"{today_date.year+1} {prospect.name}")
                if upcoming_title and re.search(r'\b(20\d{2})\b', upcoming_title):
                    logger.info("Upgrading generic umbrella prospect '%s' to upcoming concrete edition '%s'", prospect.name, upcoming_title)
                    prospect.name = upcoming_title
                    prospect.save()

        # 1. Resolve source page title or URL
        official_url = prospect.official_source_url or payload.get('master_event', {}).get('official_source_url') or scouting_audit.get('official_source_url') or ''
        wiki_url = scouting_audit.get('wikipedia_url') or (official_url if 'wikipedia.org' in (official_url or '') else '')
        page_title = self.wiki_scout.get_article_title_from_url(wiki_url)
        if not page_title:
            page_title = scouting_audit.get('wikipedia_title') or ''
        # 1. Discover Official Federation Portal & Ranked Sources via Google Search Grounding
        from tournament.services.official_site_scout import OfficialSiteScout
        ranked_sources = OfficialSiteScout.search_and_rank_tournament_sources(prospect.name, prospect.sport or "Football")
        if ranked_sources:
            top_src = ranked_sources[0]
            if top_src.get("score", 0) >= 30 and top_src.get("url"):
                official_url = top_src["url"]
                prospect.official_source_url = official_url
                payload.setdefault('master_event', {})['official_source_url'] = official_url
                payload.setdefault('scouting_audit', {})['official_source_url'] = official_url

        if not page_title:
            page_title = self.wiki_scout.search_wikipedia_article(prospect.name)

        audit = None
        if page_title:
            audit = self.llm_scout.audit_with_llm(page_title)
            if audit:
                active_sources.append(f"Multi-Source Registry Audit ({audit.get('source_type', 'Continental Registry')})")

        if not audit and official_url and 'wikipedia.org' not in official_url:
            audit = self.llm_scout.audit_webpage_content(official_url, prospect.name)
            if audit:
                active_sources.append(f"Official Site Parser ({official_url})")

        if not audit and (page_title or official_url):
            from tournament.services.gemini_scout_service import GeminiScoutService
            if GeminiScoutService.is_available():
                logger.info("ModularDeepScout: Querying Gemini AI with Google Search Grounding for '%s'", prospect.name)
                gemini_struct = GeminiScoutService.scout_structure_and_rules(
                    tournament_name=prospect.name,
                    sport=prospect.sport or "Football",
                    teams_count=getattr(prospect, 'teams_count', None) or payload.get('tournament_config', {}).get('total_teams'),
                    official_url=official_url,
                )
                if gemini_struct:
                    audit = gemini_struct
                    active_sources.append("Google Gemini AI Deep Intelligence")

        if not audit:
            prospect.completeness_grade = 'GRADE_C'
            prospect.grade_reason = f"Grad C (Ej redo): Kunde inte hämta data för '{prospect.name}'."
            if prospect.status not in ['WATCHLIST', 'CONVERTED', 'ARCHIVED']:
                prospect.status = 'NOT_READY'
            prospect.save()
            return {
                'ok': False,
                'error': f'Kunde inte läsa källsida för "{prospect.name}".',
            }

        # 1.4 Ingest Official Federation Portal Content & Press Releases
        if official_url and 'wikipedia.org' not in official_url:
            try:
                official_ingest = self.verifier.ingest_official_page(official_url, prospect.name)
                if official_ingest.get('verified'):
                    domain_name = urllib.parse.urlparse(official_url).netloc
                    active_sources.append(f"Official Federation Intelligence ({domain_name})")
                audit['official_ingest'] = official_ingest
            except Exception as exc:
                logger.debug("ModularDeepScout: Official page ingestion warning for '%s': %s", prospect.name, exc)

        # Handle Disambiguation / Split Tournament Portal pages

        # 1.5 Intermediate Auto-Rejection (Header Stage)
        # Rejects past tournaments instantly after the initial audit fetch, bypassing all 5 sub-agents
        audit_start = audit.get("start_date") or audit.get("tournament_start_date")
        if audit_start:
            try:
                astart_obj = datetime.date.fromisoformat(str(audit_start)[:10])
                if astart_obj < min_upcoming_date:
                    p_name = prospect.name
                    prospect.delete()
                    return {
                        'ok': False,
                        'error': f"Djupscanning misslyckades: Turneringen '{p_name}' är pågående eller startar inom mindre än 30 dagar (Startdatum: {astart_obj}). Endast framtida turneringar accepteras.",
                    }
            except Exception:
                pass

        if audit.get('is_disambiguation') and audit.get('sub_tournaments'):
            from tournament.services.scout_service import parse_and_save_scouted_json
            created_names = []
            for sub in audit.get('sub_tournaments'):
                sub_name = sub.get('name') or sub.get('wiki_title')
                if not sub_name:
                    continue
                sub_url = sub.get('wiki_url') or f"https://en.wikipedia.org/wiki/{urllib.parse.quote(sub_name.replace(' ', '_'))}"
                sub_code = sub_name.lower().replace(' ', '-').replace("'", '').replace('/', '-')[:100]
                
                # Auto-reject sub-tournaments from past years
                year_match = re.search(r'\b(19\d{2}|20\d{2})\b', sub_name)
                if year_match:
                    tournament_year = int(year_match.group(1))
                    if tournament_year < today_date.year:
                        logger.info(f"Skipping sub-tournament '{sub_name}' because year {tournament_year} is in the past.")
                        continue

                sub_payload = {
                    "scouting_audit": {
                        "scan_timestamp": datetime.datetime.now().isoformat(),
                        "scouting_stage": "SHALLOW",
                        "completeness_grade": "GRADE_C",
                        "grade_reason": f"Uppdelad från samlingssida '{prospect.name}'. Klicka 'Djupscanna' för fullständig analys.",
                        "official_source_url": "",
                        "wikipedia_url": sub_url,
                        "wikipedia_title": sub_name,
                        "is_compatible_sport": True,
                    },
                    "master_event": {
                        "name": sub_name,
                        "code": sub_code,
                        "sport": prospect.sport or "Football",
                        "organizer": prospect.organizer or "Sports Federation",
                        "host_country": prospect.host_country or "",
                        "official_source_url": "",
                        "wikipedia_url": sub_url,
                        "start_date": "",
                        "end_date": "",
                    },
                    "tournament_config": {
                        "name": sub_name,
                        "total_teams": 16,
                        "knockout_stages": ["Quarterfinals", "Semifinals", "Final"],
                    },
                    "groups": [],
                    "fixtures_sample": [],
                }
                sub_obj, _, _ = parse_and_save_scouted_json(sub_payload)
                if sub_obj:
                    created_names.append(sub_obj.name)

            prospect.completeness_grade = 'GRADE_C'
            prospect.grade_reason = f"Grad C (Uppdelad): Innehåller {len(created_names)} separata turneringar ({', '.join(created_names)}). Se respektive turneringskort i scout-listan."
            prospect.save()

            return {
                'ok': True,
                'grade': 'GRADE_C',
                'grade_reason': prospect.grade_reason,
                'fixtures_count': 0,
                'groups_count': 0,
                'teams_count': 0,
                'draw_completed': False,
                'draw_date': '',
                'scheduled_matchdays': 0,
            }

        # -----------------------------------------------------------------------
        # EXECUTE 5 DEDICATED SEGMENT AGENTS (WITH GEMINI AI INTEGRATION)
        # -----------------------------------------------------------------------

        # SEGMENT 1: Head Segment
        head_seg = self.head_agent.build_head_segment(
            name=prospect.name,
            sport=prospect.sport or audit.get('sport') or "Football",
            start_date=prospect.start_date.isoformat() if prospect.start_date else None,
            end_date=prospect.end_date.isoformat() if prospect.end_date else None,
            discovery_source="Deepscan Pipeline",
            master_event_code=prospect.master_event_code,
        )

        # SEGMENT 2: General Segment (Dates, venues, transparent vector emblems, and widescreen backdrops)
        general_seg = self.general_agent.build_general_segment(
            tournament_name=prospect.name,
            audit_data=audit,
            wikipedia_title=page_title,
            official_url=official_url,
            existing_logo_url=prospect.logo_url,
            existing_backdrop_url=prospect.backdrop_url,
        )

        # Date validation & Auto-Rejection Rules
        start_date_obj = None
        if general_seg.start_date:
            try:
                start_date_obj = datetime.date.fromisoformat(general_seg.start_date[:10])
            except Exception:
                pass
        if not start_date_obj and prospect.start_date:
            start_date_obj = prospect.start_date

        end_date_obj = None
        if general_seg.end_date:
            try:
                end_date_obj = datetime.date.fromisoformat(general_seg.end_date[:10])
            except Exception:
                pass
        if not end_date_obj and prospect.end_date:
            end_date_obj = prospect.end_date

        min_upcoming_date = today_date + datetime.timedelta(days=30)

        # Auto-Rejections
        if audit.get('is_ongoing_or_finished'):
            p_name = prospect.name
            prospect.delete()
            return {
                'ok': False,
                'error': f"Djupscanning misslyckades: Turneringen '{p_name}' är pågående eller avslutad (Spelade matcher/resultat hittades på Wikipedia). Endast framtida turneringar accepteras.",
            }

        if start_date_obj and start_date_obj < min_upcoming_date:
            p_name = prospect.name
            prospect.delete()
            return {
                'ok': False,
                'error': f"Djupscanning misslyckades: Turneringen '{p_name}' är pågående eller startar inom mindre än 30 dagar (Startdatum: {start_date_obj}, tröskel: {min_upcoming_date}). Endast framtida turneringar som startar om minst 30 dagar accepteras.",
            }

        if end_date_obj and end_date_obj < today_date:
            p_name = prospect.name
            prospect.delete()
            return {
                'ok': False,
                'error': f"Djupscanning misslyckades: Turneringen '{p_name}' har redan avslutats (Slutdatum: {end_date_obj}). Endast framtida turneringar accepteras.",
            }

        prospect.start_date = start_date_obj
        prospect.end_date = end_date_obj

        # SEGMENT 3: Structure & Rules Segment (Points W/D/L, tiebreakers, qualifying tables via Gemini AI)
        structure_rules_seg = self.structure_agent.build_structure_rules_segment(
            audit_data=audit,
            official_rules_text=audit.get('official_rules') or audit.get('advancement_rules') or "",
            tournament_name=prospect.name,
            sport=prospect.sport or "Football",
            teams_count=getattr(prospect, 'teams_count', None) or payload.get('tournament_config', {}).get('total_teams'),
        )

        # SEGMENT 4: Groups & Teams Segment (Group matrices, real teams, seeding pots via Gemini AI)
        groups_teams_seg = self.groups_agent.build_groups_teams_segment(
            audit_data=audit,
            default_groups_count=4,
            teams_per_group=4,
            tournament_name=prospect.name,
            sport=prospect.sport or "Football",
        )

        # SEGMENT 5: Matches & Knockout Segment (Timetable & knockout trees via Gemini AI)
        try:
            tournament_meta = {
                "name": prospect.name,
                "sport": prospect.sport or audit.get('sport') or "Football",
                "organizer": general_seg.organizer or prospect.organizer,
                "host_country": general_seg.location.host_country or prospect.host_country,
                "start_date": general_seg.start_date or (prospect.start_date.isoformat() if prospect.start_date else ""),
                "end_date": general_seg.end_date or (prospect.end_date.isoformat() if prospect.end_date else ""),
                "total_teams": groups_teams_seg.teams_count or getattr(prospect, 'teams_count', 0),
                "official_website_url": general_seg.official_website_url or official_url,
                "wikipedia_url": general_seg.wikipedia_url or wiki_url,
            }
            matches_ko_seg = self.matches_agent.build_matches_knockout_segment(
                audit_data=audit,
                groups_segment=groups_teams_seg,
                tournament_name=prospect.name,
                sport=prospect.sport or "Football",
                tournament_meta=tournament_meta,
            )
        except Exception as exc:
            from tournament.schemas.tournament_prospect_schema import MatchesAndKnockoutSegment
            matches_ko_seg = MatchesAndKnockoutSegment(
                fixtures_completed=False,
                scheduled_matchdays=0,
                group_matches=[],
                knockout_bracket=[],
                advancement_fixtures=[],
                total_matches=0,
            )


        # Grade Evaluation
        has_full_dates = bool(start_date_obj and end_date_obj)
        has_start_date = bool(start_date_obj)

        draw_date_str = structure_rules_seg.general_setup.draw_date or ''
        draw_has_passed = False
        if draw_date_str:
            try:
                from dateutil import parser
                parsed_draw = parser.parse(str(draw_date_str), fuzzy=True).date()
                if parsed_draw <= today_date:
                    draw_has_passed = True
            except Exception:
                pass

        if draw_has_passed or (groups_teams_seg.has_real_teams and groups_teams_seg.groups_count >= 2):
            structure_rules_seg.general_setup.draw_completed = True

        draw_ok = bool(
            structure_rules_seg.general_setup.draw_completed
            and groups_teams_seg.groups_count >= 2
            and groups_teams_seg.has_real_teams
        )
        fixtures_ok = bool(
            matches_ko_seg.fixtures_completed
            or (matches_ko_seg.total_matches >= 4 and groups_teams_seg.has_real_teams)
        )

        # Empty Prospect Rejection Rule
        is_empty_teams = not groups_teams_seg.has_real_teams and (audit.get('teams_count', 0) == 0)
        if not has_start_date and not draw_ok and not fixtures_ok and is_empty_teams:
            p_name = prospect.name
            prospect.delete()
            return {
                'ok': False,
                'error': f"Djupscanning misslyckades: Turneringen '{p_name}' saknar datum, spelschema och lag. Turneringen avvisades.",
            }

        if has_full_dates and draw_ok and fixtures_ok and groups_teams_seg.has_real_teams:
            final_grade = CompletenessGrade.GRADE_A
            final_reason = (f"Grad A (Redo): Verifierad från officiella källor ({', '.join(active_sources)}). "
                            f"({start_date_obj} – {end_date_obj}, {matches_ko_seg.total_matches} matcher, "
                            f"{groups_teams_seg.teams_count} lag i {groups_teams_seg.groups_count} grupper verifierade).")
        elif has_start_date and (not draw_ok or not groups_teams_seg.has_real_teams):
            final_grade = CompletenessGrade.GRADE_B
            draw_date_str = structure_rules_seg.general_setup.draw_date or ''
            draw_info = f" (Lottningsdatum: {draw_date_str})" if draw_date_str else " (Lag ej lottade ännu / Platshållare)"
            final_reason = f"Grad B (Väntar lottning): Turneringen startar {start_date_obj}, men deltagande lag/grupper är inte lottade ännu{draw_info}."
        else:
            final_grade = CompletenessGrade.GRADE_C
            date_info = f"Startdatum: {start_date_obj}" if start_date_obj else "Startdatum ej bekräftat ännu"
            final_reason = f"Grad C (Ej redo): {date_info}. Saknar spelschema, datum eller turneringsstruktur."

        # Unified 5-Segment Blueprint assembly
        unified_blueprint = TournamentProspectBlueprint(
            head_segment=head_seg,
            general_segment=general_seg,
            structure_and_rules_segment=structure_rules_seg,
            groups_and_teams_segment=groups_teams_seg,
            matches_and_knockout_segment=matches_ko_seg,
            scouting_audit=ScoutingAudit(
                stage=ScoutingStage.DEEP,
                completeness_grade=final_grade,
                status=ProspectStatus(prospect.status) if prospect.status in ['NEW', 'WATCHLIST', 'CONVERTED', 'ARCHIVED'] else ProspectStatus.NEW,
                grade_reason=final_reason,
                draw_date=structure_rules_seg.general_setup.draw_date,
                draw_completed=structure_rules_seg.general_setup.draw_completed,
                scan_timestamp=timezone.now().isoformat(),
                active_sources_used=active_sources,
            ),
        )

        # Update ScannedTournament DB instance
        payload_dict = unified_blueprint.to_payload_dict()
        prospect.completeness_grade = final_grade.value
        prospect.grade_reason = final_reason
        prospect.sport = head_seg.sport or prospect.sport
        prospect.logo_url = general_seg.emblem.logo_url or prospect.logo_url
        prospect.backdrop_url = general_seg.backdrop.backdrop_url or prospect.backdrop_url

        if final_grade == CompletenessGrade.GRADE_A:
            prospect.status = 'READY'
        elif prospect.status not in ['WATCHLIST', 'CONVERTED', 'ARCHIVED']:
            prospect.status = 'NOT_READY'

        if prospect.status == 'WATCHLIST':
            from tournament.services.scout_service import resolve_rescan_date_for_prospect
            prospect.rescan_date = resolve_rescan_date_for_prospect(prospect)

        prospect.payload = payload_dict
        prospect.tournament_blueprint = payload_dict.get('tournament_blueprint', {})
        prospect.save()

        return {
            'ok': True,
            'grade': final_grade.value,
            'grade_reason': final_reason,
            'fixtures_count': matches_ko_seg.total_matches,
            'groups_count': groups_teams_seg.groups_count,
            'teams_count': groups_teams_seg.teams_count,
            'draw_completed': structure_rules_seg.general_setup.draw_completed,
            'draw_date': structure_rules_seg.general_setup.draw_date or '',
            'scheduled_matchdays': len(matches_ko_seg.group_matches),
        }
