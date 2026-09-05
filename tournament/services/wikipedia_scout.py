import logging
import urllib.parse
import re
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class WikipediaScout:
    """
    Automated Machine Learning, LLM Semantic & NLP Heuristic Wikipedia Scout for tournament format, regulations,
    team seeding, full fixture schedules, stage mapping, and draw audits.
    
    Universal Multi-Sport Extraction Architecture:
    - 1. Universal Group/Pool/Division Extractor: Handles Group A-Z, Pool A-Z, Division A-Z, Zone A-Z across all sports.
    - 2. Heading-Scoped Section Parser: Isolates Final Tournament pools/groups, eliminating qualification and allocation metadata tables.
    - 3. Stage-Aware Fixture Mining Engine: Maps each match box directly to its group, pool, or knockout stage (Pool A, Round of 16, Quarterfinals, Final).
    - 4. Draw/Lottery Date & Advancement Rule Miner: Extracts draw dates and advancement text (e.g. "Top 4 teams from each pool advance to Round of 16").
    - 5. Confidence Scoring & Deduplication Engine (Confidence Rating 0.0 - 1.0).
    """
    def __init__(self):
        self.headers = {
            'User-Agent': 'PredictionEngine-TournamentScout/1.0 (contact@predictionengine.app)',
            'Accept': 'application/json'
        }
        self.base_url = 'https://en.wikipedia.org/w/api.php'

    def get_article_title_from_url(self, wiki_url):
        """Extracts article title from Wikipedia URL."""
        if not wiki_url or 'wikipedia.org/wiki/' not in wiki_url:
            return None
        parts = wiki_url.split('wikipedia.org/wiki/')
        if len(parts) > 1:
            clean = parts[1].split('#')[0]
            return urllib.parse.unquote(clean)
        return None

    def search_wikipedia_article(self, tournament_name, year=None):
        """
        Searches Wikipedia for matching tournament article.
        If initial search in English Wikipedia yields no results or term is non-English,
        queries Swedish Wikipedia and resolves interlanguage langlinks to English title.
        """
        query = f"{tournament_name} {year}" if year else tournament_name
        params = {
            'action': 'query',
            'list': 'search',
            'srsearch': query,
            'format': 'json',
            'srlimit': 3
        }
        try:
            res = requests.get(self.base_url, headers=self.headers, params=params, timeout=10)
            if res.status_code == 200:
                data = res.json()
                results = data.get('query', {}).get('search', [])
                if results:
                    return results[0].get('title')
        except Exception as e:
            logger.error(f"Wikipedia search error for '{query}': {e}")

        # Multilingual fallback: search Swedish Wikipedia and resolve English langlink
        try:
            sv_url = "https://sv.wikipedia.org/w/api.php"
            res_sv = requests.get(sv_url, headers=self.headers, params=params, timeout=10)
            if res_sv.status_code == 200:
                results_sv = res_sv.json().get('query', {}).get('search', [])
                if results_sv:
                    sv_title = results_sv[0].get('title')
                    res_link = requests.get(sv_url, headers=self.headers, params={
                        'action': 'query', 'prop': 'langlinks', 'titles': sv_title, 'lllang': 'en', 'format': 'json'
                    }, timeout=10)
                    if res_link.status_code == 200:
                        pages = res_link.json().get('query', {}).get('pages', {})
                        for pid, page in pages.items():
                            ll = page.get('langlinks', [])
                            if ll and ll[0].get('*'):
                                return ll[0].get('*')
                    return sv_title
        except Exception as e:
            logger.warning(f"Swedish Wikipedia search fallback error for '{query}': {e}")

        return None

    def audit_infobox_only(self, page_title):
        """
        Stage 1 Shallow Ingestion: fast Wikipedia infobox parse only.
        Extracts name, host_country, teams_count, start_date, end_date and wiki_url
        WITHOUT running the full fixture mining, group extraction, draw date auditing,
        or knockout stage detection. Returns in < 1 second per tournament.

        Returns a minimal dict suitable for saving a SHALLOW ScannedTournament prospect,
        or None if the page could not be fetched.
        """
        if not page_title:
            return None
        params = {
            'action': 'parse',
            'page': page_title,
            'prop': 'text',
            'section': '0',          # Only the lead section (contains infobox)
            'format': 'json',
        }
        try:
            res = requests.get(self.base_url, headers=self.headers, params=params, timeout=10)
            if res.status_code != 200:
                return None
            html_text = res.json().get('parse', {}).get('text', {}).get('*', '')
            if not html_text:
                return None

            soup = BeautifulSoup(html_text, 'html.parser')
            infobox = soup.find('table', class_=re.compile(r'infobox|vcard'))

            teams_count  = 0
            host_country = ''
            start_date   = ''
            end_date     = ''
            sport        = ''

            if infobox:
                for row in infobox.find_all('tr'):
                    header    = row.find('th')
                    data_cell = row.find('td')
                    if not (header and data_cell):
                        continue
                    h_text = header.get_text(separator=' ', strip=True).lower()
                    d_text = data_cell.get_text(separator=' ', strip=True)

                    if 'teams' in h_text or 'participants' in h_text:
                        m = re.search(r'\d+', d_text)
                        if m:
                            teams_count = int(m.group())

                    elif 'host' in h_text or 'location' in h_text or 'country' in h_text:
                        if not host_country:
                            host_country = d_text[:80]

                    elif 'sport' in h_text or 'discipline' in h_text:
                        if not sport:
                            raw_s = d_text.strip()
                            from tournament.services.tournament_filter import detect_sport_from_title
                            sport = detect_sport_from_title(raw_s, default_sport=raw_s)

                    elif 'date' in h_text or 'period' in h_text or 'dates' in h_text:
                        from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
                        p_start, p_end = LLMWikipediaScout._parse_date_range(d_text, "", page_title=page_title)
                        if p_start and not start_date:
                            start_date = p_start
                        if p_end and not end_date:
                            end_date = p_end

            # Fallback to lead paragraphs if infobox omitted date or sport
            paragraphs = soup.find_all('p')
            lead_text = " ".join(p.get_text(separator=' ', strip=True) for p in paragraphs[:3])

            if not start_date:
                from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
                p_start, p_end = LLMWikipediaScout._parse_date_range(lead_text, "", page_title=page_title)
                if p_start and not start_date:
                    start_date = p_start
                if p_end and not end_date:
                    end_date = p_end

            if not sport and lead_text:
                from tournament.services.tournament_filter import detect_sport_from_title
                inferred_s = detect_sport_from_title(lead_text, default_sport="")
                if inferred_s:
                    sport = inferred_s

            wiki_url = (
                f"https://en.wikipedia.org/wiki/"
                f"{urllib.parse.quote(page_title.replace(' ', '_'))}"
            )
            return {
                'page_title':   page_title,
                'wiki_url':     wiki_url,
                'host_country': host_country,
                'teams_count':  teams_count,
                'start_date':   start_date,
                'end_date':     end_date,
                'sport':        sport,
                'scouting_stage': 'SHALLOW',
            }

        except Exception as e:
            logger.error(f"Error in audit_infobox_only for '{page_title}': {e}")
            return None


    def audit_tournament_page(self, page_title):
        """
        Parses Wikipedia page HTML and sections using Universal Multi-Sport LLM Heuristics to extract:
        - clean final tournament groups/pools & team allocations (Group A-F, Pool A-D)
        - stage-mapped fixtures (Pool A, Group B, Round of 16, Quarterfinals, Semifinals, Final)
        - scheduled draw/lottery date & knockout stage advancement setup rules
        - knockout_stages (Round of 16, Quarterfinals, Semifinals, Final)
        - draw_completed & fixtures_completed status
        """
        if not page_title:
            return None

        params = {
            'action': 'parse',
            'page': page_title,
            'prop': 'text|sections',
            'format': 'json'
        }
        try:
            res = requests.get(self.base_url, headers=self.headers, params=params, timeout=15)
            if res.status_code != 200:
                return None
            
            data = res.json().get('parse', {})
            if not data:
                return None

            html_text = data.get('text', {}).get('*', '')
            sections = [s.get('line', '') for s in data.get('sections', [])]
            
            soup = BeautifulSoup(html_text, 'html.parser')
            
            # 1. Parse Infobox for host country and quick stats
            infobox = soup.find('table', class_=re.compile(r'infobox|vcard'))
            teams_count = 0
            host_country = ''
            start_date_extracted = ''
            end_date_extracted = ''
            logo_url = ''

            from tournament.services.emblem_scout import is_valid_tournament_logo

            if infobox:
                for img_tag in infobox.find_all('img'):
                    src = img_tag.get('src', '')
                    if src.startswith('//'):
                        src = 'https:' + src
                    if src:
                        src_clean = src.split('?')[0]
                        if is_valid_tournament_logo(src_clean):
                            logo_url = src_clean
                            break

                for row in infobox.find_all('tr'):
                    header = row.find('th')
                    data_cell = row.find('td')
                    if header and data_cell:
                        h_text = header.get_text().strip().lower()
                        d_text = data_cell.get_text().strip()
                        if 'teams' in h_text or 'participants' in h_text:
                            m = re.search(r'\d+', d_text)
                            if m:
                                teams_count = int(m.group())
                        elif 'host' in h_text or 'location' in h_text:
                            from tournament.services.scout_service import normalize_locations
                            a_links = [
                                a.get_text().strip() for a in data_cell.find_all('a')
                                if a.get_text().strip() and not re.match(r'^\[\s*[A-Za-z0-9]+\s*\]$', a.get_text().strip())
                            ]
                            if a_links and len(a_links) > 1:
                                host_country = ' / '.join(a_links)
                            else:
                                host_country = normalize_locations(data_cell.get_text(separator=' / ').strip())
                        elif 'date' in h_text or 'dates' in h_text or 'duration' in h_text:
                            from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
                            s_iso, e_iso = LLMWikipediaScout._parse_date_range(d_text, "", page_title)
                            if s_iso:
                                start_date_extracted = s_iso
                            if e_iso:
                                end_date_extracted = e_iso

            # 2. Universal Heading-Scoped Group & Pool Extractor (Group A-Z, Pool A-Z, Division A-Z)
            groups = []
            extracted_teams_set = set()
            headings = soup.find_all(re.compile(r'^h[2-4]$'))

            EXCLUDED_LABELS = {'stage', 'allocation', 'results', 'draw', 'qualification', 'qualifying', 'summary'}

            for h in headings:
                txt = h.get_text().strip()
                m = re.match(r'^(Group|Pool|Division|Zone)\s+([A-Z0-9]+)$', txt, re.IGNORECASE)
                if m:
                    label_type = m.group(1).capitalize()
                    label_id = m.group(2).upper()
                    
                    if label_id.lower() not in EXCLUDED_LABELS and label_type.lower() not in EXCLUDED_LABELS:
                        grp_name = f"{label_type} {label_id}"

                        # Find next standings table within current section scope
                        tbl = h.find_next('table', class_='wikitable')
                        next_h = h.find_next(re.compile(r'^h[2-4]$'))
                        if tbl and next_h:
                            # If another heading intervenes before the table, the table belongs to another section
                            tbl_pos = len(list(tbl.previous_elements))
                            next_h_pos = len(list(next_h.previous_elements))
                            if tbl_pos > next_h_pos:
                                tbl = None

                        # Reject non-group tables (seeding pots, rankings, calendar)
                        if tbl:
                            th_txt = " ".join([th.get_text() for th in tbl.find_all('th')]).lower()
                            if any(k in th_txt for k in ['pot 1', 'pot 2', 'pot 3', 'pot 4', 'seeding', 'allocation', 'criteria for final', 'matchday 1', 'matchday 2']):
                                tbl = None

                        teams_in_tbl = []
                        if tbl:
                            for row in tbl.find_all('tr')[1:]:
                                th = row.find('th')
                                tds = row.find_all('td')
                                cell = th or (tds[0] if tds else None)
                                if cell:
                                    tname = cell.get_text().strip()
                                    from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
                                    clean_t = LLMWikipediaScout._clean_team_name(tname)
                                    if clean_t and not clean_t.isdigit() and len(clean_t) > 2 and clean_t not in teams_in_tbl:
                                        teams_in_tbl.append(clean_t)
                                        extracted_teams_set.add(clean_t)

                        is_second_stage = bool(re.search(r'Main|Second|Group\s+(?:[I|V|X]+|\d+)', grp_name, re.IGNORECASE) and not re.search(r'Group\s+[A-F]$', grp_name, re.IGNORECASE))
                        if is_second_stage and not teams_in_tbl:
                            if label_id in ['I', '1']:
                                teams_in_tbl = ['A1 (1:a Grupp A)', 'A2 (2:a Grupp A)', 'A3 (3:a Grupp A)', 'B1 (1:a Grupp B)', 'B2 (2:a Grupp B)', 'B3 (3:a Grupp B)', 'C1 (1:a Grupp C)', 'C2 (2:a Grupp C)', 'C3 (3:a Grupp C)']
                            elif label_id in ['II', '2']:
                                teams_in_tbl = ['D1 (1:a Grupp D)', 'D2 (2:a Grupp D)', 'D3 (3:a Grupp D)', 'E1 (1:a Grupp E)', 'E2 (2:a Grupp E)', 'E3 (3:a Grupp E)', 'F1 (1:a Grupp F)', 'F2 (2:a Grupp F)', 'F3 (3:a Grupp F)']

                        if grp_name not in [g['name'] for g in groups]:
                            groups.append({
                                'name': grp_name,
                                'is_second_stage': is_second_stage,
                                'is_placeholder_group': is_second_stage or any(re.search(r'^[A-Z]\d', t) for t in teams_in_tbl) or not teams_in_tbl,
                                'teams': [{'name': t, 'is_placeholder': is_second_stage or bool(re.search(r'^[A-Z]\d', t))} for t in teams_in_tbl]
                            })

            # Fallback if heading-based scan didn't capture groups/pools (Only accept genuine standings tables with 3-8 teams)
            if not groups:
                wikitables = soup.find_all('table', class_=re.compile(r'wikitable'))
                for tbl in wikitables:
                    prev_h = tbl.find_previous(re.compile(r'^h[2-4]$'))
                    prev_h_txt = (prev_h.get_text().strip() if prev_h else '').lower()
                    if any(k in prev_h_txt for k in ['qualif', 'award', 'medal', 'all-time', 'statistic', 'summary', 'record', 'participat']):
                        continue

                    headers_txt = [th.get_text().strip().lower() for th in tbl.find_all('th')]
                    if any(k in headers_txt for k in ['appearance', 'streak', 'previous best', 'mvp', 'all-tournament', 'method', 'wr']):
                        continue

                    # Require standard standings headers (Pts, Pld, W, L, GF, GA, Pos, etc.)
                    has_standings_header = any(h in ['pts', 'pld', 'w', 'd', 'l', 'gf', 'ga', 'gd', 'pos', 'p', 'v', 'o', 'f', 'diff', 'points'] for h in headers_txt)
                    if any('team' in h or 'pos' in h or 'lag' in h for h in headers_txt) and has_standings_header:
                        teams_in_tbl = []
                        for row in tbl.find_all('tr')[1:]:
                            th = row.find('th')
                            tds = row.find_all('td')
                            cell = th or (tds[0] if tds else None)
                            if cell:
                                t_name = cell.get_text().strip()
                                if t_name and not t_name.isdigit() and len(t_name) > 2:
                                    from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
                                    clean_t = LLMWikipediaScout._clean_team_name(t_name)
                                    if clean_t and clean_t not in teams_in_tbl:
                                        teams_in_tbl.append(clean_t)
                                        extracted_teams_set.add(clean_t)
                        
                        # Only accept standard tournament group size (between 3 and 10 teams)
                        if 3 <= len(teams_in_tbl) <= 10 and len(groups) < 8:
                            grp_label = f"Group {chr(65 + len(groups))}"
                            groups.append({
                                'name': grp_label,
                                'teams': [{'name': t} for t in teams_in_tbl]
                            })

            # 3. Stage-Aware Multi-Strategy Fixture Mining Engine
            # Supports both real-team fixtures AND placeholder fixtures (1E, W37, TBD, A1)
            # across Group Stage, Knockout Stage, and Schedule-Table (qualifying) formats.
            fixtures = []
            seen_keys = set()
            MONTH_NAMES = {'january', 'february', 'march', 'april', 'may', 'june',
                           'july', 'august', 'september', 'october', 'november', 'december',
                           'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'}
            MONTH_RE = r'(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)'

            # Placeholder code regex: 1E, 2D, W37, W40, A1, B2, TBD, 3C/D/F, 1st, 2nd etc.
            PLACEHOLDER_RE = re.compile(
                r'^(?:TBD|TBC|[1-9][A-Z]|[A-Z][1-9]|[Ww]\d{1,3}|[1-9][a-z]{2}|'
                r'[0-9]+[A-Z][/A-Z]*|Runner[\s\-]?up|Winner(?:\s+Match\s+\d+|\s+SF\d+|\s+QF\d+)?|Host)$',
                re.IGNORECASE
            )

            def is_placeholder_team(name):
                """Returns True if the name looks like a knockout bracket placeholder code."""
                if not name:
                    return True
                from tournament.services.team_badge_service import TeamBadgeService
                if TeamBadgeService.is_placeholder(name):
                    return True
                return bool(PLACEHOLDER_RE.match(name.strip()))

            def get_preceding_stage(elem):
                headings = []
                curr = elem
                for _ in range(5):
                    h = curr.find_previous(re.compile(r'^h[2-4]$'))
                    if not h or h in headings:
                        break
                    headings.append(h)
                    curr = h

                league_part = ""
                group_part = ""
                for h in headings:
                    t = re.sub(r'\[edit\]', '', h.get_text().strip(), flags=re.I).strip()
                    # Filter out non-match section headers: criteria, ranking, seeding, tiebreakers, overview, etc.
                    if re.search(r'\b(?:criteria|ranking|seeding|pot|allocation|tiebreaker|overview|format|schedule)\b', t, re.I):
                        continue
                    if re.search(r'\b(?:league|division)\s+[A-D]\b', t, re.IGNORECASE) and not league_part:
                        league_part = t
                    if re.search(r'\b(?:group|pool)\s+[A-Z0-9]\b|quarter|semi|final|round\s+of|playoff', t, re.IGNORECASE) and not group_part:
                        group_part = t

                if league_part and group_part and league_part.lower() not in group_part.lower():
                    return f"{league_part} - {group_part}"
                elif group_part:
                    return group_part
                elif league_part:
                    return league_part
                return 'Gruppspel'

            def add_fixture(elem, home, away, date_str, time_str, venue_str, strategy_name,
                            match_num=None, is_scheduled_slot=False):
                """
                Adds a fixture entry. Accepts both real team names and placeholder codes
                (1E, W37, TBD, A1). For fixtures with no discernible teams but a valid
                date/time/venue, falls back to 'TBD' placeholder names.
                """
                from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
                clean_h = LLMWikipediaScout._clean_team_name(home)
                clean_a = LLMWikipediaScout._clean_team_name(away)

                # Substitute TBD for empty placeholder slots that have scheduling data
                if not clean_h and (date_str or time_str or match_num):
                    clean_h = 'TBD'
                if not clean_a and (date_str or time_str or match_num):
                    clean_a = 'TBD'

                # Require at least some team identity
                if not clean_h or not clean_a:
                    return
                if clean_h in ['–', '-', '—', 'N/A', 'TBD', 'TBC', ''] or clean_a in ['–', '-', '—', 'N/A', 'TBD', 'TBC', '']:
                    return
                if re.match(r'^\d+(?:st|nd|rd|th)$', clean_h, re.I) or re.match(r'^\d+(?:st|nd|rd|th)$', clean_a, re.I):
                    return
                if clean_h.lower().startswith('as ') or clean_a.lower().startswith('as '):
                    return
                # Reject month names accidentally parsed as teams
                if clean_h.lower() in MONTH_NAMES or clean_a.lower() in MONTH_NAMES:
                    return
                # Reject trivially short non-placeholder strings
                h_is_pholder = is_placeholder_team(clean_h)
                a_is_pholder = is_placeholder_team(clean_a)
                if len(clean_h) < 2 and not h_is_pholder:
                    return
                if len(clean_a) < 2 and not a_is_pholder:
                    return
                # Reject identical non-placeholder teams (duplicates)
                if clean_h.lower() == clean_a.lower() and not (h_is_pholder and a_is_pholder):
                    return

                # Dedup: use match_num if available, else home+away+date
                if match_num:
                    norm_key = f'match_{match_num}'
                else:
                    norm_key = f'{clean_h.lower()}_vs_{clean_a.lower()}_{date_str[:10]}'
                if norm_key in seen_keys:
                    return
                seen_keys.add(norm_key)

                stage_label = get_preceding_stage(elem) if elem is not None else 'Scheduled'

                confidence = 0.5
                if date_str: confidence += 0.2
                if time_str: confidence += 0.15
                if venue_str: confidence += 0.1
                if h_is_pholder or a_is_pholder: confidence -= 0.1  # slight deduction for placeholder

                iso_date = LLMWikipediaScout._parse_date_string(date_str) if date_str else ''
                clean_date = iso_date if iso_date else date_str

                fixtures.append({
                    'home_team': clean_h,
                    'away_team': clean_a,
                    'stage_or_group': stage_label,
                    'date': clean_date,
                    'time': time_str,
                    'venue': venue_str,
                    'confidence': round(max(0.1, confidence), 2),
                    'strategy': strategy_name,
                    'is_placeholder': h_is_pholder or a_is_pholder,
                })

            # --- Strategy 1: FIFA footballbox match blocks (group-stage seeded + knockout placeholders) ---
            MONTH_RE = r'(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
            DATE_RE  = rf'(\d{{1,2}}\s+{MONTH_RE}\s+\d{{4}})'
            TIME_RE  = r'(\d{1,2}:\d{2})'

            footballboxes = soup.find_all('div', class_='footballbox')
            for fbox in footballboxes:
                home_el  = fbox.find(class_=re.compile(r'fhome|home|vcard'))
                away_el  = fbox.find(class_=re.compile(r'faway|away'))
                venue_el = fbox.find(class_=re.compile(r'fright|fvenue|location|venue'))

                home_t  = home_el.get_text().strip()  if home_el  else ''
                away_t  = away_el.get_text().strip()  if away_el  else ''
                venue_t = venue_el.get_text().strip() if venue_el else ''

                if home_t and away_t:
                    full_text = ' '.join(fbox.get_text().split())
                    date_m = re.search(DATE_RE, full_text)
                    time_m = re.search(TIME_RE, full_text)

                    # --- Strategy 1b: NLP Placeholder Fallback ---
                    # When class-based extraction returns empty (knockout placeholder matches),
                    # parse the raw text block for codes like '1E Match 39 2D' or 'W37 Match 46 W40'
                    if (not home_t or not away_t):
                        # Pattern: [CODE] Match [NUM] [CODE]  (knockout bracket placeholder)
                        m_ko = re.search(
                            r'\b((?:[0-9]+[A-Za-z/]+|[A-Za-z]+[0-9]+|TBD|[Ww]\d+))\s+'
                            r'Match\s+(\d+)\s+'
                            r'((?:[0-9]+[A-Za-z/]+|[A-Za-z]+[0-9]+|TBD|[Ww]\d+))\b',
                            full_text, re.IGNORECASE
                        )
                        if m_ko:
                            home_t  = m_ko.group(1).upper()
                            away_t  = m_ko.group(3).upper()
                            match_num_ko = int(m_ko.group(2))
                            add_fixture(fbox, home_t, away_t,
                                        date_m.group(1) if date_m else '',
                                        time_m.group(1) if time_m else '',
                                        venue_t, 'Strategy_1b_Footballbox_KO_Placeholder',
                                        match_num=match_num_ko)
                            continue  # already added, skip generic add below

                    add_fixture(fbox, home_t, away_t,
                                date_m.group(1) if date_m else '',
                                time_m.group(1) if time_m else '',
                                venue_t, 'Strategy_1_Footballbox')

            # --- Strategy 2: Class Containers (vevent, fevent, handballbox, basketballbox, icehockeybox) ---
            match_containers = soup.find_all(
                ['table', 'div'],
                class_=re.compile(r'vevent|fevent|handballbox|basketballbox|icehockeybox')
            )
            for elem in match_containers:
                vcards = elem.find_all(class_=re.compile(r'vcard|attendee'))
                if len(vcards) >= 2:
                    home_t = vcards[0].get_text().replace('\xa0', ' ').strip()
                    away_t = vcards[1].get_text().replace('\xa0', ' ').strip()

                    a_home = vcards[0].find('a')
                    a_away = vcards[1].find('a')
                    if a_home: home_t = a_home.get_text().strip()
                    if a_away: away_t = a_away.get_text().strip()

                    full_text = ' '.join(elem.get_text().split())
                    date_m = re.search(DATE_RE, full_text)
                    time_m = re.search(TIME_RE, full_text)

                    cells   = elem.find_all(['td', 'th'])
                    venue_t = cells[-1].get_text().strip() if len(cells) >= 5 else ''

                    add_fixture(elem, home_t, away_t,
                                date_m.group(1) if date_m else '',
                                time_m.group(1) if time_m else '',
                                venue_t, 'Strategy_2_ClassContainers')

            # --- Strategy 3: NLP Table & Row Pattern Mining ---
            for row in soup.find_all('tr'):
                prev_h = row.find_previous(re.compile(r'^h[2-4]$'))
                prev_h_txt = (prev_h.get_text().strip() if prev_h else '').lower()
                if any(k in prev_h_txt for k in ['summar', 'result', 'history', 'medal', 'past', 'edition', 'champions', 'award', 'statistic', 'all-time', 'record']):
                    continue

                cells = [c.get_text().strip() for c in row.find_all(['td', 'th'])]
                if len(cells) >= 3:
                    found_cell_fixture = False
                    for idx, cell_txt in enumerate(cells[1:-1], start=1):
                        c_strip = cell_txt.strip()
                        if c_strip in ['v', 'vs', 'v\n', 'vs\n']:
                            home_c = cells[idx - 1].replace('\xa0', ' ').strip()
                            away_c = cells[idx + 1].replace('\xa0', ' ').strip()
                            venue_c = cells[idx + 2].replace('\xa0', ' ').strip() if len(cells) > idx + 2 else ''
                            datetime_c = cells[idx - 2].replace('\xa0', ' ').strip() if idx >= 2 else ''

                            date_m = re.search(DATE_RE, datetime_c) or re.search(DATE_RE, ' '.join(cells))
                            time_m = re.search(TIME_RE, datetime_c) or re.search(TIME_RE, ' '.join(cells))

                            add_fixture(row,
                                        home_c,
                                        away_c,
                                        date_m.group(1) if date_m else '',
                                        time_m.group(1) if time_m else '',
                                        venue_c, 'Strategy_3a_CellMining')
                            found_cell_fixture = True
                            break
                    if found_cell_fixture:
                        continue

                txt = ' '.join(cells) if cells else ' '.join(row.get_text().split())
                m_vs = re.search(r'([A-Z][a-zA-Z\s]{2,20})\s+(?:v|vs|\u2013|\-)\s+([A-Z][a-zA-Z\s]{2,20})', txt)
                date_m = re.search(DATE_RE, txt)
                time_m = re.search(TIME_RE, txt)

                if m_vs and (date_m or time_m):
                    venue_t = cells[-1] if len(cells) >= 5 and cells[-1] and not re.search(r'\d{1,2}:\d{2}', cells[-1]) else ''
                    add_fixture(row,
                                m_vs.group(1).strip(),
                                m_vs.group(2).strip(),
                                date_m.group(1) if date_m else '',
                                time_m.group(1) if time_m else '',
                                venue_t, 'Strategy_3b_NLP_TableMining')

            # --- Strategy 5: Cross-Table & Group-Adjacent Match Matrix Mining ---
            # Supports round-robin group tables ONLY where home/away fixture dates or scores
            # are embedded as a cross-table matrix (header row and first column have matching teams).
            matrix_count = 0
            for tbl in soup.find_all('table', class_=re.compile(r'wikitable')):
                prev_h = tbl.find_previous(re.compile(r'^h[2-4]$'))
                prev_h_txt = prev_h.get_text().strip() if prev_h else ''
                # Strictly reject tables under non-fixture headers (criteria, seeding, rankings, tiebreakers)
                if re.search(r'\b(?:criteria|ranking|seeding|pot|allocation|tiebreaker|overview|format|schedule|standings)\b', prev_h_txt, re.I):
                    continue

                rows = tbl.find_all('tr')
                if len(rows) < 3:
                    continue

                # Check if header row contains standings keywords
                header_row = rows[0]
                th_headers = [th.get_text().strip() for th in header_row.find_all(['th', 'td'])]
                if any(h in ['Pts', 'Pld', 'W', 'D', 'L', 'GF', 'GA', 'GD', 'Pos', 'Team', 'Lag', 'P', 'V', 'O', 'F', 'GM', 'IM', 'MS'] for h in th_headers):
                    continue

                teams_in_matrix = []
                team_rows = []
                for r in rows[1:]:
                    tds = r.find_all(['td', 'th'])
                    if not tds:
                        continue
                    tname = ''
                    for cell in tds[:3]:
                        txt = cell.get_text().strip()
                        clean = re.sub(r'^\d+\s*', '', txt).strip()
                        if clean and not clean.isdigit() and len(clean) > 2 and not re.search(r'qualification|promotion|relegation|play.?off|criteria|ranking|seeding|pot', clean, re.IGNORECASE):
                            tname = clean
                            break
                    if tname:
                        teams_in_matrix.append(tname)
                        team_rows.append(r)

                if len(teams_in_matrix) >= 2:
                    for r_idx, r in enumerate(team_rows):
                        home_t = teams_in_matrix[r_idx]
                        cells = [c.get_text().strip() for c in r.find_all(['td', 'th'])]

                        matrix_cells = []
                        for c_txt in cells:
                            if c_txt in ['—', '–'] or re.search(rf'\d{{1,2}}\s+{MONTH_RE}', c_txt, re.IGNORECASE) or re.search(r'\d+\s*[\u2013\-]\s*\d+', c_txt):
                                matrix_cells.append(c_txt)

                        if len(matrix_cells) == len(teams_in_matrix):
                            for c_idx, val in enumerate(matrix_cells):
                                if c_idx != r_idx and val not in ['—', '–']:
                                    away_t = teams_in_matrix[c_idx]
                                    m_date = re.search(rf'(\d{{1,2}}\s+{MONTH_RE}(?:\s+\d{{4}})?|\d{{1,2}}[\s\u2013\-]+\d{{1,2}}\s+{MONTH_RE})', val, re.IGNORECASE)
                                    date_val = m_date.group(1) if m_date else val
                                    add_fixture(r, home_t, away_t, date_val, '', '', 'Strategy_5_CrossTable_MatchMatrix')
                                    matrix_count += 1
            logger.info("Strategy 5 matrix fixtures added: %d, total fixtures now: %d", matrix_count, len(fixtures))

            # --- Strategy 4: Matchday / Schedule Table Mining ---
            # For qualifying competitions (e.g. UEFA Euro 2028 qualifying) and league-format
            # tournaments where fixtures are expressed as matchday date-range rows
            # ("Matchday 1: 26-27 March 2027"). Each matchday row counts as a scheduled
            # fixture slot even when individual match teams are not yet defined.
            scheduled_matchdays = 0
            MATCHDAY_RE = re.compile(
                r'(?:Matchday|Match\s*day|Round|Gameweek|MD|Stage|Play.?off)\s*\d+',
                re.IGNORECASE
            )
            DATERANGE_RE = re.compile(
                rf'\d{{1,2}}[\s\u2013\-]+\d{{1,2}}\s+{MONTH_RE}\s+\d{{4}}'
                rf'|\d{{1,2}}\s+{MONTH_RE}\s+\d{{4}}',
                re.IGNORECASE
            )
            for tbl in soup.find_all('table', class_=re.compile(r'wikitable')):
                prev_h = tbl.find_previous(re.compile(r'^h[2-4]$'))
                section_hint = prev_h.get_text().strip().lower() if prev_h else ''
                if not re.search(r'schedule|calendar|fixture|matchday|format|group\s+stage|stage', section_hint):
                    continue
                for row in tbl.find_all('tr'):
                    rtxt = ' '.join(row.get_text().split())
                    if MATCHDAY_RE.search(rtxt) and DATERANGE_RE.search(rtxt):
                        scheduled_matchdays += 1

            # 4. Extract Scheduled Draw Date & Semantic Draw Completion Auditor
            draw_date_str = ''
            is_future_draw = False
            advancement_rules = 'De två eller fyra bästa lagen från varje grupp/pool går vidare till slutspel.'

            full_body_text = soup.get_text()

            m_future_draw = re.search(
                r'draw\s+(?:will\s+take\s+place|is\s+scheduled|is\s+set\s+to\s+take\s+place)'
                r'\s+(?:on\s+)?(\d{1,2}\s+' + MONTH_RE + r'\s+\d{4})',
                full_body_text, re.IGNORECASE
            )
            m_past_draw = re.search(
                r'draw\s+(?:was\s+held|took\s+place)\s+(?:on\s+)?'
                r'(\d{1,2}\s+' + MONTH_RE + r'\s+\d{4})',
                full_body_text, re.IGNORECASE
            )

            if m_future_draw:
                draw_date_str = m_future_draw.group(1)
                is_future_draw = True
            elif m_past_draw:
                draw_date_str = m_past_draw.group(1)

            if is_future_draw:
                draw_completed = False
            else:
                draw_completed = bool(
                    (len(groups) > 0 and sum(len(g.get('teams', [])) for g in groups) >= 4)
                    or len(fixtures) >= 4
                )

            # fixtures_completed = True when either real/placeholder match fixtures exist
            # OR a matchday schedule table defines at least 4 matchday date slots.
            fixtures_completed = bool(len(fixtures) >= 4 or scheduled_matchdays >= 4)

            # Flag whether all fixtures are placeholder-only (no real teams yet)
            fixtures_have_placeholders = bool(fixtures) and all(
                f.get('is_placeholder', False) for f in fixtures
            )

            # 5. Detect Knockout Stages
            knockout_stages = []
            sec_lines_lower = [s.lower() for s in sections]
            if any('round of 16' in s for s in sec_lines_lower):
                knockout_stages.append('Round of 16')
            if any('quarter' in s for s in sec_lines_lower):
                knockout_stages.append('Quarterfinals')
            if any('semi' in s for s in sec_lines_lower):
                knockout_stages.append('Semifinals')
            if any('final' in s or 'knockout' in s for s in sec_lines_lower):
                knockout_stages.append('Final')

            if not knockout_stages:
                knockout_stages = ['Quarterfinals', 'Semifinals', 'Final']

            for p in soup.find_all(['p', 'li']):
                ptxt = ' '.join(p.get_text().split())
                if ('advance' in ptxt.lower()
                        and ('group' in ptxt.lower() or 'pool' in ptxt.lower() or 'stage' in ptxt.lower())
                        and len(ptxt) < 220):
                    advancement_rules = ptxt
                    break

            total_extracted_teams = (
                len(extracted_teams_set)
                or sum(len(g.get('teams', [])) for g in groups)
                or teams_count
                or 16
            )

            return {
                'page_title': page_title,
                'wiki_url': f"https://en.wikipedia.org/wiki/{urllib.parse.quote(page_title.replace(' ', '_'))}",
                'sections': sections,
                'teams_count': total_extracted_teams,
                'groups_count': len(groups),
                'groups': groups,
                'fixtures': fixtures,
                'fixtures_count': len(fixtures),
                'scheduled_matchdays': scheduled_matchdays,
                'fixtures_have_placeholders': fixtures_have_placeholders,
                'draw_completed': draw_completed,
                'draw_date': draw_date_str,
                'advancement_rules': advancement_rules,
                'fixtures_completed': fixtures_completed,
                'knockout_stages': knockout_stages,
                'host_country': host_country,
                'tournament_start_date': start_date_extracted,
                'tournament_end_date': end_date_extracted,
                'start_date': start_date_extracted,
                'end_date': end_date_extracted,
                'logo_url': logo_url,
            }

        except Exception as e:
            logger.error(f"Error auditing Wikipedia page '{page_title}': {e}")
            return None
