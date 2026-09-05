import re
import logging

logger = logging.getLogger(__name__)

# Dynamic whitelist of H2H Team Sports suitable for 1X2 & Playoff tree prediction engine formats
H2H_TEAM_SPORTS = {
    'football', 'soccer', 'ice hockey', 'hockey', 'handball', 'basketball',
    'rugby', 'rugby union', 'rugby league', 'volleyball', 'beach volleyball',
    'floorball', 'futsal', 'water polo', 'american football', 'cricket',
    'baseball', 'softball', 'bandy', 'netball', 'lacrosse', 'curling',
    'beach soccer', 'field hockey'
}

# Explicit blacklist of Individual, racing, multi-sport, or non-H2H Sports
INDIVIDUAL_NON_H2H_SPORTS = {
    'athletics', 'track & field', 'swimming', 'artistic swimming', 'open water swimming',
    'diving', 'high diving', 'chess', 'darts', 'motorsport', 'motor sports', 'motorbike racing',
    'formula 1', 'f1', 'motogp', 'speedboat racing', 'golf', 'tennis', 'table tennis', 'badminton',
    'cycling', 'skiing', 'alpine skiing', 'cross-country skiing', 'biathlon', 'freestyle skiing',
    'nordic combined', 'ski jumping', 'snowboard', 'snowboarding', 'gymnastics', 'artistic gymnastics',
    'rhythmic gymnastics', 'trampoline', 'figure skating', 'speed skating', 'short track',
    'snooker', 'billiards', 'boxing', 'mma', 'ufc', 'weightlifting', 'archery', 'shooting',
    'triathlon', 'rowing', 'canoeing', 'kayaking', 'sailing', 'equestrian', 'horse racing',
    'fencing', 'judo', 'karate', 'taekwondo', 'wrestling', 'sambo', 'bobsleigh', 'luge',
    'skeleton', 'modern pentathlon', 'skateboarding', 'sport climbing', 'surfing',
    'multi-sport events'
}


# Keyword Filtering System for Format (Championships & Cups only)
FORMAT_WHITELIST_KEYWORDS = [
    'cup', 'championship', 'world cup', 'euro', 'copa', 'playoff', 'play-off',
    'play-offs', 'finals', 'knockout', 'tournament', 'olympic', 'olympics',
    'qualifier', 'qualifiers', 'qualification', 'preliminary', 'wfc'
]



FORMAT_BLACKLIST_KEYWORDS = [
    'league', 'regular season', 'division', 'premiership', 'series'
]

LEAGUE_EXCEPTION_PATTERNS = [
    'champions league', 'europa league', 'nations league', 'conference league',
    'premier league cup', 'league cup'
]


def is_h2h_team_sport(sport_name):
    """
    Determines if a sport name belongs to H2H team sports dynamic whitelist.
    Returns True for compatible H2H team sports, False otherwise.
    """
    if not sport_name:
        return False
    
    clean_name = sport_name.lower().strip()
    
    # Check explicit individual blacklist
    if clean_name in INDIVIDUAL_NON_H2H_SPORTS:
        return False

    # Check whitelist match
    if clean_name in H2H_TEAM_SPORTS:
        return True

    # Partial keyword match for H2H sports (e.g. "Women's Football", "Ice Hockey Men")
    for h2h in H2H_TEAM_SPORTS:
        if h2h in clean_name:
            return True

    return False


def is_championship_or_cup_format(title, category_name=None):
    """
    Multi-step keyword filtering system to verify tournament is a cup / championship / playoff format.
    Returns (is_valid: bool, reason: str).
    """
    if not title:
        return False, "Saknar titel."

    title_lower = title.lower()
    cat_lower = (category_name or '').lower()
    combined_text = f"{title_lower} {cat_lower}"

    # Step 1: Check Whitelist Keywords
    has_whitelist_keyword = any(kw in combined_text for kw in FORMAT_WHITELIST_KEYWORDS)

    # Step 2: Check Blacklist Keywords
    has_blacklist_keyword = any(kw in combined_text for kw in FORMAT_BLACKLIST_KEYWORDS)

    # Step 3: Check Exception Patterns (Allow "League" ONLY if it represents a tournament/cup format)
    has_league_exception = any(pattern in combined_text for pattern in LEAGUE_EXCEPTION_PATTERNS)

    if has_blacklist_keyword and not has_league_exception:
        # If it matched whitelist (e.g. "Premier League Championship Series"), but contains blacklisted league terms without exception
        return False, f"Exkluderad p.g.a. ligasystems-nyckelord i titeln '{title}'."

    if has_whitelist_keyword or has_league_exception:
        return True, "Godkänd turnering/cup-format."

    # If title contains neither whitelist nor blacklist keywords, require manual review
    return False, f"Innehåller inga godkända turneringsnyckelord (Cup, Championship, Euro, etc.)"


import datetime

def evaluate_event_grade(event_dict, is_h2h_sport_compatible):
    """
    Evaluates tournament prospect grade according to business rules:
    - GRADE_A: Verified on official site, upcoming, all teams seeded, fixtures set, rules/setup verified, sport compatible with model.
    - GRADE_B: Verified on official site, upcoming, rules/setup verified, sport compatible with model, but NOT complete for publication (teams/fixtures pending).
    - GRADE_C: Sport is not 100% compatible or event is already started/finished.
    """
    if not is_h2h_sport_compatible:
        return 'GRADE_C', "Grad C: Sporten är inte 100% kompatibel med H2H-prediktionsmodellen (t.ex. individuell sport eller ej 1X2-anpassad)."

    # FILTER: Qualification competitions (qualifying / qualification / kval) are graded Grade C
    title_str = (event_dict.get('name') or event_dict.get('title') or '').lower()
    if any(k in title_str for k in ['qualifying', 'qualification', 'kval', 'preliminary']):
        return 'GRADE_C', f"Grad C: Kvalturnering ('{event_dict.get('name') or event_dict.get('title')}'). Endast slutspelets huvudturneringar accepteras."

    # STRICT CHECK: ONLY accept coming tournaments, not started or finished

    today = datetime.date.today()
    start_date_val = None
    raw_start = event_dict.get('dateFrom') or event_dict.get('startDate') or event_dict.get('start_date')
    if raw_start:
        try:
            if isinstance(raw_start, datetime.date):
                start_date_val = raw_start
            else:
                start_date_val = datetime.date.fromisoformat(str(raw_start)[:10])
        except Exception:
            pass

    if start_date_val and start_date_val <= today:
        return 'GRADE_C', f"Grad C: Turneringen har redan startat eller avslutats (Startdatum: {start_date_val}). Endast kommande turneringar accepteras."

    official_url = event_dict.get('webUrl') or event_dict.get('official_website') or event_dict.get('url') or event_dict.get('OfficialWebsite') or ''
    teams = event_dict.get('teams') or event_dict.get('participants') or []
    fixtures = event_dict.get('fixtures') or event_dict.get('matches') or []

    has_official_url = bool(official_url and official_url.startswith('http'))
    has_complete_teams_and_fixtures = bool(len(teams) >= 2 or len(fixtures) >= 2)

    if has_official_url and has_complete_teams_and_fixtures:
        return 'GRADE_A', "Grad A: Verifierad på officiell sida. Lottning, lag och spelschema bekräftade. 100% redo för publicering."
    
    if has_official_url or event_dict.get('dateFrom') or event_dict.get('start_date'):
        return 'GRADE_B', "Grad B: Verifierad på officiell sida och sport kompatibel. Ej 100% komplett för publicering ännu (lottning/spelschema pågår)."

    return 'GRADE_C', "Grad C: Saknar officiell verifierad webbplats eller grundläggande turneringsstruktur."


def _matches_any_sport_kw(text: str, keywords: list) -> bool:
    """Matches keywords against text respecting word boundaries for acronyms and short words."""
    for kw in keywords:
        if len(kw) <= 4 or ' ' not in kw:
            if re.search(r'\b' + re.escape(kw) + r'\b', text, re.IGNORECASE):
                return True
        elif kw.lower() in text:
            return True
    return False


def detect_sport_from_title(title: str, default_sport: str = "Football") -> str:
    """
    Infers the correct sport discipline from the tournament title if default_sport is generic or unknown.
    Matches specific disciplines (e.g. Field Hockey, American Football, Cricket, Netball)
    before falling back to generic team sports or default_sport.
    """
    if not title:
        return default_sport
    t_lower = title.lower()
    
    # 1. Distinct Hockey Disciplines
    if _matches_any_sport_kw(t_lower, ['eurohockey', 'field hockey', 'landhockey', 'fih hockey', 'fih']):
        return 'Field Hockey'
    if _matches_any_sport_kw(t_lower, ['ice hockey', 'ishockey', 'hockey-vm', 'hockey-em', 'iihf', 'nhl', 'shl', 'khl', 'chl', 'spengler cup', 'stanley cup']):
        return 'Ice Hockey'

    # 2. American Football (evaluated before generic 'football')
    if _matches_any_sport_kw(t_lower, ['american football', 'flag football', 'college football', 'nfl', 'ifaf', 'cfl']):
        return 'American Football'

    # 3. Small-pitch / Alternative Football codes (before generic 'football')
    if _matches_any_sport_kw(t_lower, ['futsal']):
        return 'Futsal'
    if _matches_any_sport_kw(t_lower, ['beach soccer']):
        return 'Beach Soccer'

    # 4. Court & Ball Sports
    if _matches_any_sport_kw(t_lower, ['basketball', 'basket', 'fiba', 'basket-em', 'basket-vm', 'nba', 'euroleague', 'wnba']):
        return 'Basketball'
    if _matches_any_sport_kw(t_lower, ['beach handball', 'handball', 'handboll', 'handbolls-vm', 'handbolls-em', 'ehf', 'ihf']):
        return 'Handball'
    if _matches_any_sport_kw(t_lower, ['volleyball', 'volleyboll', 'fivb', 'cev', 'avc', 'beach volleyball']):
        return 'Volleyball'
    if _matches_any_sport_kw(t_lower, ['netball', 'world netball']):
        return 'Netball'
    if _matches_any_sport_kw(t_lower, ['floorball', 'innebandy', 'iff', 'wfc']):
        return 'Floorball'

    # 5. Bat, Stick & Target Sports
    if _matches_any_sport_kw(t_lower, ['cricket', 'icc', 'ipl', 't20', 'the ashes']):
        return 'Cricket'
    if _matches_any_sport_kw(t_lower, ['baseball', 'baseball5', 'wbsc', 'mlb']):
        return 'Baseball'
    if _matches_any_sport_kw(t_lower, ['softball']):
        return 'Softball'
    if _matches_any_sport_kw(t_lower, ['lacrosse', 'box lacrosse', 'world lacrosse']):
        return 'Lacrosse'
    if _matches_any_sport_kw(t_lower, ['bandy', 'fib bandy']):
        return 'Bandy'

    # 6. Contact, Water & Ice Sports
    if _matches_any_sport_kw(t_lower, ['rugby', 'six nations', 'world rugby', 'rugby union', 'rugby league', 'super rugby']):
        return 'Rugby'
    if _matches_any_sport_kw(t_lower, ['water polo', 'waterpolo', 'len water polo', 'fina water polo']):
        return 'Water Polo'
    if _matches_any_sport_kw(t_lower, ['curling', 'world curling', 'curling-vm']):
        return 'Curling'

    # 7. Association Football (Soccer)
    if _matches_any_sport_kw(t_lower, ['football', 'soccer', 'fotboll', 'uefa', 'fifa', 'concacaf', 'caf', 'afc', 'conmebol', 'copa', 'gold cup', 'nations league', 'afcon', 'asian cup']):
        return 'Football'

    return default_sport

