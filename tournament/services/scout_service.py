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
                from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
                iso_start = LLMWikipediaScout._parse_date_string(infobox['start_date'])
                if not iso_start:
                    iso_start = str(infobox['start_date'])[:10]
                try:
                    start_date_val = datetime.date.fromisoformat(iso_start)
                    start_date_str = str(start_date_val)
                except Exception:
                    pass

            # Skip past, ongoing, or imminent events (< 30 days from today) during Webscan shallow ingestion.
            today = datetime.date.today()
            min_upcoming_date = today + datetime.timedelta(days=30)
            if start_date_val and start_date_val < min_upcoming_date:
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


def extract_wikipedia_url(scanned_obj):
    """
    Helper to extract and normalize the Wikipedia URL or page title key from a ScannedTournament instance.
    """
    if not scanned_obj:
        return ""
    
    payload = scanned_obj.payload or {}
    scouting_audit = payload.get('scouting_audit', {})
    master_event = payload.get('master_event', {})
    raw_wiki = payload.get('raw_wikipedia', {})
    
    wiki_url = (
        scouting_audit.get('wikipedia_url') or
        scouting_audit.get('wikipedia_title') or
        master_event.get('wikipedia_url') or
        raw_wiki.get('wiki_page') or
        ''
    )
    if not wiki_url and scanned_obj.official_source_url and 'wikipedia.org/wiki/' in scanned_obj.official_source_url:
        wiki_url = scanned_obj.official_source_url
        
    if wiki_url:
        wiki_url = wiki_url.strip()
        if 'wikipedia.org/wiki/' in wiki_url:
            wiki_url = wiki_url.split('wikipedia.org/wiki/')[-1].split('#')[0].strip('/')
        wiki_url = wiki_url.replace('./', '').replace('/wiki/', '').strip('/')
    
    return wiki_url.lower()


def merge_duplicate_scanned_tournaments_by_wikipedia():
    """
    Scans all ScannedTournament records and merges any duplicate records that share the exact same
    Wikipedia page URL or article identifier.
    
    The highest quality / deepest scanned instance is retained as primary, copying any missing groups,
    fixtures, rules, or links from duplicates before removing the duplicate prospects.
    Returns (merged_count, list_of_retained_prospects).
    """
    scanned_list = list(ScannedTournament.objects.exclude(status='ARCHIVED'))
    wiki_map = {}
    
    for s in scanned_list:
        wiki_key = extract_wikipedia_url(s)
        if wiki_key:
            wiki_map.setdefault(wiki_key, []).append(s)

    merged_count = 0
    retained_prospects = []

    for wiki_key, prospects in wiki_map.items():
        if len(prospects) <= 1:
            if prospects:
                retained_prospects.append(prospects[0])
            continue

        # Sort prospects: DEEP > SHALLOW, GRADE_A > GRADE_B > GRADE_C > GRADE_D, more groups/fixtures, oldest ID
        def sort_key(p):
            p_payload = p.payload or {}
            stage_score = 2 if p_payload.get('scouting_audit', {}).get('scouting_stage') == 'DEEP' else 1
            grade_score = {'GRADE_A': 4, 'GRADE_B': 3, 'GRADE_C': 2, 'GRADE_D': 1}.get(p.completeness_grade, 0)
            rules_score = 1 if p.official_rules else 0
            groups_count = len(p_payload.get('groups', []))
            fixtures_count = len(p_payload.get('fixtures_sample', []))
            return (stage_score, grade_score, rules_score, groups_count + fixtures_count, -p.id)

        prospects.sort(key=sort_key, reverse=True)
        primary = prospects[0]
        duplicates = prospects[1:]

        primary_payload = primary.payload or {}
        primary_groups = primary_payload.get('groups', [])
        primary_fixtures = primary_payload.get('fixtures_sample', [])

        for dup in duplicates:
            dup_payload = dup.payload or {}
            dup_groups = dup_payload.get('groups', [])
            dup_fixtures = dup_payload.get('fixtures_sample', [])

            # Merge groups & fixtures if primary lacks them
            if not primary_groups and dup_groups:
                primary_payload['groups'] = dup_groups
            if not primary_fixtures and dup_fixtures:
                primary_payload['fixtures_sample'] = dup_fixtures

            # Merge rules / links if primary lacks them
            if not primary.official_rules and dup.official_rules:
                primary.official_rules = dup.official_rules
            if not primary.official_source_url and dup.official_source_url:
                primary.official_source_url = dup.official_source_url

            # Transfer any linked TournamentEvent objects
            TournamentEvent.objects.filter(scanned_prospect=dup).update(scanned_prospect=primary)

            # Delete duplicate prospect
            dup.delete()
            merged_count += 1

        primary.payload = primary_payload
        primary.save()
        retained_prospects.append(primary)

    return merged_count, retained_prospects


MAJOR_FOOTBALL_COMPETITIONS_TARGETS = [
    # Global / FIFA
    '2026 FIFA World Cup',
    '2026 FIFA World Cup qualification',
    '2030 FIFA World Cup',
    '2027 FIFA Women\'s World Cup',
    # UEFA (Europe)
    'UEFA Euro 2028',
    'UEFA Euro 2028 qualifying',
    'UEFA Euro 2032',
    'UEFA Women\'s Euro 2025',
    'UEFA Women\'s Euro 2029',
    '2026–27 UEFA Nations League',
    '2028–29 UEFA Nations League',
    # CONMEBOL (South America)
    '2028 Copa América',
    '2026 FIFA World Cup qualification (CONMEBOL)',
    # CAF (Africa)
    '2026 African Nations Championship',
    '2027 Africa Cup of Nations',
    '2026 FIFA World Cup qualification (CAF)',
    # AFC (Asia)
    '2027 AFC Asian Cup',
    '2026 FIFA World Cup qualification (AFC)',
    # CONCACAF (North & Central America)
    '2025 CONCACAF Gold Cup',
    '2027 CONCACAF Gold Cup',
    '2026–27 CONCACAF Nations League',
    '2026 FIFA World Cup qualification (CONCACAF)',
    # OFC (Oceania)
    '2028 OFC Men\'s Nations Cup',
    '2026 FIFA World Cup qualification (OFC)',
]


def fetch_and_ingest_major_football_tournaments(sync_scout=True):
    """
    Ingests major global & continental football competitions (and their qualifiers) across all major continental federations:
    UEFA, CONMEBOL, CAF, AFC, CONCACAF, OFC, and FIFA.
    """
    created_cnt = 0
    updated_cnt = 0
    prospects_list = []

    wiki_scout = WikipediaScout()
    headers = {'User-Agent': 'PredictionEngineScout/3.0 (admin@predictionengine.org)'}

    for target in MAJOR_FOOTBALL_COMPETITIONS_TARGETS:
        try:
            res = requests.get('https://en.wikipedia.org/w/api.php', headers=headers, params={
                'action': 'query', 'list': 'search', 'srsearch': target, 'format': 'json', 'srlimit': 1
            }, timeout=10)
            if res.status_code != 200:
                continue
            results = res.json().get('query', {}).get('search', [])
            if not results:
                continue
            title = results[0].get('title')
            if not title:
                continue

            master_code = title.lower().replace(' ', '-').replace("'", '').replace('/', '-')[:100]

            existing = ScannedTournament.objects.filter(
                models.Q(master_event_code=master_code) |
                models.Q(name__iexact=title)
            ).first()

            if existing:
                continue

            wiki_page = title.replace(' ', '_')
            wiki_url = f"https://en.wikipedia.org/wiki/{wiki_page}"

            infobox = wiki_scout.audit_infobox_only(wiki_page)

            start_date_str = ""
            end_date_str = ""
            host_country = (infobox.get('host_country') if infobox else "") or ""
            logo_url = (infobox.get('logo_url') if infobox else "") or ""

            start_date_val = None
            if infobox and infobox.get('start_date'):
                from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
                iso_start = LLMWikipediaScout._parse_date_string(infobox['start_date'])
                if not iso_start:
                    iso_start = str(infobox['start_date'])[:10]
                try:
                    start_date_val = datetime.date.fromisoformat(iso_start)
                    start_date_str = str(start_date_val)
                except Exception:
                    pass

            teams_count = (infobox.get('teams_count') if infobox and infobox.get('teams_count') else 16)
            today = datetime.date.today()
            next_rescan = today + datetime.timedelta(days=7)

            scout_payload = {
                "scouting_audit": {
                    "scan_timestamp": datetime.datetime.now().isoformat(),
                    "scouting_stage": "SHALLOW",
                    "completeness_grade": "GRADE_C",
                    "grade_reason": "Grad C (Inväntar djupscanning): Hittad via Wikipedia kontinental fotbollsscanning.",
                    "official_source_url": "",
                    "wikipedia_url": wiki_url,
                    "wikipedia_title": title,
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
                    "sport": "Football",
                    "host_country": host_country,
                    "start_date": start_date_str,
                    "end_date": end_date_str,
                    "official_source_url": "",
                    "wikipedia_url": wiki_url,
                },
                "tournament_config": {
                    "total_teams": teams_count,
                    "knockout_stages": ["Quarterfinals", "Semifinals", "Final"]
                },
                "groups": [],
                "fixtures_sample": [],
                "logo_url": logo_url,
            }

            scanned_obj = ScannedTournament.objects.create(
                name=title,
                master_event_code=master_code,
                sport="Football",
                organizer="FIFA/Continental",
                host_country=host_country,
                start_date=start_date_val,
                logo_url=logo_url,
                completeness_grade="GRADE_C",
                grade_reason="Grad C (Inväntar djupscanning): Importerad från kontinental fotbollsscanning.",
                status="NEW",
                payload=scout_payload
            )

            created_cnt += 1
            prospects_list.append(scanned_obj)
        except Exception as exc:
            logger.warning("Error scanning major football competition target '%s': %s", target, exc)

    return created_cnt, updated_cnt, prospects_list


def scrape_web_for_tournaments(custom_query=None):
    return sync_all_scout_prospects(custom_query=custom_query)


def sync_all_scout_prospects(custom_query=None):
    """
    Triggers AllSportDB API (v3), Wikipedia Annual Sports Event Crawler, and
    Major Continental Football Tournaments & Qualifiers Crawler.
    Applies multi-step H2H team sport and format filtering, evaluates Grade A/B/C ratings,
    and ingests unique prospects into ScannedTournament for Engine Admin.
    After ingestion, automatically merges duplicate prospects sharing the exact same Wikipedia page.
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

    # 3. Major Continental Football Competitions & Qualifiers Ingestion
    c3, u3, p3 = fetch_and_ingest_major_football_tournaments(
        sync_scout=True
    )

    # 4. Automatic Deduplication / Merge by Wikipedia Page
    merged_cnt, _ = merge_duplicate_scanned_tournaments_by_wikipedia()
    if merged_cnt > 0:
        logger.info(f"Merged {merged_cnt} duplicate prospects sharing the same Wikipedia page.")

    # Re-fetch active non-archived prospects
    all_prospects = list(ScannedTournament.objects.exclude(status='ARCHIVED'))
    total_created = c1 + c2 + c3
    total_updated = u1 + u2 + u3

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


def ensure_complete_knockout_bracket(tournament, base_dt=None, start_match_number=0):
    """
    Ensures that every configured KnockoutStage in tournament has appropriate matches.
    If a stage (e.g. Quarterfinals, Semifinals, Final) has 0 matches, auto-generates
    the bracket matches linking previous stage winners.
    """
    stages_list = list(tournament.knockout_stages.all().order_by('order', 'id'))
    if not stages_list:
        return start_match_number

    if not base_dt:
        base_dt = timezone.now() + datetime.timedelta(days=30)

    match_counter = start_match_number or (tournament.matches.aggregate(models.Max('match_number')).get('match_number__max') or 0)

    for idx, stage in enumerate(stages_list):
        if stage.matches.exists():
            continue

        # Find previous stage with matches
        prev_stage = None
        for p in reversed(stages_list[:idx]):
            if p.matches.exists():
                prev_stage = p
                break

        if not prev_stage:
            continue

        prev_matches = list(prev_stage.matches.all().order_by('match_number', 'id'))
        if not prev_matches:
            continue

        prev_max_num = prev_stage.matches.aggregate(models.Max('match_number')).get('match_number__max') or 0
        match_counter = prev_max_num

        num_prev = len(prev_matches)
        if num_prev >= 2:
            num_new_matches = num_prev // 2
            
            for m_idx in range(num_new_matches):
                match_counter += 1
                if num_prev == 8 and num_new_matches == 4:
                    pairs = [(0, 2), (1, 5), (3, 4), (6, 7)]
                    p1_idx, p2_idx = pairs[m_idx]
                else:
                    p1_idx = m_idx * 2
                    p2_idx = m_idx * 2 + 1

                if p1_idx < num_prev and p2_idx < num_prev:
                    h_m = prev_matches[p1_idx]
                    a_m = prev_matches[p2_idx]

                    h_placeholder = f"Winner Match {h_m.match_number}"
                    a_placeholder = f"Winner Match {a_m.match_number}"

                    m_dt = base_dt + datetime.timedelta(days=7 + idx * 3 + m_idx)
                    if timezone.is_naive(m_dt):
                        m_dt = timezone.make_aware(m_dt, timezone.get_current_timezone())

                    Match.objects.create(
                        tournament=tournament,
                        stage=stage,
                        match_number=match_counter,
                        home_team=h_placeholder,
                        away_team=a_placeholder,
                        date_time=m_dt
                    )

    return match_counter


def transfer_scouted_logo_to_tournament(scanned, tournament, master_event=None):
    """
    Transfers scouted logotype image from ScannedTournament (logo_url) into
    Tournament.icon (and MasterEvent.icon) by downloading the image payload.
    """
    if not scanned or not tournament:
        return

    payload = scanned.payload or {}
    scout_audit = payload.get('scouting_audit') or {}
    wiki_audit = scout_audit.get('wikipedia_audit') if isinstance(scout_audit, dict) else {}
    master_evt_data = payload.get('master_event') if isinstance(payload.get('master_event'), dict) else {}

    logo_url = (
        scanned.logo_url
        or (wiki_audit.get('logo_url') if isinstance(wiki_audit, dict) else None)
        or master_evt_data.get('logo_url')
        or payload.get('logo_url')
    )

    if not logo_url or not isinstance(logo_url, str) or not logo_url.startswith('http'):
        return

    # Skip if logo_url is invalid or country flag
    from tournament.services.wikidata_scout import is_valid_tournament_logo
    if not is_valid_tournament_logo(logo_url):
        return

    try:
        import requests
        import urllib.parse
        import os
        from django.core.files.base import ContentFile

        headers = {'User-Agent': 'PredictionEngineScout/3.0 (contact@predictionengine.app)'}
        res = requests.get(logo_url, headers=headers, timeout=10)
        if res.status_code == 200 and res.content and len(res.content) > 100:
            parsed_path = urllib.parse.urlparse(logo_url).path
            ext = os.path.splitext(parsed_path)[1].lower()
            if not ext or len(ext) > 5 or ext not in ['.png', '.jpg', '.jpeg', '.svg', '.webp']:
                ext = '.png'

            file_name = f"scouted_{tournament.id}_{scanned.id}{ext}"
            tournament.icon.save(file_name, ContentFile(res.content), save=True)

            if master_event and (not master_event.icon or not hasattr(master_event.icon, 'url') or not master_event.icon.url):
                master_event.icon.save(file_name, ContentFile(res.content), save=True)
    except Exception as e:
        logger.warning(f"Could not transfer scouted logo from '{logo_url}' to tournament #{tournament.id}: {e}")


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

        def _resolve_stage_obj(s_name, created_stages):
            if not created_stages:
                return None
            if s_name in created_stages:
                return created_stages[s_name]
            clean_s = (s_name or '').lower().strip()
            for k, obj in created_stages.items():
                clean_k = k.lower().strip()
                if clean_s == clean_k:
                    return obj
                if ('quarter' in clean_s or 'kvart' in clean_s) and ('quarter' in clean_k or 'kvart' in clean_k):
                    return obj
                if 'semi' in clean_s and 'semi' in clean_k:
                    return obj
                if ('final' in clean_s and 'semi' not in clean_s and 'quarter' not in clean_s) and ('final' in clean_k and 'semi' not in clean_k and 'quarter' not in clean_k):
                    return obj
                if ('16' in clean_s or '8-del' in clean_s) and ('16' in clean_k or '8-del' in clean_k):
                    return obj
                if ('32' in clean_s or '16-del' in clean_s) and ('32' in clean_k or '16-del' in clean_k):
                    return obj
            return list(created_stages.values())[0]

        # 7. Knockout mapping fixtures
        if knockout_mapping:
            for k_item in knockout_mapping:
                match_number_counter += 1
                m_num = k_item.get('match_number', match_number_counter)
                s_name = k_item.get('stage', '')
                home_ph = k_item.get('home_placeholder', '')
                away_ph = k_item.get('away_placeholder', '')
                
                stage_obj = _resolve_stage_obj(s_name, created_stages)
                m_dt = timezone.make_aware(base_dt + datetime.timedelta(days=7 + (match_number_counter % 5)), timezone.get_current_timezone())

                Match.objects.create(
                    tournament=tournament,
                    stage=stage_obj,
                    match_number=m_num,
                    home_team=home_ph,
                    away_team=away_ph,
                    date_time=m_dt
                )

        # Auto-complete any empty knockout stages (Quarterfinals, Semifinals, Final)
        match_number_counter = ensure_complete_knockout_bracket(tournament, base_dt, match_number_counter)

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

        # Transfer scouted logotype image to Tournament.icon and MasterEvent.icon
        transfer_scouted_logo_to_tournament(scanned, tournament, master_event)

        return tournament, None
