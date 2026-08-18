import datetime
import logging
import re
import requests
from bs4 import BeautifulSoup
from django.db import transaction, models

from django.utils import timezone
from django.contrib.auth.models import User
from tournament.models import (
    ScannedTournament, MasterEvent, Tournament, PointSystem, Group, Team,
    KnockoutStage, Match, Sidebet, COUNTRY_CODE_MAP, Sport, TournamentEvent
)
from tournament.services.allsportdb_client import AllSportDBClient
from tournament.services.tournament_filter import (
    is_h2h_team_sport, is_championship_or_cup_format, evaluate_event_grade
)
from tournament.services.wikipedia_scout import WikipediaScout
from tournament.services.official_regulations_verifier import OfficialRegulationsVerifier

logger = logging.getLogger(__name__)



def parse_and_save_scouted_json(payload):
    """
    Validates and ingests a JSON payload from Gemini Tournament Scout.
    Returns (scanned_instance, created_boolean, error_string_if_any).
    """
    if not isinstance(payload, dict):
        return None, False, "Payload måste vara ett giltigt JSON-objekt."

    master_event_data = payload.get('master_event', {})
    tournament_config = payload.get('tournament_config', {})
    scouting_audit = payload.get('scouting_audit', {})

    name = tournament_config.get('name') or master_event_data.get('name')
    if not name:
        return None, False, "Saknar turneringsnamn ('name' under master_event eller tournament_config)."

    master_code = master_event_data.get('code') or name.lower().replace(' ', '-').replace("'", '')
    sport = master_event_data.get('sport', 'Football')
    organizer = master_event_data.get('organizer', '')
    host_country = master_event_data.get('host_country', '')
    
    start_date_str = master_event_data.get('start_date')
    end_date_str = master_event_data.get('end_date')
    
    start_date = None
    if start_date_str:
        try:
            start_date = datetime.date.fromisoformat(start_date_str)
        except Exception:
            pass

    end_date = None
    if end_date_str:
        try:
            end_date = datetime.date.fromisoformat(end_date_str)
        except Exception:
            pass

    grade = scouting_audit.get('completeness_grade', 'GRADE_A')
    if grade not in ['GRADE_A', 'GRADE_B', 'GRADE_C', 'GRADE_D']:
        grade = 'GRADE_A'

    grade_reason = scouting_audit.get('grade_reason') or ''
    if not grade_reason:
        missing = scouting_audit.get('missing_items', [])
        if missing:
            grade_reason = f"Gradering {grade}: Saknar följande uppgifter: " + ", ".join(missing)
        elif grade == 'GRADE_A':
            grade_reason = "100% redo för publicering. Lottning genomförd, alla lag namngivna och spelschema bekräftat."
        elif grade == 'GRADE_B':
            grade_reason = "Nästan redo. Lottning och datum klara, men vissa avslagstider eller playoff-platser är preliminära."
        elif grade == 'GRADE_C':
            grade_reason = "Bevakningslista. Turneringen är bekräftad men lottning eller kvalificering är ej slutförd."
        elif grade == 'GRADE_D':
            grade_reason = "Ej kompatibel sport eller avslutad turnering."

    official_source_url = (
        master_event_data.get('official_source_url') or 
        scouting_audit.get('official_source_url') or 
        payload.get('official_source_url') or ''
    )

    official_rules = (
        scouting_audit.get('official_rules') or
        scouting_audit.get('advancement_rules') or
        payload.get('official_rules') or ''
    )

    # Check if existing prospect with same code or name
    scanned_obj = ScannedTournament.objects.filter(master_event_code=master_code).first()
    if not scanned_obj:
        scanned_obj = ScannedTournament.objects.filter(name=name).first()

    created = False
    if scanned_obj:
        scanned_obj.name = name
        scanned_obj.master_event_code = master_code
        scanned_obj.sport = sport
        scanned_obj.organizer = organizer
        scanned_obj.host_country = host_country
        scanned_obj.start_date = start_date
        scanned_obj.end_date = end_date
        scanned_obj.completeness_grade = grade
        scanned_obj.grade_reason = grade_reason
        if official_source_url:
            scanned_obj.official_source_url = official_source_url
        if official_rules:
            scanned_obj.official_rules = official_rules
        scanned_obj.payload = payload
        # Preserve status if existing (e.g. ARCHIVED or WATCHLIST stays preserved on rescans)
        scanned_obj.save()
    else:
        scanned_obj = ScannedTournament.objects.create(
            name=name,
            master_event_code=master_code,
            sport=sport,
            organizer=organizer,
            host_country=host_country,
            start_date=start_date,
            end_date=end_date,
            completeness_grade=grade,
            grade_reason=grade_reason,
            official_source_url=official_source_url,
            official_rules=official_rules,
            status='NEW',
            payload=payload
        )
        created = True

    return scanned_obj, created, None


def fetch_and_ingest_allsportdb_tournaments(months_ahead=12, dry_run=False, sync_scout=True, start_date=None, end_date=None):
    """
    Fetches upcoming sports events from AllSportDB API (v3), strictly filters for H2H team sports
    and championship/cup formats, evaluates Grade A/B/C ratings, and saves them to Sport,
    TournamentEvent, and ScannedTournament models.

    Date Rule:
    - Default from: Today's date + 2 months (to target coming events)
    - Default to: End of +1 year (December 31st of next year)
    """
    client = AllSportDBClient()

    # 1. Fetch & Store Sports
    raw_sports = client.get_sports()
    sports_map = {}
    
    for idx, s_item in enumerate(raw_sports):
        if not isinstance(s_item, dict):
            continue
        ext_id = s_item.get('id') or s_item.get('sportId') or (idx + 1)
        name = s_item.get('name') or s_item.get('sportName') or ''
        if not name:
            continue
        
        is_h2h = is_h2h_team_sport(name)
        if not dry_run:
            sport_obj, _ = Sport.objects.update_or_create(
                external_id=ext_id,
                defaults={'name': name, 'is_h2h_team_sport': is_h2h}
            )
        else:
            sport_obj = Sport(external_id=ext_id, name=name, is_h2h_team_sport=is_h2h)
        
        sports_map[ext_id] = sport_obj
        sports_map[name.lower()] = sport_obj

    # 2. Fetch Calendar Events (From: today + 1 month, To: end of +1 year)
    today = timezone.now().date()
    if not start_date:
        start_date = today + datetime.timedelta(days=30)
    if not end_date:
        end_date = datetime.date(today.year + 1, 12, 31)

    raw_events = client.get_calendar(start_date=start_date, end_date=end_date)




    
    created_count = 0
    updated_count = 0
    prospects_list = []
    
    for idx, ev in enumerate(raw_events):
        if not isinstance(ev, dict):
            continue
            
        ext_event_id = ev.get('id') or ev.get('eventId') or (10000 + idx)
        title = ev.get('title') or ev.get('name') or ev.get('eventName') or ''
        if not title:
            continue

        # Format Filtering (Championships & Cups Only)
        cat_name = ev.get('category') or ev.get('sportName') or ''
        is_championship, fmt_reason = is_championship_or_cup_format(title, cat_name)
        if not is_championship:
            continue

        # Match Sport
        sport_id = ev.get('sportId') or ev.get('sport_id')
        sport_name = ev.get('sport') or ev.get('sportName') or cat_name or 'Football'
        sport_obj = None
        if sport_id in sports_map:
            sport_obj = sports_map[sport_id]
        elif str(sport_name).lower() in sports_map:
            sport_obj = sports_map[str(sport_name).lower()]
        
        if not sport_obj and not dry_run:
            sport_obj, _ = Sport.objects.get_or_create(
                external_id=sport_id or (5000 + idx),
                defaults={'name': str(sport_name), 'is_h2h_team_sport': is_h2h_team_sport(str(sport_name))}
            )
        elif not sport_obj:
            sport_obj = Sport(external_id=5000+idx, name=str(sport_name), is_h2h_team_sport=is_h2h_team_sport(str(sport_name)))

        # Check H2H Team Sport requirement
        is_h2h = sport_obj.is_h2h_team_sport

        # Extract dates & metadata
        start_date_val = None
        end_date_val = None
        raw_start = ev.get('dateFrom') or ev.get('startDate')
        raw_end = ev.get('dateTo') or ev.get('endDate')
        if raw_start:
            try: start_date_val = datetime.date.fromisoformat(str(raw_start)[:10])
            except Exception: pass
        if raw_end:
            try: end_date_val = datetime.date.fromisoformat(str(raw_end)[:10])
            except Exception: pass

        loc_data = ev.get('location')
        country = ev.get('country') or ev.get('hostCountry') or ''
        city = ev.get('city') or ''
        if isinstance(loc_data, list) and len(loc_data) > 0 and isinstance(loc_data[0], dict):
            if not country:
                country = loc_data[0].get('name') or ''
            sub_locs = loc_data[0].get('locations') or []
            if isinstance(sub_locs, list) and len(sub_locs) > 0 and isinstance(sub_locs[0], dict):
                if not city:
                    city = sub_locs[0].get('name') or ''
        
        organizer = ev.get('organizer') or ev.get('federation') or ev.get('continent') or ''
        official_website = ev.get('webUrl') or ev.get('officialWebsite') or ev.get('url') or ev.get('website') or ''
        
        # Fallback regulations search URL
        official_regulations = client.fetch_official_regulations_url(title, official_website)


        # Grade Evaluation (Grade A, B, C)
        grade, grade_reason = evaluate_event_grade(ev, is_h2h)

        if dry_run:
            prospects_list.append({
                'title': title,
                'sport': sport_obj.name,
                'is_h2h': is_h2h,
                'grade': grade,
                'grade_reason': grade_reason
            })
            continue

        # Save TournamentEvent
        event_obj, created = TournamentEvent.objects.update_or_create(
            external_id=ext_event_id,
            defaults={
                'sport': sport_obj,
                'title': title,
                'start_date': start_date_val,
                'end_date': end_date_val,
                'country': country,
                'city': city,
                'organizer': organizer,
                'official_website': official_website,
                'official_regulations_url': official_regulations,
                'format_category': 'Championship/Cup',
                'completeness_grade': grade,
                'grade_reason': grade_reason,
                'payload': ev
            }
        )

        if created: created_count += 1
        else: updated_count += 1

        today = datetime.date.today()
        is_upcoming = bool(start_date_val and start_date_val > today)

        # Sync to ScannedTournament prospect ONLY if H2H team sport AND strictly upcoming (start_date > today)
        if sync_scout and is_h2h and is_upcoming:
            master_code = title.lower().replace(' ', '-').replace("'", '').replace('/', '-')[:100]
            host_str = f"{country} ({city})".strip(' ()')

            # --- Stage 1: Shallow Ingestion ---
            # Only find the Wikipedia link and parse the infobox.
            # Full audit_tournament_page() is deferred to on-demand Stage 2 (Djupscanna button).
            wiki_scout = WikipediaScout()

            wiki_title = wiki_scout.get_article_title_from_url(ev.get('wikiUrl'))
            if not wiki_title:
                wiki_title = wiki_scout.search_wikipedia_article(title, ev.get('year'))

            infobox = wiki_scout.audit_infobox_only(wiki_title) if wiki_title else None

            wiki_url = (infobox.get('wiki_url') if infobox
                        else (ev.get('wikiUrl') or ''))

            final_grade  = 'GRADE_C'
            final_reason = f"Grad C (Inväntar djupscanning): Hittad via AllSportDB. Klicka 'Djupscanna' för fullständig Wikipedia-analys."

            today_date       = datetime.date.today()
            next_rescan_date = today_date + datetime.timedelta(days=7)

            scout_payload = {
                "scouting_audit": {
                    "scan_timestamp":    datetime.datetime.now().isoformat(),
                    "scouting_stage":    "SHALLOW",
                    "completeness_grade": final_grade,
                    "grade_reason":      final_reason,
                    "official_source_url": official_website or official_regulations,
                    "wikipedia_url":     wiki_url,
                    "wikipedia_title":   wiki_title or "",
                    "is_compatible_sport": is_h2h,
                    "draw_date":         "",
                    "next_rescan_date":  next_rescan_date.isoformat(),
                    "advancement_rules": "",
                    "official_site_audit": None,
                    "wikipedia_audit":   None,
                },
                "master_event": {
                    "name":               title,
                    "code":               master_code,
                    "sport":              sport_obj.name,
                    "organizer":          organizer,
                    "host_country":       (infobox.get('host_country') if infobox and infobox.get('host_country') else host_str),
                    "official_source_url": official_website or official_regulations,
                    "wikipedia_url":      wiki_url,
                    "start_date":         str(start_date_val) if start_date_val else "",
                    "end_date":           str(end_date_val) if end_date_val else "",
                },
                "tournament_config": {
                    "name":           title,
                    "total_teams":    (infobox.get('teams_count') if infobox and infobox.get('teams_count') else (len(ev.get('teams', [])) or 16)),
                    "knockout_stages": ["Quarterfinals", "Semifinals", "Final"],
                },
                "groups":          [],
                "fixtures_sample": [],
                "raw_allsportdb":  ev,
            }


            scanned_obj, s_created, _ = parse_and_save_scouted_json(scout_payload)
            if scanned_obj:
                event_obj.scanned_prospect = scanned_obj
                event_obj.save(update_fields=['scanned_prospect'])
                prospects_list.append(scanned_obj)


    return created_count, updated_count, prospects_list


def fetch_and_ingest_wikipedia_year_events(years=None, sync_scout=True):
    """
    Crawls Wikipedia's annual sports overview pages (e.g. https://en.wikipedia.org/wiki/2026_in_sports)
    for target years matching the scan time horizon.
    
    Filters for H2H team sports & championship/cup formats, evaluates initial shallow metadata,
    and ingests new unique prospects into ScannedTournament.
    """
    if not years:
        today_year = datetime.date.today().year
        years = [today_year, today_year + 1]

    created_cnt = 0
    updated_cnt = 0
    prospects_list = []
    
    wiki_scout = WikipediaScout()
    headers = {'User-Agent': 'PredictionEngineScout/1.0 (https://predictionengine.app; info@predictionengine.app)'}

    for year in years:
        url = f"https://en.wikipedia.org/api/rest_v1/page/html/{year}_in_sports"
        try:
            res = requests.get(url, headers=headers, timeout=12)
            if res.status_code != 200:
                continue
            soup = BeautifulSoup(res.content, 'html.parser')
        except Exception as e:
            logger.warning(f"Wikipedia {year}_in_sports fetch error: {e}")
            continue

        seen_pages = set()
        for a in soup.find_all('a'):
            href = a.get('href', '')
            title = (a.get('title') or a.get_text(strip=True)).strip()
            if not href.startswith('./') and not href.startswith('/wiki/'):
                continue
            
            wiki_page = href.replace('./', '').replace('/wiki/', '')
            if wiki_page in seen_pages or not title:
                continue

            if any(wiki_page.startswith(p) for p in ['File:', 'Help:', 'Special:', 'Wikipedia:', 'Portal:', 'Category:', 'Template:']):
                continue

            is_champ, fmt_reason = is_championship_or_cup_format(title)
            if not is_champ:
                continue

            is_h2h = is_h2h_team_sport(title)
            if not is_h2h:
                continue

            seen_pages.add(wiki_page)

            # Check if prospect already exists by master_event_code or name
            master_code = title.lower().replace(' ', '-').replace("'", '').replace('/', '-')[:100]

            existing = ScannedTournament.objects.filter(
                models.Q(master_event_code=master_code) |
                models.Q(name__iexact=title)
            ).first()

            if existing:
                continue

            wiki_url = f"https://en.wikipedia.org/wiki/{wiki_page}"

            # Shallow infobox audit for dates & host country
            infobox = wiki_scout.audit_infobox_only(wiki_page)
            
            start_date_str = ""
            end_date_str = ""
            host_country = (infobox.get('host_country') if infobox else "") or ""
            
            # Start/End date parsing
            start_date_val = None
            if infobox and infobox.get('start_date'):
                try:
                    start_date_val = datetime.date.fromisoformat(str(infobox['start_date'])[:10])
                    start_date_str = str(start_date_val)
                except Exception:
                    pass

            # Skip past events
            today = datetime.date.today()
            if start_date_val and start_date_val <= today:
                continue

            sport_name = (infobox.get('sport') if infobox and infobox.get('sport') else "") or "Sports"
            teams_count = (infobox.get('teams_count') if infobox and infobox.get('teams_count') else 16)

            next_rescan = today + datetime.timedelta(days=7)

            scout_payload = {
                "scouting_audit": {
                    "scan_timestamp": datetime.datetime.now().isoformat(),
                    "scouting_stage": "SHALLOW",
                    "completeness_grade": "GRADE_C",
                    "grade_reason": f"Grad C (Inväntar djupscanning): Hittad via Wikipedia {year} in sports events.",
                    "official_source_url": "",
                    "wikipedia_url": wiki_url,
                    "wikipedia_title": wiki_page,
                    "is_compatible_sport": True,
                    "draw_date": "",
                    "next_rescan_date": next_rescan.isoformat(),
                    "advancement_rules": "",
                    "official_site_audit": None,
                    "wikipedia_audit": None,
                },
                "master_event": {
                    "name": title,
                    "code": master_code,
                    "sport": sport_name,
                    "organizer": "Wikipedia",
                    "host_country": host_country,
                    "official_source_url": "",
                    "wikipedia_url": wiki_url,
                    "start_date": start_date_str,
                    "end_date": end_date_str,
                },
                "tournament_config": {
                    "name": title,
                    "total_teams": teams_count,
                    "knockout_stages": ["Quarterfinals", "Semifinals", "Final"],
                },
                "groups": [],
                "fixtures_sample": [],
                "raw_wikipedia": {
                    "year": year,
                    "wiki_page": wiki_page,
                    "title": title
                }
            }

            scanned_obj, s_created, _ = parse_and_save_scouted_json(scout_payload)
            if scanned_obj:
                if s_created:
                    created_cnt += 1
                else:
                    updated_cnt += 1
                prospects_list.append(scanned_obj)

    return created_cnt, updated_cnt, prospects_list


def scrape_web_for_tournaments(custom_query=None):
    """
    Triggers both AllSportDB API (v3) and Wikipedia Annual Sports Event Crawler (e.g. 2026 in sports),
    applies multi-step H2H team sport and format filtering, evaluates Grade A/B/C ratings,
    and ingests unique prospects into ScannedTournament for Engine Admin.
    Returns (created_count, updated_count, list_of_prospects).
    """
    # 1. Authoritative AllSportDB Ingestion
    c1, u1, p1 = fetch_and_ingest_allsportdb_tournaments(
        months_ahead=12,
        sync_scout=True
    )

    # 2. Wikipedia Annual Sports Events Ingestion (Current year + Next year)
    today_year = datetime.date.today().year
    c2, u2, p2 = fetch_and_ingest_wikipedia_year_events(
        years=[today_year, today_year + 1],
        sync_scout=True
    )

    total_created = c1 + c2
    total_updated = u1 + u2
    all_prospects = p1 + p2

    if custom_query and all_prospects:
        q_lower = custom_query.lower().strip()
        filtered_prospects = [
            p for p in all_prospects
            if q_lower in p.name.lower() 
            or q_lower in (p.sport or '').lower()
            or q_lower in (p.organizer or '').lower()
            or q_lower in (p.host_country or '').lower()
            or q_lower in (p.master_event_code or '').lower()
        ]
        if filtered_prospects:
            all_prospects = filtered_prospects

    return total_created, total_updated, all_prospects




def convert_scanned_to_live_tournament(scanned_id, admin_user, is_active=False, custom_point_system=None):
    """
    Takes a ScannedTournament prospect and converts it into a full live tournament
    in the database (MasterEvent, Tournament, PointSystem, Groups, Teams, Matches, KnockoutStages, Sidebets).
    Returns (tournament_obj, error_string_if_any).
    """
    scanned = ScannedTournament.objects.filter(id=scanned_id).first()
    if not scanned:
        return None, "Kunde inte hitta det scannade prospektet."

    payload = scanned.payload or {}
    master_event_data = payload.get('master_event', {})
    tournament_config = payload.get('tournament_config', {})
    groups_data = payload.get('groups', [])
    fixtures_data = payload.get('fixtures_sample', [])
    knockout_mapping = payload.get('knockout_mapping_sample', [])
    sidebets_data = payload.get('sidebets_suggestions', [])

    with transaction.atomic():
        # 1. Master Event
        master_code = scanned.master_event_code or master_event_data.get('code') or scanned.name.lower().replace(' ', '-')
        master_event_name = master_event_data.get('name') or scanned.name
        master_event, _ = MasterEvent.objects.update_or_create(
            code=master_code,
            defaults={
                'name': master_event_name,
                'is_active': True,
            }
        )

        # 2. Tournament
        has_best_thirds = tournament_config.get('has_best_thirds_table', False)
        has_runners_up = tournament_config.get('has_runners_up_table', False)
        has_host_ranking = tournament_config.get('has_host_ranking_table', False)
        off_rules = scanned.official_rules or payload.get('scouting_audit', {}).get('official_rules') or payload.get('scouting_audit', {}).get('advancement_rules') or ''
        off_url = scanned.official_source_url or payload.get('master_event', {}).get('official_source_url') or ''

        tournament, _ = Tournament.objects.update_or_create(
            name=scanned.name,
            defaults={
                'admin': admin_user,
                'is_active': is_active,
                'is_paused': False,
                'has_best_thirds_table': has_best_thirds,
                'has_runners_up_table': has_runners_up,
                'has_host_ranking_table': has_host_ranking,
                'official_rules': off_rules,
                'official_regulations_url': off_url,
            }
        )

        # 3. Point System
        pts_defaults = {
            'match_correct_goals_per_team': 2,
            'match_correct_total_goals': 2,
            'match_correct_1x2': 4,
            'group_correct_placement': 3,
            'group_correct_points': 2,
            'group_correct_goals_scored': 1,
            'group_correct_goals_conceded': 1,
            'group_correct_goal_diff': 1,
            'group_team_qualified': 0,
            'qualifying_table_team_qualified': 5,
            'knockout_round_of_32': 2,
            'knockout_round_of_16': 4,
            'knockout_quarterfinal': 6,
            'knockout_semifinal': 8,
            'knockout_bronze_match': 10,
            'knockout_final': 10,
        }
        if custom_point_system and isinstance(custom_point_system, dict):
            pts_defaults.update(custom_point_system)

        PointSystem.objects.update_or_create(
            tournament=tournament,
            defaults=pts_defaults
        )

        # Clear existing children for clean import
        tournament.tournament_groups.all().delete()
        tournament.knockout_stages.all().delete()
        tournament.teams.all().delete()
        tournament.matches.all().delete()
        tournament.sidebets.all().delete()

        created_groups = {}
        created_teams = {}

        # 4. Groups & Teams
        for g_idx, g_item in enumerate(groups_data, start=1):
            g_name = g_item.get('name', f"Grupp {g_idx}")
            g_order = g_item.get('order', g_idx)
            group = Group.objects.create(
                tournament=tournament,
                name=g_name,
                order=g_order
            )
            created_groups[g_name] = group

            for t_item in g_item.get('teams', []):
                t_name = t_item.get('name') if isinstance(t_item, dict) else str(t_item)
                t_code = t_item.get('code') if isinstance(t_item, dict) else None
                if not t_code and t_name:
                    clean_n = t_name.strip().lower()
                    t_code = COUNTRY_CODE_MAP.get(clean_n, '')
                
                team = Team.objects.create(
                    tournament=tournament,
                    group=group,
                    name=t_name,
                    code=t_code or ''
                )
                created_teams[t_name] = team

        # 5. Knockout Stages
        stage_names = tournament_config.get('knockout_stages', [])
        created_stages = {}
        for s_idx, s_name in enumerate(stage_names, start=1):
            stage = KnockoutStage.objects.create(
                tournament=tournament,
                name=s_name,
                order=s_idx
            )
            created_stages[s_name] = stage

        # 6. Fixtures
        match_number_counter = 0
        base_date = scanned.start_date or datetime.date.today()
        base_dt = datetime.datetime.combine(base_date, datetime.time(15, 0))

        if fixtures_data:
            for f_item in fixtures_data:
                match_number_counter += 1
                m_num = f_item.get('match_number', match_number_counter)
                stage_grp_name = f_item.get('stage_or_group', '')
                home = f_item.get('home_team', '')
                away = f_item.get('away_team', '')
                dt_str = f_item.get('date_time')
                
                match_dt = None
                if dt_str:
                    try:
                        match_dt = datetime.datetime.fromisoformat(dt_str)
                        if timezone.is_naive(match_dt):
                            match_dt = timezone.make_aware(match_dt, timezone.get_current_timezone())
                    except Exception:
                        pass
                
                if not match_dt:
                    match_dt = timezone.make_aware(base_dt + datetime.timedelta(days=(match_number_counter // 4)), timezone.get_current_timezone())

                group_obj = created_groups.get(stage_grp_name)
                stage_obj = created_stages.get(stage_grp_name)

                Match.objects.create(
                    tournament=tournament,
                    group=group_obj,
                    stage=stage_obj,
                    match_number=m_num,
                    home_team=home,
                    away_team=away,
                    date_time=match_dt
                )
        else:
            # Auto-generate round robin fixtures for groups if fixtures_sample was empty
            for g_name, group_obj in created_groups.items():
                g_teams = list(group_obj.teams.all())
                for i in range(len(g_teams)):
                    for j in range(i + 1, len(g_teams)):
                        match_number_counter += 1
                        m_dt = timezone.make_aware(base_dt + datetime.timedelta(days=(match_number_counter % 7)), timezone.get_current_timezone())
                        Match.objects.create(
                            tournament=tournament,
                            group=group_obj,
                            match_number=match_number_counter,
                            home_team=g_teams[i].name,
                            away_team=g_teams[j].name,
                            date_time=m_dt
                        )

        # 7. Knockout mapping fixtures
        if knockout_mapping:
            for k_item in knockout_mapping:
                match_number_counter += 1
                m_num = k_item.get('match_number', match_number_counter)
                s_name = k_item.get('stage', '')
                home_ph = k_item.get('home_placeholder', '')
                away_ph = k_item.get('away_placeholder', '')
                
                stage_obj = created_stages.get(s_name) or list(created_stages.values())[0] if created_stages else None
                m_dt = timezone.make_aware(base_dt + datetime.timedelta(days=7 + (match_number_counter % 5)), timezone.get_current_timezone())

                Match.objects.create(
                    tournament=tournament,
                    stage=stage_obj,
                    match_number=m_num,
                    home_team=home_ph,
                    away_team=away_ph,
                    date_time=m_dt
                )

        # 8. Sidebets
        for sb in sidebets_data:
            q_text = sb.get('question')
            q_type = sb.get('question_type', 'TEXT')
            q_pts = sb.get('points', 5)
            if q_text:
                Sidebet.objects.create(
                    tournament=tournament,
                    question=q_text,
                    points=q_pts,
                    question_type=q_type
                )

        # Mark ScannedTournament as converted and link to live tournament
        scanned.status = 'CONVERTED'
        scanned.converted_tournament = tournament
        scanned.save()

        return tournament, None
