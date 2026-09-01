"""
special_edition_reporter.py
---------------------------
Reporter and narrative generation engine for Gazzetta Round Special Editions (v2.0).

Handles both:
1. PREDICTIONS_LOCK (Round 1 / Kickoff Milestone):
   - 🔮 Orakeltipset: Tre Profeter Synar Kupongerna (Vetenskapsmannen, Experten, Kaospiloten)
   - 👥 Konsensusfällan: Gruppens Kollektiva Masspsykos
   - 🐺 Ensamvargarna: De Isolerade Hävstångsdragen
   - ⚽ Kupongernas Karaktär: Betongförsvar mot Romantisk Champagne
   - 📋 Omgångens Kupongbikt: Spelare för Spelare
2. ROUND_CONCLUSION & STAGE MILESTONES (In-progress group/knockout rounds):
   - 👑 HEADLINE 1: Toppstrid, Rivalitet & Banter
   - 🔥 HEADLINE 2: Framstående Resultat & Spikar
   - 📉 HEADLINE 3: Omgångens Tunga Bakslag & Faller
   - 🤖 AI-ANALYS: Framtida Utsikter & Hot
3. TOURNAMENT_FINALE (Grand Final):
   - 🏆 Guldets Väg & Podiets Slutstrid
   - 🪵 Träsleven & Skammens Bokslut
   - 🎖️ Skuggpriserna (Turknutten, Teoretiske Mästaren, Kaoskungen)
   - 📜 Almanackans Slutdom & Det Sista Slutbetyget
"""

import math
import random
from collections import Counter
from django.db.models import Count, Q
from tournament.models import (
    Tournament, Match, MatchPrediction, DailyGazette, RoundLeaderboardSnapshot, TournamentSubmission
)
from tournament.editorial_engine.journalist import BEHAVIOR_DESCRIPTIONS
from tournament.editorial_engine.compiler import load_player_personas, find_persona_for_player
from tournament.editorial_engine.posture_engine import resolve_portrait_url, resolve_posture_path

MILESTONE_ROUNDS = {
    1: {'name': 'Alla Tips Verifierade', 'code': 'VERIFIED'},
    2: {'name': 'Gruppomgång 1 Spelad', 'code': 'GROUP_1'},
    3: {'name': 'Gruppomgång 2 Spelad', 'code': 'GROUP_2'},
    4: {'name': 'Gruppomgång 3 Spelad', 'code': 'GROUP_3'},
    5: {'name': 'Åttondelsfinaler Spelade', 'code': 'R16'},
    6: {'name': 'Kvartsfinaler Spelade', 'code': 'QF'},
    7: {'name': 'Semifinaler Spelade', 'code': 'SF'},
    8: {'name': 'Bronsmatch Spelad', 'code': 'BRONZE'},
    9: {'name': 'Final Spelad', 'code': 'FINAL'},
    10: {'name': 'Slutmagasin & Mästaren Kronad', 'code': 'RECAP'},
}


def is_toarps_pool(tournament: Tournament) -> bool:
    """Returns True strictly if pool/tournament belongs to Toarps Herrklubb."""
    if not tournament:
        return False
    t_name = getattr(tournament, 'name', '').lower()
    if "toarp" in t_name:
        return True
    if hasattr(tournament, 'leagues') and tournament.leagues.filter(name__icontains='toarp').exists():
        return True
    return False


def get_player_nick_or_name(player, personas_list=None, is_toarp=False) -> str:
    """Returns persona nickname strictly for Toarp, else clean display/first name."""
    if not player:
        return "Tipparen"
    p_name = player.get_full_name() if hasattr(player, 'get_full_name') and player.get_full_name() else (
        f"{player.first_name} {player.last_name}".strip() if getattr(player, 'first_name', '') else getattr(player, 'email', 'Spelare')
    )
    first_or_full = p_name.split()[0] if ' ' in p_name else p_name
    if is_toarp and personas_list:
        p_match = find_persona_for_player(p_name, personas_list)
        if p_match:
            nicks = p_match.get('nicknames', [])
            if nicks and nicks[0]:
                return nicks[0]
    return first_or_full


def get_player_behavior_dynamic(player_name: str, role: str = 'LEADER') -> str:
    """Returns specialized Toarp behavior description if defined, else dynamic sports behavior."""
    if player_name in BEHAVIOR_DESCRIPTIONS:
        return BEHAVIOR_DESCRIPTIONS[player_name]
    
    if role == 'LEADER':
        return random.choice([
            "studerade kalkylerna med absolut lugn och självförtroende efter en taktisk fullträff",
            "manövrerade fältet med kirurgisk precision och dominerade poängfördelningen",
            "kontrollerade händelserna från toppen med stoisk disciplin och kyliga spikar"
        ])
    elif role == 'RUNNER_UP':
        return random.choice([
            "pressade på med aggressiva taktiska drag för att ta över förstaplatsen",
            "vägrade vika en tum i toppstriden och höll jakten vid liv med modiga resultatval",
            "vässade formen inför nästa omgång för att sätta maximal press på ledartröjan"
        ])
    else: # FALLER / STRUGGLER
        return random.choice([
            "sökte febrilt efter förklaringar till omgångens tunga stolpe-ut-resultat",
            "tvingades konstatera att marginalerna inte var på rätt sida under kvällens drabbningar",
            "laddar om för en omedelbar taktisk revansch efter ett oväntat poängtapp"
        ])


def get_matches_up_to_round(tournament: Tournament, round_num: int = None):
    """Returns the set of matches played up to a given round milestone."""
    if not tournament:
        return Match.objects.none()
    if round_num is None or round_num >= 999:
        return Match.objects.filter(tournament=tournament, is_finished=True)
    if round_num == 1:
        return Match.objects.none()
    elif round_num == 2:
        # Group Round 1: first 2 matches per group
        match_ids = []
        for grp in tournament.tournament_groups.all():
            grp_m = list(grp.matches.filter(is_finished=True).order_by('match_number', 'id')[:2])
            match_ids.extend([m.id for m in grp_m])
        return Match.objects.filter(id__in=match_ids)
    elif round_num == 3:
        # Group Round 2: first 4 matches per group
        match_ids = []
        for grp in tournament.tournament_groups.all():
            grp_m = list(grp.matches.filter(is_finished=True).order_by('match_number', 'id')[:4])
            match_ids.extend([m.id for m in grp_m])
        return Match.objects.filter(id__in=match_ids)
    elif round_num == 4:
        # Group Stage complete (all 36 group matches)
        return Match.objects.filter(tournament=tournament, group__isnull=False, is_finished=True)
    elif round_num == 11:
        # Round of 16 completed: all group matches + R16
        r16 = tournament.knockout_stages.filter(order=1).first()
        r16_ids = list(r16.matches.values_list('id', flat=True)) if r16 else []
        grp_ids = list(Match.objects.filter(tournament=tournament, group__isnull=False).values_list('id', flat=True))
        return Match.objects.filter(id__in=grp_ids + r16_ids, is_finished=True)
    elif round_num == 12:
        # Quarterfinals completed: all group matches + R16 + QF
        r16 = tournament.knockout_stages.filter(order=1).first()
        qf = tournament.knockout_stages.filter(order=2).first()
        ko_ids = []
        if r16:
            ko_ids.extend(list(r16.matches.values_list('id', flat=True)))
        if qf:
            ko_ids.extend(list(qf.matches.values_list('id', flat=True)))
        grp_ids = list(Match.objects.filter(tournament=tournament, group__isnull=False).values_list('id', flat=True))
        return Match.objects.filter(id__in=grp_ids + ko_ids, is_finished=True)
    elif round_num == 13:
        # Semifinals completed: all group matches + R16 + QF + SF
        ko_stages = list(tournament.knockout_stages.filter(order__lte=3))
        ko_ids = []
        for ks in ko_stages:
            ko_ids.extend(list(ks.matches.values_list('id', flat=True)))
        grp_ids = list(Match.objects.filter(tournament=tournament, group__isnull=False).values_list('id', flat=True))
        return Match.objects.filter(id__in=grp_ids + ko_ids, is_finished=True)
    else:
        return Match.objects.filter(tournament=tournament, is_finished=True)


def get_matches_for_single_round(tournament: Tournament, round_num: int):
    """Returns only the matches played within this specific round slice."""
    if not tournament:
        return Match.objects.none()
    if round_num == 2:
        # Group Round 1: first 2 matches per group
        match_ids = []
        for grp in tournament.tournament_groups.all():
            grp_m = list(grp.matches.filter(is_finished=True).order_by('match_number', 'id')[:2])
            match_ids.extend([m.id for m in grp_m])
        return Match.objects.filter(id__in=match_ids)
    elif round_num == 3:
        # Group Round 2: matches 3 & 4 per group
        match_ids = []
        for grp in tournament.tournament_groups.all():
            grp_m = list(grp.matches.filter(is_finished=True).order_by('match_number', 'id')[2:4])
            match_ids.extend([m.id for m in grp_m])
        return Match.objects.filter(id__in=match_ids)
    elif round_num == 4:
        # Group Round 3: matches 5 & 6 per group
        match_ids = []
        for grp in tournament.tournament_groups.all():
            grp_m = list(grp.matches.filter(is_finished=True).order_by('match_number', 'id')[4:6])
            match_ids.extend([m.id for m in grp_m])
        return Match.objects.filter(id__in=match_ids)
    elif round_num == 11:
        # Round of 16 matches
        r16 = tournament.knockout_stages.filter(order=1).first()
        return r16.matches.filter(is_finished=True) if r16 else Match.objects.none()
    elif round_num == 12:
        # Quarterfinals matches
        qf = tournament.knockout_stages.filter(order=2).first()
        return qf.matches.filter(is_finished=True) if qf else Match.objects.none()
    elif round_num == 13:
        # Semifinals matches
        sf = tournament.knockout_stages.filter(order=3).first()
        return sf.matches.filter(is_finished=True) if sf else Match.objects.none()
    else:
        return Match.objects.filter(tournament=tournament, is_finished=True)


def _build_featured_players_json(current_lb: list, personas_list: list) -> list:
    """
    Builds the featured_players_json payload for the Special Edition gazette banner.
    Returns up to 3 player dicts: [leader, runner-up, bottom-faller] each with:
      - name       : display name / nickname (Toarp persona)
      - nick       : short nickname
      - role       : LEADER | RUNNER_UP | FALLER
      - portrait_url : /static/... URL to the real portrait photo (or '' if missing)
    """
    result = []
    roles = [
        (0, 'LEADER'),
        (1, 'RUNNER_UP'),
        (-1, 'FALLER'),   # last-place player
    ]
    for idx, role in roles:
        entry = current_lb[idx] if (abs(idx) < len(current_lb)) else None
        if not entry:
            continue
        user = entry.get('user')
        full_name = user.get_full_name().strip() if user and user.get_full_name() else entry.get('name', '')
        nick = entry.get('name', full_name)  # already persona-resolved nick from calculate_leaderboard

        # Resolve portrait photo from persona definition
        persona = find_persona_for_player(full_name, personas_list)
        avatar_filename = persona.get('avatar_filename', '') if persona else ''
        portrait_url = resolve_portrait_url(full_name, avatar_filename)

        # Resolve expressive full-body posture for Special Edition composite
        initials = persona.get('initials', '') if persona else ''
        role_postures = {
            'LEADER': 'Bane',
            'RUNNER_UP': 'Fist',
            'FALLER': 'Me',
        }
        posture_name = role_postures.get(role, 'Analyst')
        posture_url = resolve_posture_path(initials, posture_name) if initials else ''

        result.append({
            'name': nick,
            'nick': nick,
            'full_name': full_name,
            'role': role,
            'posture': posture_name,
            'posture_url': posture_url,
            'portrait_url': portrait_url,
            'points': entry.get('points', 0),
            'rank': entry.get('rank', idx + 1),
        })
    return result



class SpecialEditionReporter:


    @classmethod
    def get_player_name(cls, user, is_toarp=False, personas_list=None) -> str:
        """Helper to get player display name."""
        return get_player_nick_or_name(user, personas_list, is_toarp=is_toarp)

    @classmethod
    def calculate_leaderboard(cls, tournament: Tournament, round_num: int = None, is_toarp=False, personas_list=None) -> list:
        """Computes current leaderboard list with player info, rank, points, and exact score hits."""
        from tournament.services.scoring import calc_pred_points
        players = list(tournament.players.all())
        if not players:
            from django.contrib.auth.models import User
            pred_p_ids = MatchPrediction.objects.filter(match__tournament=tournament).values_list('player_id', flat=True).distinct()
            players = list(User.objects.filter(id__in=pred_p_ids))

        point_system = getattr(tournament, 'point_system', None)
        relevant_matches = get_matches_up_to_round(tournament, round_num)
        
        leaderboard = []
        for p in players:
            p_preds = MatchPrediction.objects.filter(player=p, match__in=relevant_matches)
            pts = 0
            exact_count = 0
            
            for pred in p_preds:
                m = pred.match
                pts += calc_pred_points(pred, m, point_system)
                if m.home_goals is not None and m.away_goals is not None:
                    if pred.home_goals == m.home_goals and pred.away_goals == m.away_goals:
                        exact_count += 1

            leaderboard.append({
                'user': p,
                'name': cls.get_player_name(p, is_toarp=is_toarp, personas_list=personas_list),
                'points': pts,
                'exact_count': exact_count,
            })

        leaderboard.sort(key=lambda x: (x['points'], x['exact_count']), reverse=True)
        for idx, entry in enumerate(leaderboard, 1):
            entry['rank'] = idx

        return leaderboard

    @classmethod
    def snapshot_leaderboard(cls, tournament: Tournament, round_num: int, round_name: str, is_toarp=False, personas_list=None) -> list:
        """Saves current leaderboard state to RoundLeaderboardSnapshot for historical comparison."""
        lb = cls.calculate_leaderboard(tournament, round_num=round_num, is_toarp=is_toarp, personas_list=personas_list)
        snapshots = []
        for entry in lb:
            snap, _ = RoundLeaderboardSnapshot.objects.update_or_create(
                tournament=tournament,
                round_number=round_num,
                player=entry['user'],
                defaults={
                    'round_name': round_name,
                    'rank': entry['rank'],
                    'points': entry['points'],
                    'exact_scores_count': entry['exact_count'],
                }
            )
            snapshots.append(snap)
        return lb

    @classmethod
    def analyze_round_changes(cls, tournament: Tournament, round_num: int, current_lb: list) -> dict:
        """Compares current round leaderboard vs previous round snapshot to find climbers and fallers."""
        prev_round_num = round_num - 1
        prev_snapshots = {
            s.player_id: s for s in RoundLeaderboardSnapshot.objects.filter(tournament=tournament, round_number=prev_round_num)
        }

        changes = []
        for entry in current_lb:
            p_id = entry['user'].id
            prev = prev_snapshots.get(p_id)
            if prev:
                rank_change = prev.rank - entry['rank'] # Positive = climbed, Negative = fell
                pts_gained = entry['points'] - prev.points
            else:
                rank_change = 0
                pts_gained = entry['points']

            changes.append({
                'user': entry['user'],
                'name': entry['name'],
                'current_rank': entry['rank'],
                'current_pts': entry['points'],
                'rank_change': rank_change,
                'pts_gained': pts_gained,
                'exact_count': entry['exact_count'],
            })

        climbers = sorted(changes, key=lambda x: (x['rank_change'], x['pts_gained']), reverse=True)
        fallers = sorted(changes, key=lambda x: (x['rank_change'], x['pts_gained']))

        return {
            'changes': changes,
            'top_climber': climbers[0] if climbers and climbers[0]['rank_change'] > 0 else None,
            'top_faller': fallers[0] if fallers and fallers[0]['rank_change'] < 0 else (fallers[0] if fallers else None),
        }

    # =========================================================================
    # 1. DRAFT PREDICTIONS LOCK EDITION (Round 1 / Kickoff Preview)
    # =========================================================================
    @classmethod
    def draft_predictions_lock_edition(cls, tournament: Tournament, round_num: int, round_name: str) -> DailyGazette:
        """
        Drafts the PREDICTIONS_LOCK Magazine Edition before any match is played:
        1. Orakeltipset: Tre Profeter Synar Kupongerna (Vetenskapsmannen, Experten, Kaospiloten)
        2. Konsensusfällan: Gruppens Kollektiva Masspsykos
        3. Ensamvargarna: De Isolerade Hävstångsdragen
        4. Kupongernas Karaktär: Betongförsvar mot Romantisk Champagne
        5. Omgångens Kupongbikt (Spelare för Spelare)
        """
        is_toarp = is_toarps_pool(tournament)
        personas_list = load_player_personas() if is_toarp else []

        players = list(tournament.players.filter(is_staff=False, is_superuser=False))
        if not players:
            from django.contrib.auth.models import User
            pred_player_ids = MatchPrediction.objects.filter(
                match__tournament=tournament
            ).values_list('player_id', flat=True).distinct()
            players = list(User.objects.filter(id__in=pred_player_ids))

        all_matches = list(Match.objects.filter(tournament=tournament).order_by('match_number'))
        all_preds = list(MatchPrediction.objects.filter(match__tournament=tournament))

        player_data = []
        tot_goals_group = 0
        tot_preds_count = 0

        for p in players:
            p_name = get_player_nick_or_name(p, personas_list, is_toarp=is_toarp)
            p_preds = [pred for pred in all_preds if pred.player_id == p.id]
            cnt = len(p_preds)
            if cnt > 0:
                p_goals = sum(pred.home_goals + pred.away_goals for pred in p_preds)
                p_avg_goals = p_goals / cnt
                p_home = sum(1 for pred in p_preds if pred.home_goals > pred.away_goals)
                p_draws = sum(1 for pred in p_preds if pred.home_goals == pred.away_goals)
                p_away = sum(1 for pred in p_preds if pred.home_goals < pred.away_goals)
                p_decisive = p_home + p_away
                
                # Frequency of scorelines
                score_counter = Counter((pred.home_goals, pred.away_goals) for pred in p_preds)
                top_score_tuple, top_score_cnt = score_counter.most_common(1)[0] if score_counter else ((2,1), 1)
                top_score_str = f"{top_score_tuple[0]}–{top_score_tuple[1]}"
                
                # Highest scoring single pick
                wildest_pred = max(p_preds, key=lambda pred: pred.home_goals + pred.away_goals)
                wildest_score_str = f"{wildest_pred.home_goals}–{wildest_pred.away_goals}"
                wildest_match_name = f"{wildest_pred.match.get_home_team_info()['name']} vs {wildest_pred.match.get_away_team_info()['name']}"

                # Standard low-scoring margins (1-0, 2-1, 1-1, 2-0)
                standard_margins = sum(
                    1 for pred in p_preds 
                    if (pred.home_goals, pred.away_goals) in [(1,0),(0,1),(2,1),(1,2),(1,1),(2,0),(0,2)]
                )
                
                # Expected Value metric: reward standard statistical scorelines
                ev_score = round(14.0 + (standard_margins / cnt) * 4.5, 1)

                # Chaos Score metric: reward draws + extreme scorelines (diff >= 3 or total >= 5)
                outliers = sum(
                    1 for pred in p_preds 
                    if (pred.home_goals + pred.away_goals >= 5 or abs(pred.home_goals - pred.away_goals) >= 3 or pred.home_goals == pred.away_goals)
                )
                chaos_score = min(98, max(45, int((outliers / cnt) * 100 + random.randint(5, 15))))

                tot_goals_group += p_goals
                tot_preds_count += cnt

                player_data.append({
                    'user': p,
                    'name': p_name,
                    'total_goals': p_goals,
                    'avg_goals': p_avg_goals,
                    'home_wins': p_home,
                    'draws': p_draws,
                    'away_wins': p_away,
                    'top_score': top_score_str,
                    'top_score_cnt': top_score_cnt,
                    'wildest_score': wildest_score_str,
                    'wildest_match': wildest_match_name,
                    'decisive': p_decisive,
                    'standard_margins': standard_margins,
                    'ev_score': ev_score,
                    'chaos_score': chaos_score,
                    'preds': p_preds,
                    'cnt': cnt,
                })

        if not player_data:
            # Fallback dummy
            player_data.append({
                'name': 'Tipparen', 'total_goals': 100, 'avg_goals': 2.5, 'ev_score': 15.0, 'chaos_score': 65, 'cnt': 1
            })

        # Group average
        avg_goals_match = round(tot_goals_group / tot_preds_count, 2) if tot_preds_count > 0 else 2.5

        # ---------------------------------------------------------------------
        # 1. ORACLE TRIO
        # ---------------------------------------------------------------------
        # Scientist: Highest EV
        scientist_cand = max(player_data, key=lambda x: x['ev_score'])
        # Expert: Most standard low-margin / defensive realism
        expert_cand = max(player_data, key=lambda x: (x.get('standard_margins', 0) / max(1, x.get('cnt', 1)), -x.get('avg_goals', 0)))
        if expert_cand['name'] == scientist_cand['name'] and len(player_data) > 1:
            expert_cand = sorted(player_data, key=lambda x: -x.get('standard_margins', 0))[1]
        # WildCard / Chaos: Highest Chaos index
        wildcard_cand = max(player_data, key=lambda x: x['chaos_score'])
        if wildcard_cand['name'] in [scientist_cand['name'], expert_cand['name']] and len(player_data) > 2:
            wildcard_cand = sorted(player_data, key=lambda x: -x['chaos_score'])[2]

        oracle_body = (
            f"🔬 <strong>Vetenskapsmannen (Sannolikhet & Spelteori):</strong> Modellen korar <strong>{scientist_cand['name']}</strong> till matematisk favorit. "
            f"Med ett förväntat poängvärde (EV) på {scientist_cand['ev_score']} poäng har han maximerat utväxlingen genom att spika favoriternas mest sannolika marginaler utan att slösa poäng på statistiska extremvärden. "
            f"En kylig, optimerad ingenjörskupong som vinner i längden eftersom den vägrar drömma.<br><br>"
            f"☕ <strong>Experten (Taktik & Mästerskapsrealism):</strong> Pundit-priset går till <strong>{expert_cand['name']}</strong>. "
            f"Hans taktiska blick tar hänsyn till mästerskapens defensiva verklighet, strypta tempo och kompakta försvarslinjer. "
            f"Medan övriga förväntar sig öppen festfotboll har {expert_cand['name']} synat den taktiska logiken. Det blir inte vackert, men det är taktiskt bäst underbyggt.<br><br>"
            f"🌪️ <strong>Kaospiloten (Fjärilseffekten & Total Förödelse):</strong> <strong>{wildcard_cand['name']}</strong> är omgångens ohotade kaospilot med ett kaosindex på {wildcard_cand['chaos_score']}/100. "
            f"Genom att spika djärva skrällar och oortodoxa resultat har han lämnat all logik bakom sig. "
            f"Skulle favoriterna implodera tar {wildcard_cand['name']} ensam full pott medan övriga nollar. Det är en procents chans, men han kommer påminna alla om det i tio år om det inträffar."
        )

        # ---------------------------------------------------------------------
        # 2. KONSENSUSFÄLLAN
        # ---------------------------------------------------------------------
        match_consensus = []
        for m in all_matches:
            m_preds = [p for p in all_preds if p.match_id == m.id]
            if len(m_preds) >= 3:
                h_cnt = sum(1 for p in m_preds if p.home_goals > p.away_goals)
                d_cnt = sum(1 for p in m_preds if p.home_goals == p.away_goals)
                a_cnt = sum(1 for p in m_preds if p.home_goals < p.away_goals)
                max_sign_cnt = max(h_cnt, d_cnt, a_cnt)
                sign_str = "hemmaseger" if max_sign_cnt == h_cnt else ("oavgjort" if max_sign_cnt == d_cnt else "bortaseger")
                match_consensus.append({
                    'match_name': f"{m.get_home_team_info()['name']} vs {m.get_away_team_info()['name']}",
                    'max_cnt': max_sign_cnt,
                    'tot_cnt': len(m_preds),
                    'sign_str': sign_str,
                })

        match_consensus.sort(key=lambda x: x['max_cnt'], reverse=True)
        top_banker = match_consensus[0] if match_consensus else {
            'match_name': 'Stormatchen', 'max_cnt': len(player_data), 'tot_cnt': len(player_data), 'sign_str': 'hemmaseger'
        }

        consensus_body = (
            f"En analys av de inlämnade raderna avslöjar en monumental flockmentalitet. "
            f"Hela {top_banker['max_cnt']} av {top_banker['tot_cnt']} deltagare har lämnat in identisk {top_banker['sign_str']} i <strong>{top_banker['match_name']}</strong>, "
            f"vilket gör matchen till omgångens absolut tyngsta konsensusfälla.<br><br>"
            f"Detta skapar en massiv systemrisk för tabellen: om favoriten släpper in ett slumpmål i 88:e minuten eller drabbas av ett tidigt rött kort dras nästan hela gruppen med i samma fall utan att någon vinner mark."
        )

        # ---------------------------------------------------------------------
        # 3. ENSAMVARGARNA
        # ---------------------------------------------------------------------
        lone_wolves = []
        for m in all_matches:
            m_preds = [p for p in all_preds if p.match_id == m.id]
            if len(m_preds) >= 3:
                h_preds = [p for p in m_preds if p.home_goals > p.away_goals]
                d_preds = [p for p in m_preds if p.home_goals == p.away_goals]
                a_preds = [p for p in m_preds if p.home_goals < p.away_goals]
                h_name = m.get_home_team_info()['name']
                a_name = m.get_away_team_info()['name']

                if len(a_preds) == 1 and len(h_preds) >= 2:
                    p_nick = get_player_nick_or_name(a_preds[0].player, personas_list, is_toarp=is_toarp)
                    lone_wolves.append(f"• <strong>{p_nick} mot strömmen:</strong> Enda spelare att tippa bortaseger i {h_name} vs {a_name} ({a_preds[0].home_goals}-{a_preds[0].away_goals}). Ett solodrag som garanterar noll poäng i nio fall av tio, men som skapar ett direkt försprång på sex poäng gentemot fältet vid en skräll.")
                elif len(d_preds) == 1 and (len(h_preds) + len(a_preds)) >= 3:
                    p_nick = get_player_nick_or_name(d_preds[0].player, personas_list, is_toarp=is_toarp)
                    lone_wolves.append(f"• <strong>{p_nick} och kryssteorin:</strong> Har lämnat in omgångens enda kryss i {h_name} vs {a_name} ({d_preds[0].home_goals}-{d_preds[0].away_goals}). Medan övriga räknar med överkörning sitter {p_nick} ensam på pottens hela värde om matchen låser sig.")
                elif len(h_preds) == 1 and len(a_preds) >= 2:
                    p_nick = get_player_nick_or_name(h_preds[0].player, personas_list, is_toarp=is_toarp)
                    lone_wolves.append(f"• <strong>{p_nick} på jakt efter hemmaseger:</strong> Är ensam om att tro på hemmaseger i {h_name} vs {a_name} ({h_preds[0].home_goals}-{h_preds[0].away_goals}). Ett aggressivt spel med hög fallhöjd som belönas kungligt vid skräll.")

        if lone_wolves:
            lone_wolves_body = "Ute i marginalerna finns ett fåtal rader som helt bryter mot gruppens mönster och bär maximal poänghävstång:<br><br>" + "<br><br>".join(lone_wolves[:3])
        else:
            lone_wolves_body = "Gruppen har tippat synnerligen disciplinerat utan extrema solospel. Alla deltagare håller sig tätt intill de statistiska huvudvägarna."

        # ---------------------------------------------------------------------
        # 4. KUPONGERNAS KARAKTÄR (Betongförsvar vs Champagne)
        # ---------------------------------------------------------------------
        sorted_by_goals = sorted(player_data, key=lambda x: x['avg_goals'])
        pragmatist = sorted_by_goals[0]
        optimist = sorted_by_goals[-1]

        character_body = (
            f"Målfördelningen över alla inlämnade tips visar en tydlig ideologisk klyfta i gruppen:<br><br>"
            f"📊 <strong>Snittmålet:</strong> Gruppen förutspår i genomsnitt <strong>{avg_goals_match} mål per match</strong>.<br><br>"
            f"🛡️ <strong>Betongligan ({pragmatist['name']}):</strong> Har lämnat in gruppens mest målsnåla kupong med ett snitt på låga {pragmatist['avg_goals']:.2f} mål per match och frekventa 1–0/0–0-tips. Bygger helt på att anfallarna har en kollektivt trög helg.<br><br>"
            f"🍾 <strong>Champagneligan ({optimist['name']}):</strong> Står för den totala motsatsen med ett målsnitt på hela {optimist['avg_goals']:.2f} mål per match. Förutsätter öppna spjäll och bjuder på tips som 3–1 och 2–2. Kuponger som kräver konstant underhållning och havererar i samma stund som en match låser sig taktiskt."
        )

        # ---------------------------------------------------------------------
        # 5. KUPONGBIKT (Spelare för Spelare - Dynamic & Non-repetitive)
        # ---------------------------------------------------------------------
        dossiers = []
        
        # Determine group extremes for contextual contrast
        max_home_player = max(player_data, key=lambda x: x.get('home_wins', 0))
        max_draw_player = max(player_data, key=lambda x: x.get('draws', 0))
        max_away_player = max(player_data, key=lambda x: x.get('away_wins', 0))
        max_goal_player = max(player_data, key=lambda x: x.get('avg_goals', 0))
        min_goal_player = min(player_data, key=lambda x: x.get('avg_goals', 0))

        used_archetypes = set()

        for idx, p_info in enumerate(player_data):
            name = p_info['name']
            goals = p_info['avg_goals']
            h_wins = p_info.get('home_wins', 0)
            draws = p_info.get('draws', 0)
            a_wins = p_info.get('away_wins', 0)
            top_s = p_info.get('top_score', '2–1')
            top_s_cnt = p_info.get('top_score_cnt', 1)
            wild_s = p_info.get('wildest_score', '3–1')
            wild_m = p_info.get('wildest_match', 'stormatch')
            chaos = p_info.get('chaos_score', 50)
            ev = p_info.get('ev_score', 15.0)

            # Assign dynamic archetype based on distinct standout feature
            if p_info == max_goal_player and 'Champagnegeneralen' not in used_archetypes:
                archetype = "Champagnegeneralen & Målfestoptimisten"
                used_archetypes.add('Champagnegeneralen')
                commentary = (
                    f"Toppar ligans måltabell med gruppens högsta förväntade målsnitt ({goals:.2f} mål/match) och {top_s} som signaturresultat ({top_s_cnt} ggr). "
                    f"Vägrar tro på målsnåla dödlägen och laddar på med offensiva explosioner som {wild_s} i {wild_m}. "
                    f"Går all-in på att mästerskapet bjuder på anfallsshow och kan få en flygande start om favoriterna öser på framåt."
                )
            elif p_info == min_goal_player and 'Försvarsrealisten' not in used_archetypes:
                archetype = "Kryssmatematikern & Försvarsrealisten"
                used_archetypes.add('Försvarsrealisten')
                commentary = (
                    f"Står för gruppens mest disciplinerade försvarsbygge med ligans lägsta målsnitt ({goals:.2f} mål/match) och hela {draws} krysstips i raden. "
                    f"Förlitar sig på att mästerskapets inledande omgångar präglas av stängda ytor och lågt risktagande, med {top_s} som favoritvapen ({top_s_cnt} matcher). "
                    f"En strategisk ingenjörskupong som kopplar greppet så fort stormatcherna fastnar i mittfältslåsningar."
                )
            elif p_info == max_home_player and 'Favoritspikaren' not in used_archetypes:
                archetype = "Hemmastarke Favoritspikaren & Skrälljägaren"
                used_archetypes.add('Favoritspikaren')
                commentary = (
                    f"Litar stenhårt på hemmaplanens magi med ligans högsta andel hemmasegrar ({h_wins} st) och ratar krysset konsekvent (endast {draws} oavgjorda). "
                    f"Favoritresultatet är {top_s} ({top_s_cnt} matcher), kombinerat med utvalda vassa bortaskrällar för att skapa tidig hävstång. "
                    f"En attackinriktad rad byggd för att vinna stort på favoriternas stabilitet utan att slösa poäng på onödiga garderingar."
                )
            elif p_info == max_away_player and 'Bortaspikaren' not in used_archetypes:
                archetype = "Bortaspikaren & Motströmsseglaren"
                used_archetypes.add('Bortaspikaren')
                commentary = (
                    f"Går rakt emot hemmatrenden och leder ligan med hela {a_wins} bortatecken och {top_s} som återkommande chockresultat ({top_s_cnt} ggr). "
                    f"Söker aktivt efter omgångens mest lukrativa bortaskrällar för att rycka ifrån flocken tidigt. "
                    f"En modig rad med hög fallhöjd som kan vända upp och ner på tabellen om underhundarna kliver fram på motståndarnas planhalva."
                )
            elif draws >= 8:
                archetype = "Taktiske Schackspelaren"
                commentary = (
                    f"Bygger sin strategi kring {draws} noggrant utplacerade krysstecken och ett välbalanserat snitt på {goals:.2f} mål per match. "
                    f"Har identifierat matcherna där båda lagen är nöjda med delad pott och vägrar gå i favoritfällorna. "
                    f"Skulle premiären bjuda på delade poäng sitter {name} i perfekt förarsäte gentemot resten av fältet."
                )
            elif chaos >= 70:
                archetype = "Djärve Kaospiloten"
                commentary = (
                    f"Har lämnat den statistiska mittfåran bakom sig med {a_wins} bortasegrar och en rad spektakulära extremresultat ({wild_s}). "
                    f"Satsar helhjärtat på att mästerskapet bjuder på ologiska skrällar och defensiva kollapser. "
                    f"En kupong med maximal hävstång där varje fullträff kommer att svida ordentligt för konkurrenterna."
                )
            else:
                archetype = "Metodiske Spelstrategen"
                commentary = (
                    f"Levererar en ytterst stabil kupong baserad på sunda marginaler ({top_s} i {top_s_cnt} matcher) och kontrollerat målsnitt ({goals:.2f} mål/match). "
                    f"Undviker onödiga chansningar och maximerar sitt förväntade poängvärde över tid genom att hålla sig till sannolika utfall. "
                    f"En kupong som sällan kollapsar och som tål hårt tryck över en lång mästerskapsresa."
                )

            dossiers.append(
                f"• <strong>{name} ({archetype}):</strong> {commentary}"
            )

        dossiers_body = "Kortfattad genomgång av varje deltagares inlämnade rad inför premiären:<br><br>" + "<br><br>".join(dossiers)

        # Build Structured Data
        structured_data = {
            'sections': [
                {
                    'badge_text': '🔮 ORAKELTIPSET: Tre Profeter Synar Kupongerna',
                    'badge_bg': '#8B5CF6',
                    'badge_color': '#ffffff',
                    'card_bg': 'rgba(139, 92, 246, 0.12)',
                    'card_border': 'rgba(139, 92, 246, 0.4)',
                    'title': 'Vetenskapsmannen, Experten & Kaospiloten',
                    'body': oracle_body,
                },
                {
                    'badge_text': '👥 KONSENSUSFÄLLAN: Gruppens Kollektiva Masspsykos',
                    'badge_bg': '#F59E0B',
                    'badge_color': '#000000',
                    'card_bg': 'rgba(245, 158, 11, 0.12)',
                    'card_border': 'rgba(245, 158, 11, 0.4)',
                    'title': f"Massiv Flockmentalitet i {top_banker['match_name']}",
                    'body': consensus_body,
                },
                {
                    'badge_text': '🐺 ENSAMVARGARNA: De Isolerade Hävstångsdragen',
                    'badge_bg': '#EF4444',
                    'badge_color': '#ffffff',
                    'card_bg': 'rgba(239, 68, 68, 0.12)',
                    'card_border': 'rgba(239, 68, 68, 0.4)',
                    'title': 'Djärva Solospel med Maximal Hävstång',
                    'body': lone_wolves_body,
                },
                {
                    'badge_text': '⚽ KUPONGERNAS KARAKTÄR: Betongförsvar mot Romantisk Champagne',
                    'badge_bg': '#10B981',
                    'badge_color': '#ffffff',
                    'card_bg': 'rgba(16, 185, 129, 0.12)',
                    'card_border': 'rgba(16, 185, 129, 0.4)',
                    'title': f"Gruppsnitt: {avg_goals_match} mål per match",
                    'body': character_body,
                },
                {
                    'badge_text': '📋 OMGÅNGENS KUPONGBIKT: Spelare för Spelare',
                    'badge_bg': '#6366F1',
                    'badge_color': '#ffffff',
                    'card_bg': 'rgba(99, 102, 241, 0.12)',
                    'card_border': 'rgba(99, 102, 241, 0.4)',
                    'title': 'Kupongbikt & Risknivåer',
                    'body': dossiers_body,
                },
            ]
        }

        full_content = (
            f"### 🔮 Orakeltipset: Tre Profeter Synar Kupongerna\n\n{oracle_body}\n\n"
            f"### 👥 Konsensusfällan: Gruppens Kollektiva Masspsykos\n\n{consensus_body}\n\n"
            f"### 🐺 Ensamvargarna: De Isolerade Hävstångsdragen\n\n{lone_wolves_body}\n\n"
            f"### ⚽ Kupongernas Karaktär: Betongförsvar mot Romantisk Champagne\n\n{character_body}\n\n"
            f"### 📋 Omgångens Kupongbikt\n\n{dossiers_body}"
        )

        from django.utils import timezone
        pub_date = timezone.now().date()

        main_headline = "ORAKELTIPSET SYNER GÄNGETS ALLA RADER!"
        tagline = "Alla tips inlämnade & verifierade • Orakeltipset, Konsensusfällan & Kupongbikten"

        gazette, _ = DailyGazette.objects.update_or_create(
            tournament=tournament,
            round_number=round_num,
            defaults={
                'publish_date': pub_date,
                'is_special_edition': True,
                'round_name': round_name,
                'content_format': 'PREDICTIONS_LOCK',
                'headline': main_headline,
                'tagline': tagline,
                'content': full_content,
                'headline_top_contenders': oracle_body,
                'headline_standout_results': consensus_body,
                'headline_worst_performers': lone_wolves_body,
                'analysis_outlook': character_body,
                'structured_data': structured_data,
                'image_url': '/static/tournament/img/gazette_default_cover.jpg',
                'tone_used': 'Orakel & Spelteori',
            }
        )

        return gazette

    # =========================================================================
    # 2. DRAFT ROUND CONCLUSION / IN-PROGRESS STAGE EDITION
    # =========================================================================
    @classmethod
    def draft_special_edition(cls, tournament: Tournament, round_num: int, round_name: str = None) -> DailyGazette:
        """Generates a complete Special Edition DailyGazette record for a given round milestone."""
        from tournament.services.scoring import calc_pred_points
        if not round_name:
            round_info = MILESTONE_ROUNDS.get(round_num, {'name': f'Omgång {round_num}', 'code': f'ROUND_{round_num}'})
            round_name = round_info['name']

        # Check if this is the PREDICTIONS_LOCK / Kickoff edition (Round 1)
        if round_num == 1 or 'verifierade' in round_name.lower() or 'lock' in round_name.lower():
            return cls.draft_predictions_lock_edition(tournament, round_num, round_name)

        is_toarp = is_toarps_pool(tournament)
        personas_list = load_player_personas() if is_toarp else []
        point_system = getattr(tournament, 'point_system', None)

        # 1. Snapshot current cumulative leaderboard
        current_lb = cls.snapshot_leaderboard(tournament, round_num, round_name, is_toarp=is_toarp, personas_list=personas_list)
        analysis = cls.analyze_round_changes(tournament, round_num, current_lb)

        # Build featured players banner data (portrait photos for Toarp)
        featured_players = _build_featured_players_json(current_lb, personas_list) if is_toarp else []

        # 2. Extract matches played specifically in this single round
        single_round_matches = list(get_matches_for_single_round(tournament, round_num))
        tot_round_matches_cnt = len(single_round_matches)

        # 3. Calculate points and exact hits scored specifically in THIS round
        for p_entry in current_lb:
            p_user = p_entry['user']
            p_round_preds = [
                pred for pred in MatchPrediction.objects.filter(player=p_user, match__in=single_round_matches)
            ]
            round_pts = sum(calc_pred_points(pred, pred.match, point_system) for pred in p_round_preds)
            round_exact = sum(
                1 for pred in p_round_preds 
                if pred.match.home_goals is not None and pred.match.away_goals is not None
                and pred.home_goals == pred.match.home_goals and pred.away_goals == pred.match.away_goals
            )
            p_entry['pts_in_round'] = round_pts
            p_entry['exact_in_round'] = round_exact

        # Identify key players for this specific round
        leader = current_lb[0] if current_lb else {'name': 'Tipparen', 'points': 0, 'pts_in_round': 0}
        runner_up = current_lb[1] if len(current_lb) > 1 else {'name': 'Utmanaren', 'points': 0, 'pts_in_round': 0}
        third_place = current_lb[2] if len(current_lb) > 2 else None
        
        leader_name = leader['name']
        runner_name = runner_up['name']

        round_mvp = max(current_lb, key=lambda x: (x.get('pts_in_round', 0), x.get('exact_in_round', 0))) if current_lb else leader
        round_bust = min(current_lb, key=lambda x: (x.get('pts_in_round', 0), x.get('exact_in_round', 0))) if current_lb else leader

        top_climber = analysis.get('top_climber')
        top_faller = analysis.get('top_faller') or (current_lb[-1] if current_lb else leader)

        pts_diff = leader['points'] - runner_up['points']

        # 4. Find Coupon Buster match in this round (match where most players scored 0)
        buster_match_name = "Stormatchen"
        buster_actual_res = "1–0"
        buster_zeros_cnt = 0
        if single_round_matches:
            match_zero_counts = []
            for m in single_round_matches:
                m_zeros = 0
                for p_entry in current_lb:
                    pred = MatchPrediction.objects.filter(player=p_entry['user'], match=m).first()
                    pts = calc_pred_points(pred, m, point_system)
                    if pts == 0:
                        m_zeros += 1
                match_zero_counts.append({
                    'match': m,
                    'zeros': m_zeros,
                    'name': f"{m.get_home_team_info()['name']} vs {m.get_away_team_info()['name']}",
                    'result': f"{m.home_goals}–{m.away_goals}"
                })
            match_zero_counts.sort(key=lambda x: x['zeros'], reverse=True)
            top_b = match_zero_counts[0]
            buster_match_name = top_b['name']
            buster_actual_res = top_b['result']
            buster_zeros_cnt = top_b['zeros']

        # 5. Championship Probability Estimator
        total_pool_points = sum(x['points'] for x in current_lb) or 1
        lead_share = (leader['points'] / total_pool_points) * 100
        lead_prob = min(85, max(35, int(lead_share * 1.35 + (10 if pts_diff >= 15 else (5 if pts_diff >= 5 else 0)))))
        runner_prob = min(100 - lead_prob, max(15, int((runner_up['points'] / total_pool_points) * 100)))
        chaser_prob = max(5, 100 - lead_prob - runner_prob)

        # 6. Stage-Specific Thematic Narratives
        if round_num == 2:
            # Gruppomgång 1
            stage_theme = "Premiäromgångens Bokslut (12 matcher)"
            sec1_title = f"Premiärrycket: {leader['name']} Tar Ledartröjan på {leader['points']}p!"
            sec1_body = (
                f"Mästerskapets första 12 drabbningar är avslutade och startfältet har satt sin första struktur. "
                f"<strong>{leader['name']}</strong> kopplar ett tidigt grepp om tabellen med <strong>{leader['points']} poäng</strong> efter en knivskarp öppning. "
                f"Tätt i rygg lurar dock <strong>{runner_name}</strong> på {runner_up['points']} poäng (endast {pts_diff}p bakom). "
                f"Premiäromgången präglades av intensiva taktiska låsningar där de som vågade gardera med kalla spikar belönades direkt."
            )
            sec2_title = f"Omgångens Kung & Haverist: {round_mvp['name']} Glänste (+{round_mvp['pts_in_round']}p)!"
            sec2_body = (
                f"Omgångens MVP-pris går ohotat till <strong>{round_mvp['name']}</strong> som var absolut vassast i premiären med hela <strong>+{round_mvp['pts_in_round']} poäng</strong> och {round_mvp['exact_in_round']} fullpottar.<br><br>"
                f"I tabellens andra ände fick <strong>{round_bust['name']}</strong> en blytung start med blygsamma +{round_bust['pts_in_round']} poäng. "
                f"Med hela turneringen kvar krävs dock bara en enda stark omgång för att vända på steken."
            )
            sec3_title = f"Kupongdödaren: {buster_match_name} ({buster_actual_res})"
            sec3_body = (
                f"Matchen som ställde till med mest förödelse i premiären blev <strong>{buster_match_name} ({buster_actual_res})</strong>, "
                f"där hela {buster_zeros_cnt} av {len(current_lb)} deltagare kammade noll. "
                f"Ett oväntat matchförlopp som raserade flockens kalkyler och skapade omgångens största tabellkast."
            )
            sec4_title = f"AI-Simulering: Guldchans efter Omgång 1"
            sec4_body = (
                f"Vår prediktiva modell har kört den första live-simuleringen över återstående turneringsträd. "
                f"<strong>{leader['name']}</strong> tilldelas <strong>{lead_prob}% guldchans</strong> tack vare sin stabila öppning, "
                f"medan <strong>{runner_up['name']}</strong> skuggar på <strong>{runner_prob}%</strong>. "
                f"Övriga fältet delar på resterande {chaser_prob}% i vad som fortfarande är ett vidöppet mästerskap."
            )
        elif round_num == 3:
            # Gruppomgång 2
            stage_theme = "Gruppspelets Halvtidsaudit (24 matcher)"
            sec1_title = f"Halvtidsstriden: {leader['name']} Håller Undan på {leader['points']}p!"
            sec1_body = (
                f"Med 24 matcher spelade har gruppspelet nått sin mittpunkt. "
                f"<strong>{leader['name']}</strong> försvarar ledningen på <strong>{leader['points']} poäng</strong>, men marginalen bakåt till <strong>{runner_up['name']}</strong> ({runner_up['points']}p) är nu endast {pts_diff} poäng! "
                f"Omgången bjöd på stenhård poängjakt där varje målskillnad blev avgörande för ligapositionerna."
            )
            sec2_title = f"Omgångens Kung: {round_mvp['name']} Storspelade (+{round_mvp['pts_in_round']}p)!"
            sec2_body = (
                f"Omgång 2 tillhörde <strong>{round_mvp['name']}</strong>, som samlade in helgens högsta skörd med <strong>+{round_mvp['pts_in_round']} poäng</strong> och {round_mvp['exact_in_round']} fullpottar.<br><br>"
                f"Samtidigt fick <strong>{round_bust['name']}</strong> se kalkylerna krascha med endast +{round_bust['pts_in_round']}p under perioden, vilket ökar pressen inför den avgörande sista gruppomgången."
            )
            sec3_title = f"Kupongdödaren: {buster_match_name} ({buster_actual_res})"
            sec3_body = (
                f"Omgångens mest förrädiska fälla blev <strong>{buster_match_name} ({buster_actual_res})</strong>. "
                f"Hela {buster_zeros_cnt} kuponger nollades i detta möte då favoriterna tappade greppet och spräckte gruppens konsensus."
            )
            sec4_title = f"Modellens Nya Guldkalkyl: {leader['name']} ({lead_prob}%) vs {runner_up['name']} ({runner_prob}%)"
            sec4_body = (
                f"Efter 24 matcher börjar mönstren utkristallisera sig. Modellen värderar <strong>{leader['name']}s</strong> titelchans till <strong>{lead_prob}%</strong>, "
                f"men understryker att den stundande gruppavslutningen bär tillräckligt med poäng för att vända hela ställningen upp och ner."
            )
        elif round_num == 4:
            # Gruppspel Avslutat
            stage_theme = "Gruppspelets Stora Bokslut (36 matcher)"
            sec1_title = f"Gruppspelets Mästare: {leader['name']} Vinner Gruppfasen på {leader['points']}p!"
            sec1_body = (
                f"Gruppspelet i {tournament.name} är officiellt i hamn efter 36 intensiva drabbningar. "
                f"<strong>{leader['name']}</strong> kröns till gruppspelets kung på <strong>{leader['points']} poäng</strong> efter en mästerlig uppvisning i taktisk uthållighet. "
                f"På andra plats går <strong>{runner_up['name']}</strong> in i slutspelet med {runner_up['points']} poäng ({pts_diff}p bakom), redo att utnyttja slutspelsträdets hävstänger."
            )
            sec2_title = f"Gruppavslutningens Kung: {round_mvp['name']} (+{round_mvp['pts_in_round']}p)!"
            sec2_body = (
                f"I den dramatiska sista gruppomgången var <strong>{round_mvp['name']}</strong> i en klass för sig och håvade in mäktiga <strong>+{round_mvp['pts_in_round']} poäng</strong>.<br><br>"
                f"För <strong>{round_bust['name']}</strong> blev gruppavslutningen däremot en motig historia (+{round_bust['pts_in_round']}p), vilket innebär att slutspelsfasen nu kräver djärva solodrag för att ta sig tillbaka in i medaljstriden."
            )
            sec3_title = f"Gruppspelets Sista Skräll: {buster_match_name} ({buster_actual_res})"
            sec3_body = (
                f"Den match som orsakade störst huvudbry i gruppfinalen var <strong>{buster_match_name} ({buster_actual_res})</strong>, "
                f"där {buster_zeros_cnt} tippare gick bet. Slutspelslagen är nu klara och marginalerna blir från och med nu dubbelt så dyrköpta."
            )
            sec4_title = f"Slutspelets Fraktaler: Guldchans inför Åttondelsfinalerna"
            sec4_body = (
                f"Med 36 matcher avklarade skiftar turneringen karaktär från maraton till utslagning. "
                f"Modellen håller <strong>{leader['name']}</strong> som favorit på <strong>{lead_prob}%</strong>, men knockout-trädets poängmultiplikatorer öppnar för massiva kast om underhundarna skräller."
            )
        elif round_num == 11:
            # Round of 16 Spelad
            stage_theme = "Åttondelsfinalernas Slutspelsdramatik (44 matcher)"
            sec1_title = f"Slutspelets Schavott: {leader['name']} Behåller Greppet på {leader['points']}p!"
            sec1_body = (
                f"Åttondelsfinalernas plötsliga död har skördat sina första offer. "
                f"<strong>{leader['name']}</strong> navigerade genom slutspelskorselden med bibehållen ledning på <strong>{leader['points']} poäng</strong>. "
                f"Bakom ledartröjan vägrar <strong>{runner_up['name']}</strong> ({runner_up['points']}p) att vika ner sig i en duell som nu utvecklats till ett psykologiskt ställningskrig."
            )
            sec2_title = f"Slutspelskungen: {round_mvp['name']} Spikade Åttondelarna (+{round_mvp['pts_in_round']}p)!"
            sec2_body = (
                f"I åttondelsfinalernas nervpress klev <strong>{round_mvp['name']}</strong> fram och levererade omgångens bästa facit med <strong>+{round_mvp['pts_in_round']} poäng</strong> och {round_mvp['exact_in_round']} fullträffar.<br><br>"
                f"Omvänt blev åttondelarna en dyrköpt lektion för <strong>{round_bust['name']}</strong> (+{round_bust['pts_in_round']}p), vars slutspelsträd fick ta emot tunga smällar."
            )
            sec3_title = f"Slutspelsdödaren: {buster_match_name} ({buster_actual_res})"
            sec3_body = (
                f"Slutspelets första stora knall inträffade i <strong>{buster_match_name} ({buster_actual_res})</strong>, "
                f"där {buster_zeros_cnt} deltagare nollades när matchbilden vände upp och ner på alla förhandstips."
            )
            sec4_title = f"Kvartarnas Hävstång: Modellens Nya Guldsannolikhet"
            sec4_body = (
                f"Med endast 8 lag kvar i turneringen kliver vi in i kvartsfinalfasen. "
                f"<strong>{leader['name']}</strong> står på <strong>{lead_prob}% titelchans</strong>, men <strong>{runner_up['name']}</strong> ({runner_prob}%) har fortfarande den matematiska hävstången i sina egna händer."
            )
        elif round_num == 12:
            # Quarterfinals Spelad
            stage_theme = "Kvartsfinalernas Slakt & Finalfyran (48 matcher)"
            sec1_title = f"Finalfyran Klar: {leader['name']} Tar Jättekliv mot Titeln på {leader['points']}p!"

            sec1_body = (
                f"Kvartsfinalerna är färdigspelade och endast semifinaler och final återstår av {tournament.name}. "
                f"<strong>{leader['name']}</strong> stormar mot slutsegern på mäktiga <strong>{leader['points']} poäng</strong> efter en urstark kvartsfinalinsats. "
                f"Med en marginal på {pts_diff} poäng ner till <strong>{runner_up['name']}</strong> ({runner_up['points']}p) krävs det nu perfekta fullträffar av utmanarna för att stoppa ledaren."
            )
            sec2_title = f"Kvartsfinalernas MVP: {round_mvp['name']} Dominerade (+{round_mvp['pts_in_round']}p)!"
            sec2_body = (
                f"Omgångens vassaste analytiker i kvartsfinalerna blev <strong>{round_mvp['name']}</strong> som drygade ut kassan med <strong>+{round_mvp['pts_in_round']} poäng</strong>.<br><br>"
                f"För <strong>{round_bust['name']}</strong> blev kvartsfinalerna en stolpe-ut-afton (+{round_bust['pts_in_round']}p), vilket innebär att siktet nu får ställas in på att försvara sin hedersplacering."
            )
            sec3_title = f"Kupongdödaren: {buster_match_name} ({buster_actual_res})"
            sec3_body = (
                f"Kvartarnas mest dramatiska ögonblick utspelade sig i <strong>{buster_match_name} ({buster_actual_res})</strong>, "
                f"där {buster_zeros_cnt} deltagare fick se sina tips gå i kras."
            )
            sec4_title = f"Finalens Matematiska Tipping Point: {leader['name']} ({lead_prob}%)"
            sec4_body = (
                f"Med endast 4 matcher kvar i mästerskapet har <strong>{leader['name']}</strong> ett järngrepp med <strong>{lead_prob}% guldchans</strong>. "
                f"För <strong>{runner_up['name']}</strong> ({runner_prob}%) krävs nu att semifinalerna och finalen går exakt enligt utmanarens rad för att skapa ett mirakel på mållinjen."
            )
        else:
            # Generic stage fallback
            stage_theme = f"{round_name} ({tot_round_matches_cnt} matcher)"
            sec1_title = f"Tabellkriget: {leader['name']} Toppar Tabellen på {leader['points']}p!"
            sec1_body = (
                f"Efter {round_name} står <strong>{leader['name']}</strong> stolt överst på <strong>{leader['points']} poäng</strong>. "
                f"Tätt bakom lurar <strong>{runner_up['name']}</strong> på {runner_up['points']} poäng ({pts_diff}p bakom)."
            )
            sec2_title = f"Omgångens Kung: {round_mvp['name']} (+{round_mvp['pts_in_round']}p)!"
            sec2_body = f"<strong>{round_mvp['name']}</strong> plockade flest poäng i omgången med +{round_mvp['pts_in_round']}p."
            sec3_title = f"Kupongdödaren: {buster_match_name} ({buster_actual_res})"
            sec3_body = f"Matchen {buster_match_name} ställde till med mest problem i omgången."
            sec4_title = f"AI-Analys & Guldchans: {leader['name']} ({lead_prob}%)"
            sec4_body = f"Modellen värderar {leader['name']}s guldchans till {lead_prob}%."

        # Build structured data
        structured_data = {
            'sections': [
                {
                    'badge_text': '👑 TABELLKRIGET: Toppstrid, Klättrare & Marginaler',
                    'badge_bg': '#8B5CF6',
                    'badge_color': '#ffffff',
                    'card_bg': 'rgba(139, 92, 246, 0.12)',
                    'card_border': 'rgba(139, 92, 246, 0.4)',
                    'title': sec1_title,
                    'body': sec1_body,
                },
                {
                    'badge_text': '🏆 KUNG & HAVERIST: Omgångens MVP vs Bottennapp',
                    'badge_bg': '#F59E0B',
                    'badge_color': '#000000',
                    'card_bg': 'rgba(245, 158, 11, 0.12)',
                    'card_border': 'rgba(245, 158, 11, 0.4)',
                    'title': sec2_title,
                    'body': sec2_body,
                },
                {
                    'badge_text': '💥 KUPONGDÖDAREN: Matchen Som Krossade Gruppens Tips',
                    'badge_bg': '#EF4444',
                    'badge_color': '#ffffff',
                    'card_bg': 'rgba(239, 68, 68, 0.12)',
                    'card_border': 'rgba(239, 68, 68, 0.4)',
                    'title': sec3_title,
                    'body': sec3_body,
                },
                {
                    'badge_text': '🤖 GULDCHANSENS OMRÄKNING: AI-Modellens Nya Simulering',
                    'badge_bg': '#10B981',
                    'badge_color': '#ffffff',
                    'card_bg': 'rgba(16, 185, 129, 0.12)',
                    'card_border': 'rgba(16, 185, 129, 0.4)',
                    'title': sec4_title,
                    'body': sec4_body,
                },
            ]
        }

        full_content = (
            f"### {sec1_title}\n\n{sec1_body}\n\n"
            f"### {sec2_title}\n\n{sec2_body}\n\n"
            f"### {sec3_title}\n\n{sec3_body}\n\n"
            f"### {sec4_title}\n\n{sec4_body}"
        )

        from django.utils import timezone
        pub_date = timezone.now().date()

        main_headline = sec1_title.upper()
        tagline = f"{stage_theme} • Toppstrid ({pts_diff}p diff), Omgångens MVP & Guldchans"

        gazette, _ = DailyGazette.objects.update_or_create(
            tournament=tournament,
            round_number=round_num,
            defaults={
                'publish_date': pub_date,
                'is_special_edition': True,
                'round_name': round_name,
                'content_format': 'ROUND_CONCLUSION',
                'headline': main_headline,
                'tagline': tagline,
                'content': full_content,
                'headline_top_contenders': sec1_body,
                'headline_standout_results': sec2_body,
                'headline_worst_performers': sec3_body,
                'analysis_outlook': sec4_body,
                'structured_data': structured_data,
                'featured_players_json': featured_players,
                'image_url': '/static/tournament/img/gazette_default_cover.jpg',
                'tone_used': 'Magasin & Taktisk Analys',
            }
        )

        return gazette


