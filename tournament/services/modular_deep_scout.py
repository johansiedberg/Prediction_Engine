"""
Phase 2: Modular Deepscan Agent
===============================
Tool-Agnostic, Source-Agnostic Deep Scout Orchestrator that populates the complete
TournamentProspectBlueprint JSON schema.

Decoupled from hardcoded Wikipedia scraping, using modular capability providers:
- OfficialRegulationsProvider (Scrapes & verifies official federation site rules)
- LLMMultiSourceParser (Uses Gemini Flash LLM to semantically extract groups, schedules, tiebreakers)
- WikidataProvider (Fetches Wikidata QID, official website, and emblem URLs)
- SkeletonBracketProvider (Generates group & knockout placeholders)

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
    ProspectMetadata,
    ScoutingAudit,
    ScoutingStage,
    CompletenessGrade,
    ProspectStatus,
    GroupProspect,
    TeamEntry,
    FixtureProspect,
    KnockoutStageProspect,
    KnockoutMatchProspect,
    RulesAndPointsProspect,
    TiebreakerRule,
)
from tournament.models import ScannedTournament
from tournament.services.wikipedia_scout import WikipediaScout
from tournament.services.wikidata_scout import WikidataScout
from tournament.services.official_regulations_verifier import OfficialRegulationsVerifier
from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
from tournament.services.skeleton_builder import SkeletonBuilder

logger = logging.getLogger(__name__)


def is_valid_tournament_logo(url: str) -> bool:
    """Helper: returns True if url is a valid tournament logo (not a flag)."""
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


class ModularDeepScout:
    """
    Modular Deepscan Orchestrator for Phase 2.
    """

    def __init__(self):
        self.wiki_scout = WikipediaScout()
        self.wikidata_scout = WikidataScout()
        self.off_verifier = OfficialRegulationsVerifier()
        self.llm_scout = LLMWikipediaScout()

    def deep_scan_prospect(self, prospect: ScannedTournament) -> Dict[str, Any]:
        """
        Performs a full tool-agnostic Deepscan on a ScannedTournament prospect,
        populates the unified TournamentProspectBlueprint schema, and persists results.
        """
        payload = prospect.payload or {}
        scouting_audit = payload.get('scouting_audit', {})
        today_date = datetime.date.today()
        active_sources: List[str] = []

        # 1. Resolve source page title or URL

        official_url = prospect.official_source_url or payload.get('master_event', {}).get('official_source_url') or scouting_audit.get('official_source_url') or ''
        wiki_url = scouting_audit.get('wikipedia_url') or (official_url if 'wikipedia.org' in (official_url or '') else '')
        page_title = self.wiki_scout.get_article_title_from_url(wiki_url)
        if not page_title:
            page_title = scouting_audit.get('wikipedia_title') or ''
        if not page_title:
            page_title = self.wiki_scout.search_wikipedia_article(prospect.name)

        audit = None
        if page_title:
            audit = self.llm_scout.audit_with_llm(page_title)
            if audit:
                active_sources.append(f"LLM Multimodal Audit ({audit.get('source_type', 'Wikipedia')})")

        if not audit and official_url and 'wikipedia.org' not in official_url:
            audit = self.llm_scout.audit_webpage_content(official_url, prospect.name)
            if audit:
                active_sources.append(f"Official Site Parser ({official_url})")

        if not audit and (not official_url or 'wikipedia.org' in official_url):
            from tournament.services.official_site_scout import OfficialSiteScout
            disc_url = OfficialSiteScout.discover_official_site(prospect.name, wikipedia_title=page_title)
            if disc_url:
                official_url = disc_url
                prospect.official_source_url = official_url
                payload.setdefault('master_event', {})['official_source_url'] = official_url
                payload.setdefault('scouting_audit', {})['official_source_url'] = official_url
                prospect.payload = payload
                prospect.save()
                audit = self.llm_scout.audit_webpage_content(official_url, prospect.name)
                if audit:
                    active_sources.append(f"Official Site Parser ({official_url})")


        if not audit:
            prospect.completeness_grade = 'GRADE_C'
            prospect.grade_reason = f"Grad C (Ej redo): Kunde inte läsa källsida eller källartikel för '{prospect.name}'."
            if prospect.status not in ['WATCHLIST', 'CONVERTED', 'ARCHIVED']:
                prospect.status = 'NOT_READY'
            prospect.save()
            return {
                'ok': False,
                'error': f'Kunde inte läsa källsida för "{prospect.name}".',
            }

        # Handle Disambiguation / Split Tournament Portal pages
        if audit.get('is_disambiguation') and audit.get('sub_tournaments'):
            from tournament.services.scout_service import parse_and_save_scouted_json
            created_names = []
            for sub in audit.get('sub_tournaments'):
                sub_name = sub.get('name') or sub.get('wiki_title')
                if not sub_name:
                    continue
                sub_url = sub.get('wiki_url') or f"https://en.wikipedia.org/wiki/{urllib.parse.quote(sub_name.replace(' ', '_'))}"
                sub_code = sub_name.lower().replace(' ', '-').replace("'", '').replace('/', '-')[:100]

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
                        "sport": prospect.sport or "Sports",
                        "organizer": prospect.organizer or "Wikipedia",
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

        active_sources.append(f"LLM Multimodal Audit ({audit.get('source_type', 'LLM')})")

        # 3. Wikidata Entity Resolution
        wikidata = self.wikidata_scout.fetch_wikidata_entity(page_title)
        if wikidata.get('wikidata_qid'):
            active_sources.append(f"Wikidata Entity ({wikidata['wikidata_qid']})")

        # Extract dates
        audit_start_str = audit.get('tournament_start_date') or audit.get('start_date') or wikidata.get('start_date') or ''
        audit_end_str = audit.get('tournament_end_date') or audit.get('end_date') or wikidata.get('end_date') or ''

        start_date_obj = None
        if audit_start_str:
            try:
                start_date_obj = datetime.date.fromisoformat(audit_start_str[:10])
            except Exception:
                pass
        if not start_date_obj and prospect.start_date:
            start_date_obj = prospect.start_date

        end_date_obj = None
        if audit_end_str:
            try:
                end_date_obj = datetime.date.fromisoformat(audit_end_str[:10])
            except Exception:
                pass
        if not end_date_obj and prospect.end_date:
            end_date_obj = prospect.end_date

        min_upcoming_date = today_date + datetime.timedelta(days=30)

        # 4. Auto-Rejection Rules
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

        # 5. Official Regulations Cross-Audit
        official_website = (
            payload.get('master_event', {}).get('official_source_url')
            or prospect.official_source_url
            or ''
        )
        official_audit = None
        if official_website:
            official_audit = self.off_verifier.verify_official_regulations(official_website, prospect.name)
            active_sources.append("Official Site Verifier")

        # 6. Parse groups & teams into schema models
        raw_groups = audit.get('groups') or payload.get('groups') or []
        group_models: List[GroupProspect] = []
        real_teams_count = 0
        total_teams_count = 0

        from tournament.services.scout_service import is_real_team_name, has_real_teams
        teams_real = has_real_teams(raw_groups)

        for g in raw_groups:
            g_name = g.get('name') if isinstance(g, dict) else "Group A"
            g_teams_raw = g.get('teams', []) if isinstance(g, dict) else []
            team_entries: List[TeamEntry] = []

            for t in g_teams_raw:
                t_name = t.get('name') if isinstance(t, dict) else str(t)
                t_code = (t.get('code') if isinstance(t, dict) else "") or ""
                is_fake = not is_real_team_name(t_name)
                total_teams_count += 1
                if not is_fake:
                    real_teams_count += 1
                team_entries.append(TeamEntry(
                    name=t_name,
                    code=t_code,
                    is_placeholder=is_fake,
                ))

            group_models.append(GroupProspect(
                name=g_name,
                teams_count=len(team_entries) or 4,
                teams=team_entries,
                advancement_description=g.get('advancement_description', '') if isinstance(g, dict) else '',
            ))

        # 7. Parse fixtures into schema models
        raw_fixtures = audit.get('fixtures') or payload.get('fixtures_sample') or []
        fixture_models: List[FixtureProspect] = []

        for idx, fix in enumerate(raw_fixtures, 1):
            if isinstance(fix, dict):
                dt_str = fix.get('date_time') or f"{fix.get('date', '')} {fix.get('time', '')}".strip()
                fixture_models.append(FixtureProspect(
                    match_number=fix.get('match_number') or idx,
                    stage_or_group=fix.get('stage_or_group') or "Gruppspel",
                    date_time=dt_str or None,
                    home_team=fix.get('home_team', ''),
                    away_team=fix.get('away_team', ''),
                    venue=fix.get('venue', ''),
                    is_placeholder=fix.get('is_placeholder', False),
                ))

        # 8. Knockout stage tree mapping via SkeletonBuilder
        raw_blueprint = audit.get('tournament_blueprint') or payload.get('tournament_blueprint') or {}
        sk_builder = SkeletonBuilder(raw_blueprint)
        skeleton = sk_builder.build_skeleton()
        raw_ko_tree = skeleton.get('knockout_tree', [])

        knockout_stage_models: List[KnockoutStageProspect] = []
        for stage_dict in raw_ko_tree:
            s_name = stage_dict.get('stage_name', 'Knockout')
            m_list = []
            for m in stage_dict.get('matches', []):
                m_list.append(KnockoutMatchProspect(
                    match_code=m.get('match_code', ''),
                    stage_name=s_name,
                    home_source=m.get('home_source', ''),
                    away_source=m.get('away_source', ''),
                ))
            knockout_stage_models.append(KnockoutStageProspect(
                stage_name=s_name,
                matches=m_list,
            ))

        total_teams_count = max(total_teams_count, audit.get('teams_count', 0))

        # 9. Evaluate Multi-Level Readiness Grade & Empty Prospect Rejection
        has_full_dates = bool(start_date_obj and end_date_obj)
        has_start_date = bool(start_date_obj)
        draw_ok = bool(audit.get('draw_completed') and len(group_models) >= 2 and teams_real)
        fixtures_ok = bool(audit.get('fixtures_completed') and (len(fixture_models) >= 4 or audit.get('scheduled_matchdays', 0) >= 4) and teams_real)

        # Empty Prospect Rejection Rule (missing start date AND no draw AND no fixtures AND 0 teams)
        if not has_start_date and not draw_ok and not fixtures_ok and total_teams_count == 0:
            p_name = prospect.name
            prospect.delete()
            return {
                'ok': False,
                'error': f"Djupscanning misslyckades: Turneringen '{p_name}' saknar datum, spelschema och lag. Turneringen avvisades.",
            }

        if has_full_dates and draw_ok and fixtures_ok and teams_real:
            final_grade = CompletenessGrade.GRADE_A
            final_reason = (f"Grad A (Redo): Djupskannad från källor ({', '.join(active_sources)}). "
                            f"({start_date_obj} – {end_date_obj}, {len(fixture_models)} matcher, "
                            f"{total_teams_count} lag i {len(group_models)} grupper verifierade).")
        elif has_start_date and (not draw_ok or not teams_real):
            final_grade = CompletenessGrade.GRADE_B
            draw_date_str = audit.get('draw_date') or ''
            draw_info = f" (Lottningsdatum: {draw_date_str})" if draw_date_str else " (Lag ej lottade ännu / Platshållare)"
            final_reason = f"Grad B (Väntar lottning): Turneringen startar {start_date_obj}, men deltagande lag/grupper är inte lottade ännu{draw_info}."
        else:
            final_grade = CompletenessGrade.GRADE_C
            date_info = f"Startdatum: {start_date_obj}" if start_date_obj else "Startdatum ej bekräftat ännu"
            final_reason = f"Grad C (Ej redo): {date_info}. Saknar spelschema, datum eller turneringsstruktur."

        # Logo URL resolution via EmblemScout
        from tournament.services.emblem_scout import EmblemScout
        official_web_url = prospect.official_source_url or audit.get('official_source_url') or ""
        discovered_emblem = EmblemScout.discover_official_emblem(
            tournament_name=prospect.name,
            official_url=official_web_url,
            wikidata_qid=wikidata.get('wikidata_qid')
        )
        final_logo_url = discovered_emblem or audit.get('logo_url') or prospect.logo_url or ""


        # Construct unified blueprint object
        unified_blueprint = TournamentProspectBlueprint(
            metadata=ProspectMetadata(
                name=prospect.name,
                master_event_code=prospect.master_event_code or prospect.name.lower().replace(' ', '-'),
                sport=prospect.sport or "Football",
                is_h2h_team_sport=True,
                organizer=prospect.organizer or "",
                host_country=prospect.host_country or audit.get('host_country') or "",
                start_date=str(start_date_obj) if start_date_obj else None,
                end_date=str(end_date_obj) if end_date_obj else None,
                draw_date=audit.get('draw_date') or None,
                draw_completed=bool(audit.get('draw_completed')),
                official_source_url=prospect.official_source_url or audit.get('official_source_url') or "",
                logo_url=final_logo_url,
                wikidata_qid=wikidata.get('wikidata_qid'),
            ),
            scouting_audit=ScoutingAudit(
                stage=ScoutingStage.DEEP,
                completeness_grade=final_grade,
                status=ProspectStatus(prospect.status) if prospect.status in ['NEW', 'WATCHLIST', 'CONVERTED', 'ARCHIVED'] else ProspectStatus.NEW,
                grade_reason=final_reason,
                draw_date=audit.get('draw_date') or None,
                draw_completed=bool(audit.get('draw_completed')),
                scan_timestamp=timezone.now().isoformat(),
                active_sources_used=active_sources,
            ),

            groups=group_models,
            fixtures=fixture_models,
            knockout_stages=knockout_stage_models,
            rules_and_points=RulesAndPointsProspect(
                official_rules_summary=audit.get('official_rules') or audit.get('advancement_rules') or "",
            )
        )


        # Update ScannedTournament DB instance
        legacy_dict = unified_blueprint.to_legacy_dict()
        prospect.completeness_grade = final_grade.value
        prospect.grade_reason = final_reason
        prospect.logo_url = final_logo_url
        if final_grade == CompletenessGrade.GRADE_A:
            prospect.status = 'READY'
        elif prospect.status not in ['WATCHLIST', 'CONVERTED', 'ARCHIVED']:
            prospect.status = 'NOT_READY'

        if prospect.status == 'WATCHLIST':
            from tournament.services.scout_service import resolve_rescan_date_for_prospect
            prospect.rescan_date = resolve_rescan_date_for_prospect(prospect)

        prospect.payload = legacy_dict
        prospect.tournament_blueprint = legacy_dict.get('tournament_blueprint', {})
        prospect.save()


        return {
            'ok': True,
            'grade': final_grade.value,
            'grade_reason': final_reason,
            'fixtures_count': len(fixture_models),
            'groups_count': len(group_models),
            'teams_count': total_teams_count,
            'draw_completed': draw_ok,
            'draw_date': audit.get('draw_date', ''),
            'scheduled_matchdays': audit.get('scheduled_matchdays', 0),
        }
