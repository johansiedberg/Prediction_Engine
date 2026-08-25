import json
import logging

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404

logger = logging.getLogger(__name__)
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_POST

from tournament.models import ScannedTournament
from tournament.services.scout_service import (
    convert_scanned_to_live_tournament, parse_and_save_scouted_json)
from tournament.views.auth import superuser_or_staff_required

EURO_2028_EUROPEAN_TEAMS = [
    'Spanien', 'Frankrike', 'England', 'Belgien', 'Nederländerna', 'Portugal',
    'Italien', 'Kroatien', 'Tyskland', 'Danmark', 'Turkiet', 'Sverige',
    'Tjeckien', 'Grekland', 'Skottland', 'Wales', 'Polen', 'Ungern',
    'Ukraina', 'Österrike', 'Schweiz', 'Serbien', 'Slovakien', 'Norge',
    'Georgien', 'Irland', 'Nordmakedonien', 'Montenegro', 'Albanien', 'Armenien',
    'Island', 'Bosnien och Hercegovina', 'Slovenien', 'Bulgarien', 'Finland', 'Nordirland',
    'Cypern', 'Gibraltar', 'Malta', 'Färöarna', 'Andorra', 'San Marino',
    'Azerbajdzjan', 'Kazakstan', 'Kosovo', 'Luxemburg', 'Lettland', 'Rumänien',
    'Liechtenstein', 'Moldavien', 'Belarus', 'Litauen', 'Estland', 'Israel'
]
WORLD_CUP_2026_NATIONAL_TEAMS = [
    'USA', 'Mexiko', 'Kanada', 'Brasilien', 'Argentina', 'Frankrike',
    'England', 'Spanien', 'Tyskland', 'Belgien', 'Nederländerna', 'Portugal',
    'Italien', 'Kroatien', 'Uruguay', 'Japan', 'Sydkorea', 'Marocko',
    'Senegal', 'Australien', 'Colombia', 'Ecuador', 'Chile', 'Peru',
    'Nigeria', 'Elfenbenskusten', 'Ghana', 'Algeriet', 'Egypten', 'Kamerun',
    'Iran', 'Saudiarabien', 'Qatar', 'Irak', 'Uzbekistan', 'Förenade Arabemiraten',
    'Costa Rica', 'Jamaica', 'Panama', 'Honduras', 'Nya Zeeland', 'Tunisien'
]


# --- AI Tournament Scout Endpoints ---

@superuser_or_staff_required
@require_POST
def scout_import_json_view(request: HttpRequest) -> JsonResponse:
    """Imports or updates a ScannedTournament from JSON payload."""
    try:
        raw_data = request.POST.get('json_data')
        if not raw_data and request.body:
            try:
                body_json = json.loads(request.body.decode('utf-8'))
                raw_data = body_json.get('json_data') if isinstance(body_json, dict) else request.body.decode('utf-8')
            except Exception:
                raw_data = request.body.decode('utf-8')

        if not raw_data:
            return JsonResponse({'status': 'error', 'message': 'Ingen JSON-data mottogs.'}, status=400)

        payload = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        scanned_obj, created, error = parse_and_save_scouted_json(payload)

        if error:
            return JsonResponse({'status': 'error', 'message': error}, status=400)

        verb = 'importerades som nytt prospekt' if created else 'uppdaterades'
        return JsonResponse({
            'status': 'success',
            'message': f'"{scanned_obj.name}" {verb} ({scanned_obj.completeness_grade})!',
            'prospect': {
                'id': scanned_obj.id,
                'name': scanned_obj.name,
                'grade': scanned_obj.completeness_grade,
                'status': scanned_obj.status,
            }
        })
    except json.JSONDecodeError as jde:
        return JsonResponse({'status': 'error', 'message': f'Ogiltig JSON: {str(jde)}'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Ett fel uppstod: {str(e)}'}, status=500)


@superuser_or_staff_required
@require_POST
def scout_search_specific_view(request: HttpRequest) -> JsonResponse:
    """
    Stage 1 Shallow Search / Ingestion: Searches the web, Wikipedia, and Google/Gemini
    for a specific tournament by name or URL, extracting metadata and creating/updating
    a ScannedTournament prospect.
    """
    query = ""
    try:
        query = (request.POST.get('tournament_query') or request.POST.get('query') or request.POST.get('wikipedia_url') or '').strip()
        if not query and request.body:
            try:
                b_data = json.loads(request.body.decode('utf-8'))
                if isinstance(b_data, dict):
                    query = (b_data.get('tournament_query') or b_data.get('query') or b_data.get('wikipedia_url') or '').strip()
            except Exception:
                pass

        if not query:
            return JsonResponse({'status': 'error', 'message': 'Ange ett turneringsnamn eller en webbadress att söka efter.'}, status=400)

        import datetime
        import urllib.parse

        from tournament.services.emblem_scout import EmblemScout
        from tournament.services.gemini_scout_service import GeminiScoutService
        from tournament.services.scout_service import \
            parse_and_save_scouted_json
        from tournament.services.wikipedia_scout import WikipediaScout

        wiki_scout = WikipediaScout()
        is_url = query.startswith(('http://', 'https://'))
        resolved_url = query if is_url else ''
        page_title = ''

        if is_url:
            page_title = wiki_scout.get_article_title_from_url(query)
            if not page_title:
                page_title = wiki_scout.search_wikipedia_article(query)
        else:
            page_title = wiki_scout.search_wikipedia_article(query)

        infobox = wiki_scout.audit_infobox_only(page_title) if page_title else None

        title = (infobox.get('page_title') if infobox else page_title) or query
        if not resolved_url and infobox and infobox.get('wiki_url'):
            resolved_url = infobox['wiki_url']
        elif not resolved_url and page_title:
            resolved_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(page_title.replace(' ', '_'))}"

        # Gemini General Intelligence fallback/enrichment for name, sport, host
        gemini_meta = {}
        if GeminiScoutService.is_available():
            try:
                gemini_meta = GeminiScoutService.scout_general_details(tournament_name=title) or {}
            except Exception:
                pass

        sport = gemini_meta.get('sport') or 'Championship'
        host_country = (infobox.get('host_country') if infobox else None) or gemini_meta.get('host_country') or 'Värdnation'
        start_date = (infobox.get('start_date') if infobox else None) or gemini_meta.get('start_date') or ''
        end_date = (infobox.get('end_date') if infobox else None) or gemini_meta.get('end_date') or ''
        logo_url = gemini_meta.get('logo_url') or EmblemScout.discover_official_emblem(title, official_url=resolved_url)

        from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
        if start_date:
            start_date = LLMWikipediaScout._parse_date_string(start_date)
        if end_date:
            end_date = LLMWikipediaScout._parse_date_string(end_date)

        today_date = datetime.date.today()
        min_upcoming_date = today_date + datetime.timedelta(days=30)
        
        # Enforce 30-day runway rule on specific search import
        if start_date:
            try:
                s_date_obj = datetime.date.fromisoformat(start_date)
                if s_date_obj < min_upcoming_date:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Turneringen "{title}" avvisades eftersom startdatumet ({s_date_obj}) är i det förflutna eller infaller inom mindre än 30 dagar (tröskel: {min_upcoming_date}).'
                    }, status=400)
            except Exception:
                pass

        master_code = title.lower().replace(' ', '-').replace("'", '').replace('/', '-')[:100]
        final_grade = 'GRADE_C'
        grade_reason_str = f"Grad C (Inväntar djupscanning): Prospektet hittades via webbsökning för '{title}'. Klicka 'Djupscanna' för fullständig analys."

        next_rescan_date = today_date + datetime.timedelta(days=7)

        scout_payload = {
            "scouting_audit": {
                "scan_timestamp": datetime.datetime.now().isoformat(),
                "scouting_stage": "SHALLOW",
                "completeness_grade": final_grade,
                "grade_reason": grade_reason_str,
                "official_source_url": resolved_url,
                "wikipedia_url": resolved_url,
                "wikipedia_title": page_title or title,
                "is_compatible_sport": True,
                "draw_date": "",
                "next_rescan_date": next_rescan_date.isoformat(),
                "advancement_rules": "",
                "wikipedia_audit": None,
            },
            "master_event": {
                "name": title,
                "code": master_code,
                "sport": sport,
                "organizer": gemini_meta.get('organizer') or "International Federation",
                "host_country": host_country,
                "official_source_url": resolved_url,
                "wikipedia_url": resolved_url,
                "start_date": start_date,
                "end_date": end_date,
                "logo_url": logo_url,
            },
            "tournament_config": {
                "name": title,
                "total_teams": (infobox.get('teams_count') if infobox else None) or 16,
                "knockout_stages": ["Quarterfinals", "Semifinals", "Final"],
            },
            "groups": [],
            "fixtures_sample": [],
            "raw_allsportdb": {"source": "Web / Specific Search", "wiki_url": resolved_url},
        }

        scanned_obj, created, error = parse_and_save_scouted_json(scout_payload)
        if error:
            return JsonResponse({'status': 'error', 'message': error}, status=400)

        if logo_url and not scanned_obj.logo_url:
            scanned_obj.logo_url = logo_url
            scanned_obj.save(update_fields=['logo_url'])

        verb = 'hittades och lades till' if created else 'uppdaterades'
        return JsonResponse({
            'status': 'success',
            'message': f'Turneringen "{scanned_obj.name}" {verb}! Klicka "Djupscanna" för fullständig analys.',
            'prospect': {
                'id': scanned_obj.id,
                'name': scanned_obj.name,
                'grade': scanned_obj.completeness_grade,
                'status': scanned_obj.status,
                'sport': scanned_obj.sport,
                'logo_url': scanned_obj.logo_url,
            }
        })
    except Exception as e:
        logger.error(f"Error in scout_search_specific_view for query '{query}': {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': f'Ett fel uppstod vid sökningen: {str(e)}'}, status=500)


@superuser_or_staff_required
@require_POST
def scout_import_wikipedia_view(request: HttpRequest) -> JsonResponse:
    """Legacy alias routing to scout_search_specific_view."""
    return scout_search_specific_view(request)


@superuser_or_staff_required
@require_POST
def scout_convert_view(request: HttpRequest, prospect_id: int) -> JsonResponse:

    """Converts a ScannedTournament prospect into a full live tournament."""
    try:
        is_active = request.POST.get('is_active') in ['true', '1', 'on']
        
        # Optional custom point system payload
        custom_pts = None
        custom_pts_str = request.POST.get('custom_point_system')
        if custom_pts_str:
            try:
                custom_pts = json.loads(custom_pts_str)
            except Exception:
                pass

        tournament, error = convert_scanned_to_live_tournament(
            scanned_id=prospect_id,
            admin_user=request.user,
            is_active=is_active,
            custom_point_system=custom_pts
        )

        if error:
            return JsonResponse({'status': 'error', 'message': error}, status=400)

        return JsonResponse({
            'status': 'success',
            'message': f'Turneringen "{tournament.name}" har skapats och finns nu i Engine Admin!',
            'tournament_id': tournament.id,
            'tournament_name': tournament.name,
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Kunde inte konvertera prospekt: {str(e)}'}, status=500)


@superuser_or_staff_required
@require_POST
def scout_update_status_view(request: HttpRequest, prospect_id: int) -> JsonResponse:
    """Updates status for a ScannedTournament (e.g. WATCHLIST, ARCHIVED, NEW)."""
    prospect = get_object_or_404(ScannedTournament, id=prospect_id)
    new_status = request.POST.get('status', '').upper().strip()

    valid_statuses = ['NEW', 'WATCHLIST', 'CONVERTED', 'ARCHIVED']
    if new_status not in valid_statuses:
        return JsonResponse({'status': 'error', 'message': f'Ogiltig status "{new_status}".'}, status=400)

    prospect.status = new_status
    if new_status == 'WATCHLIST':
        from tournament.services.scout_service import \
            resolve_rescan_date_for_prospect
        res_date = resolve_rescan_date_for_prospect(prospect)
        if res_date:
            payload = prospect.payload or {}
            scouting_audit = payload.get('scouting_audit', {})
            scouting_audit['next_rescan_date'] = res_date.strftime('%Y-%m-%d')
            payload['scouting_audit'] = scouting_audit
            prospect.payload = payload
    prospect.save()

    return JsonResponse({
        'status': 'success',
        'message': f'Status för "{prospect.name}" ändrades till {new_status}.',
        'prospect_id': prospect.id,
        'new_status': prospect.status,
        'rescan_date': prospect.rescan_date.strftime('%Y-%m-%d') if prospect.rescan_date else None
    })


@superuser_or_staff_required
@require_POST
def scout_delete_view(request: HttpRequest, prospect_id: int) -> JsonResponse:
    """Deletes a ScannedTournament prospect from staging."""
    prospect = get_object_or_404(ScannedTournament, id=prospect_id)
    name = prospect.name
    prospect.delete()

    return JsonResponse({
        'status': 'success',
        'message': f'Prospektet "{name}" raderades från scout-listan.'
    })


@superuser_or_staff_required
def scout_prospect_json_view(request: HttpRequest, prospect_id: int) -> JsonResponse:
    """Returns raw payload JSON for review modal."""
    prospect = get_object_or_404(ScannedTournament, id=prospect_id)
    return JsonResponse({
        'status': 'success',
        'prospect': {
            'id': prospect.id,
            'name': prospect.name,
            'sport': prospect.sport,
            'organizer': prospect.organizer,
            'host_country': prospect.host_country,
            'start_date': str(prospect.start_date) if prospect.start_date else '',
            'end_date': str(prospect.end_date) if prospect.end_date else '',
            'grade': prospect.completeness_grade,
            'grade_reason': prospect.grade_reason,
            'official_source_url': prospect.official_source_url or prospect.payload.get('master_event', {}).get('official_source_url') or '',
            'status': prospect.status,
            'payload': prospect.payload,
        }
    })


@superuser_or_staff_required
@require_POST
def scout_scrape_web_view(request: HttpRequest) -> JsonResponse:
    """Triggers Phase 1 WebCrawl / Ingestion Agent to discover upcoming tournaments."""
    try:
        custom_query = request.POST.get('query', '').strip()
        from tournament.services.web_crawl_agent import WebCrawlAgent
        agent = WebCrawlAgent()
        created_cnt, updated_cnt, prospects = agent.discover_and_ingest(custom_query)
        total_found = len(prospects)

        api_key = getattr(settings, 'ALLSPORTDB_API_KEY', '')
        if total_found == 0 and not api_key:
            return JsonResponse({
                'status': 'error',
                'message': 'Ingen giltig AllSportDB API-nyckel konfigurerad. Ange ALLSPORTDB_API_KEY i inställningarna eller använd "Importera via Wikipedia".'
            }, status=400)

        return JsonResponse({
            'status': 'success',
            'message': f'Webbscanning slutförd! Hittade {total_found} prospekt ({created_cnt} nya, {updated_cnt} uppdaterade).',
            'created_count': created_cnt,
            'updated_count': updated_cnt,
            'total_count': total_found
        })

    except Exception as e:
        logger.error(f"Error in scout_scrape_web_view: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': f'Fel under webbscanning: {str(e)}'
        }, status=500)


def _run_deep_scan_on_prospect(prospect, wiki_scout=None, off_verifier=None):
    """
    Shared Stage 2 Deep Scan Engine.
    Delegates to ModularDeepScout to populate the unified TournamentProspectBlueprint schema.
    """
    from tournament.services.modular_deep_scout import ModularDeepScout
    scout = ModularDeepScout()
    if wiki_scout is not None:
        scout.wiki_scout = wiki_scout
    if off_verifier is not None:
        scout.off_verifier = off_verifier
    return scout.deep_scan_prospect(prospect)


@superuser_or_staff_required
@require_POST
def scout_deep_scan_one_view(request: HttpRequest, prospect_id: int) -> JsonResponse:
    """
    Stage 2–4 Deep Scout for a single prospect.
    Delegates to _run_deep_scan_on_prospect() and returns a JSON response.
    Called by the per-card '🔬 Djupscanna' button in the Engine Admin Scout UI.
    """
    from tournament.services.official_regulations_verifier import \
        OfficialRegulationsVerifier
    from tournament.services.wikipedia_scout import WikipediaScout

    prospect = get_object_or_404(ScannedTournament, id=prospect_id)

    try:
        result = _run_deep_scan_on_prospect(
            prospect,
            WikipediaScout(),
            OfficialRegulationsVerifier(),
        )
        if not result['ok']:
            if any(k in result.get('error', '') for k in ['avslutats', 'avvisades', 'passerats', 'mindre än 30 dagar', 'pågående', 'avslutad', 'misslyckades', 'avbröts', 'förflutna']):
                return JsonResponse({'status': 'deleted', 'message': result['error']}, status=200)
            return JsonResponse({'status': 'error', 'message': result['error']}, status=400)

        if result.get('merged_into'):
            return JsonResponse({
                'status': 'merged',
                'message': f"Sammanfogad med '{result.get('target_name', '')}' ({result.get('grade', 'GRADE_A')})",
                'grade': result.get('grade', 'GRADE_A'),
                'grade_reason': result.get('grade_reason', ''),
                'fixtures_count': result.get('fixtures_count', 0),
                'groups_count': result.get('groups_count', 0),
                'draw_completed': result.get('draw_completed', True),
                'draw_date': result.get('draw_date', ''),
            }, status=200)

        prospect.save()
        
        # Merge duplicate prospects sharing the exact same Wikipedia link
        from tournament.services.scout_service import \
            merge_duplicate_scanned_tournaments_by_wikipedia
        merge_duplicate_scanned_tournaments_by_wikipedia()

        return JsonResponse({
            'status':              'success',
            'message':             f'Djupscanning slutförd! "{prospect.name}" → {result["grade"]}',
            'grade':               result['grade'],
            'grade_reason':        result['grade_reason'],
            'fixtures_count':      result['fixtures_count'],
            'groups_count':        result['groups_count'],
            'teams_count':         result['teams_count'],
            'draw_completed':      result['draw_completed'],
            'draw_date':           result['draw_date'],
            'scheduled_matchdays': result['scheduled_matchdays'],
        })

    except Exception as e:
        logger.error(f"Error in scout_deep_scan_one_view (prospect #{prospect_id}): {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': f'Fel under djupscanning: {str(e)}'}, status=500)


@superuser_or_staff_required
@require_POST
def scout_update_official_url_view(request: HttpRequest, prospect_id: int) -> JsonResponse:
    """
    Manually sets or updates the official source URL for a scanned prospect card.
    Re-runs OfficialRegulationsVerifier on the URL and updates prospect payload in-place.
    """
    from tournament.services.official_regulations_verifier import \
        OfficialRegulationsVerifier
    
    prospect = get_object_or_404(ScannedTournament, id=prospect_id)
    official_url = request.POST.get('official_url', '').strip()
    
    off_verifier = OfficialRegulationsVerifier()
    official_audit = off_verifier.verify_official_regulations(official_url, prospect.name) if official_url else None
    
    prospect.official_source_url = official_url
    
    payload = prospect.payload or {}
    scouting_audit = payload.setdefault('scouting_audit', {})
    scouting_audit['official_source_url'] = official_url
    if official_audit:
        scouting_audit['official_site_audit'] = official_audit
        
    master_event = payload.setdefault('master_event', {})
    master_event['official_source_url'] = official_url
    
    prospect.payload = payload
    prospect.save()
    
    return JsonResponse({
        'status': 'success',
        'message': f'Officiell webbadress för "{prospect.name}" har sparats och verifierats!',
        'official_url': official_url,
        'official_site_audit': official_audit,
    })


@superuser_or_staff_required
@require_POST
def scout_update_official_rules_view(request: HttpRequest, prospect_id: int) -> JsonResponse:
    """
    Updates official rules text and regulations URL for a scanned prospect card or live tournament.
    """
    prospect = get_object_or_404(ScannedTournament, id=prospect_id)
    official_rules = request.POST.get('official_rules', '').strip()
    official_url = request.POST.get('official_url', '').strip()

    prospect.official_rules = official_rules
    if official_url:
        prospect.official_source_url = official_url

    payload = prospect.payload or {}
    scouting_audit = payload.setdefault('scouting_audit', {})
    scouting_audit['official_rules'] = official_rules
    if official_url:
        scouting_audit['official_source_url'] = official_url
    prospect.payload = payload
    prospect.save()

    # Also update converted tournament if already converted
    if prospect.converted_tournament:
        tour = prospect.converted_tournament
        tour.official_rules = official_rules
        if official_url:
            tour.official_regulations_url = official_url
        tour.save()

    return JsonResponse({
        'status': 'success',
        'message': f'Officiella föreskrifter & reglemente för "{prospect.name}" har sparats!',
        'official_rules': prospect.official_rules,
        'official_url': prospect.official_source_url,
    })


@superuser_or_staff_required
@require_POST
def scout_clear_list_view(request: HttpRequest) -> JsonResponse:
    """Clears scanned tournament prospects from the scout list."""
    try:
        clear_all = request.POST.get('clear_all') in ['1', 'true']
        with transaction.atomic():
            if clear_all:
                deleted_cnt, _ = ScannedTournament.objects.all().delete()
            else:
                deleted_cnt, _ = ScannedTournament.objects.exclude(status='CONVERTED').delete()
        return JsonResponse({
            'status': 'success',
            'message': f'Rensade {deleted_cnt} prospekt från scout-listan.'
        })
    except Exception as e:
        logger.error(f"Fel i scout_clear_list_view: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': f'Kunde inte rensa listan: {str(e)}'
        }, status=500)


@superuser_or_staff_required
@require_POST
def scout_refresh_all_view(request: HttpRequest) -> JsonResponse:
    """
    Bulk Stage 2–4 Deep Scout for ALL non-converted prospects.
    Delegates each prospect to _run_deep_scan_on_prospect() — the same full
    pipeline as the per-card '🔬 Djupscanna' button — so that grades,
    fixtures, groups, official-site audits, scouting_stage, and rescan dates
    are all updated identically.
    """
    from tournament.services.official_regulations_verifier import \
        OfficialRegulationsVerifier
    from tournament.services.wikipedia_scout import WikipediaScout

    wiki_scout   = WikipediaScout()
    off_verifier = OfficialRegulationsVerifier()
    prospects    = ScannedTournament.objects.exclude(status='CONVERTED')

    refreshed_count = 0
    skipped_count   = 0
    results         = []

    for prospect in prospects:
        try:
            result = _run_deep_scan_on_prospect(prospect, wiki_scout, off_verifier)
            if result['ok']:
                prospect.save()
                refreshed_count += 1
                results.append({
                    'id':    prospect.id,
                    'name':  prospect.name,
                    'grade': result['grade'],
                    'ok':    True,
                })
            else:
                skipped_count += 1
                results.append({
                    'id':    prospect.id,
                    'name':  prospect.name,
                    'ok':    False,
                    'error': result['error'],
                })
                logger.warning(f"scout_refresh_all: skipped prospect #{prospect.id} '{prospect.name}': {result['error']}")
        except Exception as e:
            if prospect.status == 'NEW':
                prospect.status = 'NOT_READY'
                prospect.save()
            skipped_count += 1
            results.append({'id': prospect.id, 'name': prospect.name, 'ok': False, 'error': str(e)})
            logger.error(f"scout_refresh_all: error on prospect #{prospect.id}: {e}", exc_info=True)

    return JsonResponse({
        'status':          'success',
        'message':         f'Djupskannade {refreshed_count} turneringar ({skipped_count} hoppades över).',
        'refreshed_count': refreshed_count,
        'skipped_count':   skipped_count,
        'results':         results,
    })

