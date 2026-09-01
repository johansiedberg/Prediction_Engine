import re
from tournament.country_registry import GLOBAL_COUNTRY_FLAG_MAP as COUNTRY_CODE_MAP

class BracketResolverService:
    @classmethod
    def resolve_team(cls, match, team_str, user_predictions=None):
        if not team_str:
            return {'name': '-', 'code': '', 'flag_url': '', 'display_name': '-'}
        
        team_str_clean = team_str.strip()

        # Check in-memory match cache when user_predictions is None
        if user_predictions is None:
            if not hasattr(match, '_resolved_team_cache'):
                match._resolved_team_cache = {}
            if team_str_clean in match._resolved_team_cache:
                return match._resolved_team_cache[team_str_clean]
        
        # 1. Match Winner/Loser knockout dependencies (e.g. "Winner Match 37", "Loser Match 49")
        m_kw = re.match(r'^(Winner|Loser|Vinnare|Förlorare)\s+(?:Match\s+)?(\d+)$', team_str_clean, re.IGNORECASE)
        if m_kw:
            role, match_num = m_kw.group(1).lower(), int(m_kw.group(2))
            matches_map = getattr(match.tournament, '_matches_by_number_dict', None)
            ref_match = matches_map.get(match_num) if matches_map is not None else match.tournament.matches.filter(match_number=match_num).first()
            if ref_match:
                ref_match.tournament = match.tournament
                winner_info = None
                loser_info = None

                if user_predictions and ref_match.id in user_predictions:
                    pred = user_predictions[ref_match.id]
                    if pred and pred.home_goals is not None and pred.away_goals is not None:
                        h_info = ref_match.get_home_team_info(user_predictions)
                        a_info = ref_match.get_away_team_info(user_predictions)
                        if pred.home_goals > pred.away_goals:
                            winner_info, loser_info = h_info, a_info
                        elif pred.away_goals > pred.home_goals:
                            winner_info, loser_info = a_info, h_info
                        else:
                            if pred.penalty_winner == a_info['name']:
                                winner_info, loser_info = a_info, h_info
                            else:
                                winner_info, loser_info = h_info, a_info

                if not winner_info and ref_match.is_finished and ref_match.home_goals is not None and ref_match.away_goals is not None:
                    if ref_match.home_goals > ref_match.away_goals:
                        winner_info = ref_match.get_home_team_info()
                        loser_info = ref_match.get_away_team_info()
                    elif ref_match.away_goals > ref_match.home_goals:
                        winner_info = ref_match.get_away_team_info()
                        loser_info = ref_match.get_home_team_info()
                    else:
                        box_data = ref_match.box_score_data or {}
                        pen_win = box_data.get('penalty_winner')
                        a_team = ref_match.get_away_team_info()
                        h_team = ref_match.get_home_team_info()
                        if pen_win and pen_win == a_team.get('name'):
                            winner_info, loser_info = a_team, h_team
                        else:
                            winner_info, loser_info = h_team, a_team

                target_info = winner_info if role in ('winner', 'vinnare') else loser_info
                if target_info and target_info.get('name') and target_info['name'] != '-':
                    real_name = target_info['name'].split(' (')[0].strip()
                    code = target_info.get('code', '') or COUNTRY_CODE_MAP.get(real_name.lower(), '')
                    flag = target_info.get('flag_url') or (f"https://flagcdn.com/w40/{code.lower()}.png" if code else '')
                    res = {
                        'name': real_name,
                        'code': code,
                        'flag_url': flag,
                        'display_name': f"{real_name} ({team_str_clean})"
                    }
                    if user_predictions is None:
                        match._resolved_team_cache[team_str_clean] = res
                    return res

        # 2. Match Group placeholder codes (e.g. "Winner Group B", "Runner-up Group A", "1st Group A", "2nd Group B", "A1", "1A", "B2")
        idx = None
        group_code = None

        m_winner = re.match(r'^(?:Winner|Vinnare|Ettan|1st|1:a)\s+(?:Group|Grupp)?\s*([A-L])$', team_str_clean, re.IGNORECASE)
        m_runner = re.match(r'^(?:Runner[- ]?up|Tvåan|2nd|2:a)\s+(?:Group|Grupp)?\s*([A-L])$', team_str_clean, re.IGNORECASE)
        m_full = re.match(r'^(\d+)(?:st|nd|rd|th|:a)?\s+(?:Group|Grupp)\s+([A-L])$', team_str_clean, re.IGNORECASE)
        
        if m_winner:
            idx, group_code = 1, m_winner.group(1).upper()
        elif m_runner:
            idx, group_code = 2, m_runner.group(1).upper()
        elif m_full:
            idx, group_code = int(m_full.group(1)), m_full.group(2).upper()
        else:
            m = re.match(r'^([A-L])([1-5])$', team_str_clean, re.IGNORECASE)
            if m:
                group_code, idx = m.group(1).upper(), int(m.group(2))
            else:
                m_rev = re.match(r'^([1-5])([A-L])$', team_str_clean, re.IGNORECASE)
                if m_rev:
                    idx, group_code = int(m_rev.group(1)), m_rev.group(2).upper()

        if group_code and idx is not None:
            if not hasattr(match.tournament, '_groups_by_code_dict'):
                match.tournament._groups_by_code_dict = {
                    (g.name.split()[-1].upper() if g.name else ''): g for g in match.tournament.tournament_groups.prefetch_related('teams').all()
                }
            group = match.tournament._groups_by_code_dict.get(group_code)
            if group:
                standings = group.get_standings(user_predictions)
                if standings and 0 <= idx - 1 < len(standings):
                    t_item = standings[idx - 1]
                    team_obj = t_item.get('team') if isinstance(t_item, dict) else t_item
                    t_name = team_obj.name if hasattr(team_obj, 'name') else str(team_obj)
                    t_code = getattr(team_obj, 'code', '') or ''
                    t_flag = getattr(team_obj, 'flag_url', '') or (f"https://flagcdn.com/w40/{t_code.lower()}.png" if t_code else '')
                    return {
                        'name': t_name,
                        'code': t_code,
                        'flag_url': t_flag,
                        'display_name': f"{t_name} ({team_str_clean})"
                    }
                
                teams = list(group.teams.all())
                if 0 <= idx - 1 < len(teams):
                    t = teams[idx - 1]
                    res = {
                        'name': t.name,
                        'code': t.code,
                        'flag_url': t.flag_url,
                        'display_name': f"{t.name} ({team_str_clean})"
                    }
                    if user_predictions is None:
                        match._resolved_team_cache[team_str_clean] = res
                    return res

        # 3. Third-place combination placeholders (e.g. "Third Group A/C/D", "3rd Group C/E/F/H/I", "3rd Group D/E/F", "3DEF", "3ABCD", "DEF3")
        group_letters = []
        m_third_slash = re.match(r'^(?:Third|Trean|3rd|3:a)\s+(?:Group|Grupp)?\s*([A-L](?:/[A-L])+)', team_str_clean, re.IGNORECASE)
        if m_third_slash:
            group_letters = [g.upper() for g in m_third_slash.group(1).split('/')]
        else:
            m_third_raw = re.match(r'^(?:3rd\s+(?:Group\s+)?)?([A-L](?:/[A-L])+)', team_str_clean, re.IGNORECASE)
            if m_third_raw:
                group_letters = [g.upper() for g in m_third_raw.group(1).split('/')]
            else:
                m_third = re.match(r'^(3?([A-L]{2,6})3?)$', team_str_clean, re.IGNORECASE)
                if m_third:
                    group_letters = list(m_third.group(2).upper())

        if group_letters:
            if not hasattr(match.tournament, '_groups_by_code_dict'):
                match.tournament._groups_by_code_dict = {
                    (g.name.split()[-1].upper() if g.name else ''): g for g in match.tournament.tournament_groups.prefetch_related('teams').all()
                }
            
            # Check official UEFA 24-team combination table if tournament has 6 groups A-F
            uefa_map = {
                'ABCD': {'3C/D/E/F': 'C', '3A/C/D/E/F': 'D', '3A/B/C/E/F': 'A', '3A/B/D/E/F': 'B'},
                'ABCE': {'3C/D/E/F': 'C', '3A/C/D/E/F': 'A', '3A/B/C/E/F': 'B', '3A/B/D/E/F': 'E'},
                'ABCF': {'3C/D/E/F': 'C', '3A/C/D/E/F': 'A', '3A/B/C/E/F': 'B', '3A/B/D/E/F': 'F'},
                'ABDE': {'3C/D/E/F': 'D', '3A/C/D/E/F': 'A', '3A/B/C/E/F': 'B', '3A/B/D/E/F': 'E'},
                'ABDF': {'3C/D/E/F': 'D', '3A/C/D/E/F': 'A', '3A/B/C/E/F': 'B', '3A/B/D/E/F': 'F'},
                'ABEF': {'3C/D/E/F': 'E', '3A/C/D/E/F': 'A', '3A/B/C/E/F': 'B', '3A/B/D/E/F': 'F'},
                'ACDE': {'3C/D/E/F': 'C', '3A/C/D/E/F': 'D', '3A/B/C/E/F': 'A', '3A/B/D/E/F': 'E'},
                'ACDF': {'3C/D/E/F': 'C', '3A/C/D/E/F': 'D', '3A/B/C/E/F': 'A', '3A/B/D/E/F': 'F'},
                'ACEF': {'3C/D/E/F': 'C', '3A/C/D/E/F': 'A', '3A/B/C/E/F': 'F', '3A/B/D/E/F': 'E'},
                'ADEF': {'3C/D/E/F': 'D', '3A/C/D/E/F': 'A', '3A/B/C/E/F': 'F', '3A/B/D/E/F': 'E'},
                'BCDE': {'3C/D/E/F': 'C', '3A/C/D/E/F': 'D', '3A/B/C/E/F': 'B', '3A/B/D/E/F': 'E'},
                'BCDF': {'3C/D/E/F': 'C', '3A/C/D/E/F': 'D', '3A/B/C/E/F': 'B', '3A/B/D/E/F': 'F'},
                'BCEF': {'3C/D/E/F': 'E', '3A/C/D/E/F': 'C', '3A/B/C/E/F': 'B', '3A/B/D/E/F': 'F'},
                'BDEF': {'3C/D/E/F': 'E', '3A/C/D/E/F': 'D', '3A/B/C/E/F': 'B', '3A/B/D/E/F': 'F'},
                'CDEF': {'3C/D/E/F': 'C', '3A/C/D/E/F': 'D', '3A/B/C/E/F': 'F', '3A/B/D/E/F': 'E'},
            }

            norm_slash_key = '3' + '/'.join(group_letters)
            all_third_teams = []
            for g_code, grp in match.tournament._groups_by_code_dict.items():
                st = grp.get_standings(user_predictions)
                if len(st) >= 3:
                    item = st[2]
                    all_third_teams.append({
                        'group_code': g_code,
                        'team': item['team'],
                        'points': item.get('points', 0),
                        'gd': item.get('gd', 0),
                        'gf': item.get('gf', 0),
                        'won': item.get('won', 0)
                    })

            all_third_teams.sort(key=lambda x: (x['points'], x['gd'], x['gf'], x['won']), reverse=True)
            top_4_groups = sorted([x['group_code'] for x in all_third_teams[:4]])
            combo_key = ''.join(top_4_groups)

            chosen_team = None
            if combo_key in uefa_map and norm_slash_key in uefa_map[combo_key]:
                chosen_group_code = uefa_map[combo_key][norm_slash_key]
                matched_item = next((x for x in all_third_teams if x['group_code'] == chosen_group_code), None)
                if matched_item:
                    chosen_team = matched_item['team']

            if not chosen_team:
                thirds = [x for x in all_third_teams if x['group_code'] in group_letters]
                if thirds:
                    chosen_team = thirds[0]['team']

            if chosen_team:
                t = chosen_team
                res = {
                    'name': t.name,
                    'code': t.code,
                    'flag_url': t.flag_url,
                    'display_name': f"{t.name} ({team_str_clean})"
                }
                if user_predictions is None:
                    match._resolved_team_cache[team_str_clean] = res
                return res

        # 3. Direct Team model match in tournament (Zero-query in-memory lookup)
        if not hasattr(match.tournament, '_teams_by_name_dict'):
            match.tournament._teams_by_name_dict = {t.name.strip().lower(): t for t in match.tournament.teams.all()}
        
        base_name = team_str_clean.split(' (')[0].strip()
        team = match.tournament._teams_by_name_dict.get(team_str_clean.lower()) or match.tournament._teams_by_name_dict.get(base_name.lower())
        if team:
            t_code = team.code or COUNTRY_CODE_MAP.get(team.name.strip().lower(), '')
            t_flag = team.flag_url or (f"https://flagcdn.com/w40/{t_code.lower()}.png" if t_code else '')
            res = {
                'name': team.name,
                'code': t_code,
                'flag_url': t_flag,
                'display_name': team_str_clean
            }
            if user_predictions is None:
                match._resolved_team_cache[team_str_clean] = res
            return res
        
        # 4. Fallback using country code map
        clean_key = base_name.lower()
        if clean_key in COUNTRY_CODE_MAP:
            code = COUNTRY_CODE_MAP[clean_key]
            res = {
                'name': base_name,
                'code': code,
                'flag_url': f"https://flagcdn.com/w40/{code}.png",
                'display_name': team_str_clean
            }
            if user_predictions is None:
                match._resolved_team_cache[team_str_clean] = res
            return res

        return {
            'name': team_str_clean,
            'code': '',
            'flag_url': '',
            'display_name': team_str_clean
        }

    @classmethod
    def resolve_actual_knockout_team(cls, match, team_str, user_actual_predictions=None):
        """
        Resolves team info for the Actual Knockout phase:
        - Group placeholders (e.g. 1A, 2B, 3C/E/F) are resolved strictly from the ACTUAL completed group standings.
        - Previous knockout round dependencies (e.g. Winner Match 37) resolve from user_actual_predictions if available.
        """
        if not team_str:
            return {'name': '-', 'code': '', 'flag_url': '', 'display_name': '-'}

        team_str_clean = team_str.strip()

        # 1. Match Winner/Loser knockout dependencies (e.g. "Winner Match 37", "Loser Match 49")
        m_kw = re.match(r'^(Winner|Loser|Vinnare|Förlorare)\s+(?:Match\s+)?(\d+)$', team_str_clean, re.IGNORECASE)
        if m_kw:
            role, match_num = m_kw.group(1).lower(), int(m_kw.group(2))
            matches_map = getattr(match.tournament, '_matches_by_number_dict', None)
            ref_match = matches_map.get(match_num) if matches_map is not None else match.tournament.matches.filter(match_number=match_num).first()
            if ref_match:
                ref_match.tournament = match.tournament
                winner_info = None
                loser_info = None

                if user_actual_predictions and ref_match.id in user_actual_predictions:
                    pred = user_actual_predictions[ref_match.id]
                    if pred and pred.home_goals is not None and pred.away_goals is not None:
                        h_info = cls.resolve_actual_knockout_team(ref_match, ref_match.home_team, user_actual_predictions)
                        a_info = cls.resolve_actual_knockout_team(ref_match, ref_match.away_team, user_actual_predictions)
                        if pred.home_goals > pred.away_goals:
                            winner_info, loser_info = h_info, a_info
                        elif pred.away_goals > pred.home_goals:
                            winner_info, loser_info = a_info, h_info
                        else:
                            if pred.penalty_winner == a_info['name']:
                                winner_info, loser_info = a_info, h_info
                            else:
                                winner_info, loser_info = h_info, a_info

                if not winner_info and ref_match.is_finished and ref_match.home_goals is not None and ref_match.away_goals is not None:
                    h_info = cls.resolve_actual_knockout_team(ref_match, ref_match.home_team)
                    a_info = cls.resolve_actual_knockout_team(ref_match, ref_match.away_team)
                    if ref_match.home_goals > ref_match.away_goals:
                        winner_info, loser_info = h_info, a_info
                    elif ref_match.away_goals > ref_match.home_goals:
                        winner_info, loser_info = a_info, h_info
                    else:
                        box_data = ref_match.box_score_data or {}
                        pen_win = box_data.get('penalty_winner')
                        if pen_win and pen_win == a_info.get('name'):
                            winner_info, loser_info = a_info, h_info
                        else:
                            winner_info, loser_info = h_info, a_info

                target_info = winner_info if role in ('winner', 'vinnare') else loser_info
                if target_info and target_info.get('name') and target_info['name'] != '-':
                    real_name = target_info['name'].split(' (')[0].strip()
                    code = target_info.get('code', '') or COUNTRY_CODE_MAP.get(real_name.lower(), '')
                    flag = target_info.get('flag_url') or (f"https://flagcdn.com/w40/{code.lower()}.png" if code else '')
                    return {
                        'name': real_name,
                        'code': code,
                        'flag_url': flag,
                        'display_name': f"{real_name} ({team_str_clean})"
                    }

        # 2. For group placeholders and direct teams in the Actual Knockout tree, resolve using ACTUAL group results (user_predictions=None)
        return cls.resolve_team(match, team_str_clean, user_predictions=None)
