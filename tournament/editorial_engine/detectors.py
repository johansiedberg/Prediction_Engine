import random
from django.db.models import Q
from tournament.models import (
    Tournament, Match, MatchPrediction, InsightEvent
)


def detect_daily_events(tournament: Tournament, matchday_number: int = None):
    """
    Tier 1 Deterministic Event Detector for Section 2 (The Daily Gazette).
    Scans completed matches and prediction results on a matchday to discover & rank
    InsightEvent records across 22 analytical and banter archetypes.
    """
    from tournament.services.scoring import calc_pred_points
    from tournament.editorial_engine.compiler import load_player_personas, find_persona_for_player
    
    events_created = []
    personas_list = load_player_personas()
    
    # Query finished matches
    finished_matches = list(Match.objects.filter(tournament=tournament, is_finished=True).order_by('match_number', 'date_time'))
    if matchday_number:
        finished_matches = [m for m in finished_matches if m.match_number == matchday_number]

    if not finished_matches:
        event, _ = InsightEvent.objects.get_or_create(
            tournament=tournament,
            type='GENERAL_DRAMA',
            description="Turneringen laddar inför nästa stora drabbning i mästerskapet.",
            defaults={'importance_score': 30, 'matchday_reference': matchday_number or 1}
        )
        return [event]

    # Calculate Leaderboard & Point Statistics
    players = list(tournament.players.all())
    if not players:
        from django.contrib.auth.models import User
        pred_p_ids = MatchPrediction.objects.filter(match__tournament=tournament).values_list('player_id', flat=True).distinct()
        players = list(User.objects.filter(id__in=pred_p_ids))

    point_system = getattr(tournament, 'point_system', None)
    player_scores = {p: 0 for p in players}
    player_exacts = {p: 0 for p in players}
    player_draw_preds = {p: 0 for p in players}

    for p in players:
        p_preds = MatchPrediction.objects.filter(player=p, match__in=finished_matches)
        for pred in p_preds:
            m = pred.match
            player_scores[p] += calc_pred_points(pred, m, point_system)
            if m.home_goals is not None and m.away_goals is not None:
                if pred.home_goals == m.home_goals and pred.away_goals == m.away_goals:
                    player_exacts[p] += 1
                if pred.home_goals == pred.away_goals:
                    player_draw_preds[p] += 1

    ranked_players = sorted(players, key=lambda p: (player_scores[p], player_exacts[p]), reverse=True)

    def get_p_display(user):
        p_match = find_persona_for_player(user.get_full_name() or user.username, personas_list)
        if p_match and p_match.get('nicknames'):
            return f"**{p_match['nicknames'][0]}** ({user.get_full_name() or user.username})"
        return f"**{user.get_full_name() or user.username}**"

    def get_p_nick(user):
        p_match = find_persona_for_player(user.get_full_name() or user.username, personas_list)
        if p_match and p_match.get('nicknames'):
            return f"**{p_match['nicknames'][0]}**"
        return f"**{user.first_name or user.username}**"

    # Match-level Event Scans
    for match in finished_matches:
        preds = list(MatchPrediction.objects.filter(match=match))
        total_preds = len(preds)
        if total_preds == 0:
            continue

        h_goals = match.home_goals or 0
        a_goals = match.away_goals or 0
        tot_goals = h_goals + a_goals
        actual_sign = '1' if h_goals > a_goals else ('X' if h_goals == a_goals else '2')

        # Count predicted signs
        sign_1_cnt = sum(1 for p in preds if p.home_goals > p.away_goals)
        sign_x_cnt = sum(1 for p in preds if p.home_goals == p.away_goals)
        sign_2_cnt = sum(1 for p in preds if p.home_goals < p.away_goals)

        exact_preds = [p for p in preds if p.home_goals == h_goals and p.away_goals == a_goals]
        is_england_match = any('england' in (t or '').lower() or 'storbritannien' in (t or '').lower() for t in [match.home_team, match.away_team])

        # ---------------------------------------------------------------------
        # 1. ENGLAND-KOMPLEXET ("It's Never Coming Home" Banter)
        # ---------------------------------------------------------------------
        if is_england_match:
            england_is_home = 'england' in (match.home_team or '').lower()
            england_won = (england_is_home and actual_sign == '1') or (not england_is_home and actual_sign == '2')
            
            if not england_won:
                # England dropped points / lost — Huge Schadenfreude!
                hero_anti_england = [p for p in preds if (england_is_home and p.home_goals <= p.away_goals) or (not england_is_home and p.home_goals >= p.away_goals)]
                hero_names = ", ".join([get_p_nick(p.player) for p in hero_anti_england[:2]]) if hero_anti_england else "Ingen"
                desc = (
                    f"England-komplexet slog till med full kraft när {match.home_team} vs {match.away_team} slutade {h_goals}-{a_goals}! "
                    f"Skadeglädjen i gänget visste inga gränser när 'Three Lions' återigen trampade snett. "
                    f"Hjältarna som vägrade backa England belönades rikligt med full pott."
                )
                ev, _ = InsightEvent.objects.get_or_create(
                    tournament=tournament,
                    type='ENGLAND_BANTER',
                    description=desc,
                    defaults={'importance_score': 98, 'matchday_reference': match.match_number or 1}
                )
                events_created.append(ev)
            else:
                # England won — Roast England backers for "dirty/unethical points"
                england_backers = [p for p in preds if (england_is_home and p.home_goals > p.away_goals) or (not england_is_home and p.home_goals < p.away_goals)]
                backer_names = ", ".join([get_p_nick(p.player) for p in england_backers[:2]]) if england_backers else "Ingen"
                desc = (
                    f"England bärgade segern ({h_goals}-{a_goals}) mot {match.away_team if england_is_home else match.home_team}, "
                    f"men stämningen kring pubbordet var iskall. {backer_names} tog hem poängen, "
                    f"men frågan kring bordet var självklar: Var de 'smutsiga poängen' verkligen värda att sälja själen för?"
                )
                ev, _ = InsightEvent.objects.get_or_create(
                    tournament=tournament,
                    type='ENGLAND_BANTER',
                    description=desc,
                    defaults={'importance_score': 88, 'matchday_reference': match.match_number or 1}
                )
                events_created.append(ev)

        # ---------------------------------------------------------------------
        # 2. PROFILLÖST / LEVA PÅ GAMLA MERITER (Historical Heavyweights Skepticism)
        # ---------------------------------------------------------------------
        heavyweights = ['frankrike', 'brasilien', 'tyskland', 'spanien', 'italien', 'argentina', 'norge', 'danmark']
        is_heavyweight_match = any(any(hw in (t or '').lower() for hw in heavyweights) for t in [match.home_team, match.away_team])
        if is_heavyweight_match and actual_sign == 'X':
            desc = (
                f"Den profillösa tron på gamla meriter straffade sig brutalt när {match.home_team} vs {match.away_team} slutade {h_goals}-{a_goals}. "
                f"De som slentrianmässigt litade på stornationens historiska glans fick se kalkylerna krascha mot verkligheten."
            )
            ev, _ = InsightEvent.objects.get_or_create(
                tournament=tournament,
                type='PAST_MERITS_SKEPTIC',
                description=desc,
                defaults={'importance_score': 89, 'matchday_reference': match.match_number or 1}
            )
            events_created.append(ev)

        # ---------------------------------------------------------------------
        # 3. SPIKKRASCHEN (Failed Banker, >= 60% consensus failed)
        # ---------------------------------------------------------------------
        if (actual_sign == 'X' or actual_sign == '2') and (sign_1_cnt / total_preds) >= 0.55:
            desc = (
                f"Kollektiv spikkrasch! Hela {sign_1_cnt} av {total_preds} spelare förväntade sig att {match.home_team} skulle ta tre säkra poäng, "
                f"men matchen slutade {h_goals}-{a_goals} och sänkte majoriteten av gängets kuponger."
            )
            ev, _ = InsightEvent.objects.get_or_create(
                tournament=tournament,
                type='FAILED_BANKER',
                description=desc,
                defaults={'importance_score': 93, 'matchday_reference': match.match_number or 1}
            )
            events_created.append(ev)

        # ---------------------------------------------------------------------
        # 4. ENSAMVARGEN (Outlier Lone Wolf Victory)
        # ---------------------------------------------------------------------
        if len(exact_preds) == 1:
            hero = exact_preds[0]
            hero_nick = get_p_nick(hero.player)
            hero_name = hero.player.get_full_name() or hero.player.username
            desc = (
                f"{hero_nick} ({hero_name}) stod för en taktisk mästerstöt och var den ENDA spelaren i hela ligan "
                f"som spikade det exakta slutresultatet {h_goals}-{a_goals} i {match.home_team} vs {match.away_team}!"
            )
            ev, _ = InsightEvent.objects.get_or_create(
                tournament=tournament,
                type='OUTLIER_VICTORY',
                player_name=hero_name,
                description=desc,
                defaults={'importance_score': 96, 'matchday_reference': match.match_number or 1}
            )
            events_created.append(ev)

        # ---------------------------------------------------------------------
        # 5. MÅLBONANZAN (Goal Avalanche, >= 5 total goals or high score)
        # ---------------------------------------------------------------------
        if tot_goals >= 5:
            desc = (
                f"Total målexplosion i {match.home_team} vs {match.away_team}! Lagen bjöd på en sanslös propagandafotboll "
                f"med hela {tot_goals} mål ({h_goals}-{a_goals}) som kastade alla defensiva taktiktavlor i papperskorgen."
            )
            ev, _ = InsightEvent.objects.get_or_create(
                tournament=tournament,
                type='GOAL_FEST',
                description=desc,
                defaults={'importance_score': 84, 'matchday_reference': match.match_number or 1}
            )
            events_created.append(ev)

        # ---------------------------------------------------------------------
        # 6. BETONGFÖRSVARET (0-0 or 1-0 Low Block Grind)
        # ---------------------------------------------------------------------
        if tot_goals <= 1:
            desc = (
                f"Betongförsvar och stängda spjäll i {match.home_team} vs {match.away_team} ({h_goals}-{a_goals})! "
                f"En taktisk lågblocksfajt som krossade alla optimistiska måltips och belönade de cyniska defensivtipparna."
            )
            ev, _ = InsightEvent.objects.get_or_create(
                tournament=tournament,
                type='LOW_BLOCK_GRIND',
                description=desc,
                defaults={'importance_score': 78, 'matchday_reference': match.match_number or 1}
            )
            events_created.append(ev)

        # ---------------------------------------------------------------------
        # 7. SKILJEMATCHEN (Entropy Split: tips evenly split 1/X/2)
        # ---------------------------------------------------------------------
        if total_preds >= 4 and min(sign_1_cnt, sign_x_cnt, sign_2_cnt) >= 1:
            desc = (
                f"Skiljematchen som klöv gänget i tre läger! I {match.home_team} vs {match.away_team} var tipsraderna "
                f"totalt splittrade mellan etta, kryss och tvåa ({sign_1_cnt}-{sign_x_cnt}-{sign_2_cnt}), vilket utlöste heta debatter."
            )
            ev, _ = InsightEvent.objects.get_or_create(
                tournament=tournament,
                type='DELUSION_INDEX',
                description=desc,
                defaults={'importance_score': 81, 'matchday_reference': match.match_number or 1}
            )
            events_created.append(ev)

    # -------------------------------------------------------------------------
    # 8. FULLPOTT-SNIPERN (2+ Exact Fullpotts by single player)
    # -------------------------------------------------------------------------
    for p, exact_cnt in player_exacts.items():
        if exact_cnt >= 2:
            p_nick = get_p_nick(p)
            p_name = p.get_full_name() or p.username
            desc = (
                f"{p_nick} ({p_name}) agerade prickskytt i omgången och bombade in hela {exact_cnt} exakta fullpottar! "
                f"En uppvisning i absolut precision som skickade chockvågor genom tabellen."
            )
            ev, _ = InsightEvent.objects.get_or_create(
                tournament=tournament,
                type='THREE_FULLPOTTS',
                player_name=p_name,
                description=desc,
                defaults={'importance_score': 95, 'matchday_reference': matchday_number or 1}
            )
            events_created.append(ev)

    # -------------------------------------------------------------------------
    # 9. MÄSTARTRONEN (Leader Runaway Swagger) & KLASSISKA DERBYT (Top 2 Duel)
    # -------------------------------------------------------------------------
    if len(ranked_players) >= 2:
        p1 = ranked_players[0]
        p2 = ranked_players[1]
        gap = player_scores[p1] - player_scores[p2]
        
        p1_nick = get_p_nick(p1)
        p1_name = p1.get_full_name() or p1.username
        p2_nick = get_p_nick(p2)
        p2_name = p2.get_full_name() or p2.username

        if gap >= 10:
            desc = (
                f"{p1_nick} ({p1_name}) dominerar turneringen och har ryckt åt sig en mäktig ledning på {player_scores[p1]}p "
                f"({gap}p före närmaste förföljare). En uppvisning i mästarklass som sätter enorm press på jakten."
            )
            ev, _ = InsightEvent.objects.get_or_create(
                tournament=tournament,
                type='IS_TOURNAMENT_LEADER',
                player_name=p1_name,
                description=desc,
                defaults={'importance_score': 94, 'matchday_reference': matchday_number or 1}
            )
            events_created.append(ev)
        elif gap <= 2:
            desc = (
                f"Klassiskt derby i tabelltoppen! Det skiljer endast {gap} poäng mellan ledande {p1_nick} ({player_scores[p1]}p) "
                f"och jagande {p2_nick} ({player_scores[p2]}p). En elektrisk titelduell där varje enskilt måltips är direkt avgörande."
            )
            ev, _ = InsightEvent.objects.get_or_create(
                tournament=tournament,
                type='RIVALRY_DUEL',
                player_name=p1_name,
                description=desc,
                defaults={'importance_score': 92, 'matchday_reference': matchday_number or 1}
            )
            events_created.append(ev)

    # -------------------------------------------------------------------------
    # 10. TRÄSLEVS-KRIGET (Bottom 2 Wooden Spoon Battle)
    # -------------------------------------------------------------------------
    if len(ranked_players) >= 4:
        last_p = ranked_players[-1]
        sec_last_p = ranked_players[-2]
        last_nick = get_p_nick(last_p)
        last_name = last_p.get_full_name() or last_p.username
        sec_last_nick = get_p_nick(sec_last_p)

        desc = (
            f"Träslevs-kriget i tabellbotten tätnar! {last_nick} ({last_name}) kämpar med näbbar och klor mot {sec_last_nick} "
            f"för att undvika den fruktade jumboplatsen och förpassas till skampålen vid turneringens slut."
        )
        ev, _ = InsightEvent.objects.get_or_create(
            tournament=tournament,
            type='BOTTOM_RANK',
            player_name=last_name,
            description=desc,
            defaults={'importance_score': 82, 'matchday_reference': matchday_number or 1}
        )
        events_created.append(ev)

    return events_created


def check_and_trigger_special_editions(tournament: Tournament):
    """
    Scans tournament progress and triggers Gazetta Special Editions for reached round milestones:
    1. Kickoff: All player predictions verified / first match started.
    2. Group Stage: Each group round played (Round 1, Round 2, Round 3, ...).
    3. Knockout Stage: Each completed knockout stage (e.g. Round of 32, 16, QF, SF, Bronze, Final).
    4. Tournament Recap: Final tournament completion.
    """
    from tournament.models import DailyGazette, TournamentSubmission, KnockoutStage
    from tournament.editorial_engine.special_edition_reporter import SpecialEditionReporter

    triggered_editions = []

    # 1. Round 1: Kickoff / All player predictions verified / time locked
    r1_exists = DailyGazette.objects.filter(tournament=tournament, is_special_edition=True, round_number=1).exists()
    if not r1_exists:
        subs = TournamentSubmission.objects.filter(tournament=tournament)
        is_locked = getattr(tournament, 'is_locked_by_time', False)
        all_verified = subs.exists() and all(s.is_verified for s in subs)
        if all_verified or is_locked:
            gazette = SpecialEditionReporter.draft_special_edition(
                tournament, round_num=1, round_name="Alla Tips Verifierade"
            )
            triggered_editions.append(gazette)

    # 2. Group Stage Rounds
    all_teams = list(tournament.teams.all())
    all_groups = list(tournament.tournament_groups.all())

    def get_team_finished_matches_count(team):
        return Match.objects.filter(
            tournament=tournament, is_finished=True
        ).filter(Q(home_team=team.name) | Q(away_team=team.name)).count()

    if all_groups and all_teams:
        # Calculate max rounds expected in group stage
        max_group_rounds = 0
        for grp in all_groups:
            t_cnt = grp.teams.count()
            if t_cnt > 1:
                max_group_rounds = max(max_group_rounds, t_cnt - 1)
        if max_group_rounds == 0:
            max_group_rounds = 3 # default fallback

        for r in range(1, max_group_rounds + 1):
            r_num = 1 + r
            r_exists = DailyGazette.objects.filter(tournament=tournament, is_special_edition=True, round_number=r_num).exists()
            if not r_exists:
                if all(get_team_finished_matches_count(t) >= r for t in all_teams):
                    is_last_grp = (r == max_group_rounds)
                    r_name = f"Gruppspel Avslutat (Omgång {r})" if is_last_grp else f"Gruppomgång {r} Spelad"
                    gazette = SpecialEditionReporter.draft_special_edition(
                        tournament, round_num=r_num, round_name=r_name
                    )
                    triggered_editions.append(gazette)

    # 3. Knockout Stage Rounds
    knockout_stages = list(tournament.knockout_stages.all().order_by('order', 'id'))
    base_ko_round = 10
    
    final_stage_completed = False
    for idx, ks in enumerate(knockout_stages, start=1):
        ko_round_num = base_ko_round + idx
        ko_exists = DailyGazette.objects.filter(tournament=tournament, is_special_edition=True, round_number=ko_round_num).exists()
        
        ks_matches = ks.matches.all()
        if ks_matches.exists() and all(m.is_finished for m in ks_matches):
            if not ko_exists:
                gazette = SpecialEditionReporter.draft_special_edition(
                    tournament, round_num=ko_round_num, round_name=f"{ks.name} Spelad"
                )
                triggered_editions.append(gazette)
            is_grand_final_stage = (
                any(k in ks.name.lower() for k in ['final', 'guld', 'championship'])
                and not any(k in ks.name.lower() for k in ['semi', 'quarter', 'kvart', 'åttondel', '16', '32', '64', 'bronze', 'brons', 'third', '3:e'])
            )
            if is_grand_final_stage:
                final_stage_completed = True

    # 4. Tournament Finale / Full Recap
    all_tourn_matches = list(tournament.matches.all())
    if final_stage_completed or (all_tourn_matches and all(m.is_finished for m in all_tourn_matches)):
        r_recap_exists = DailyGazette.objects.filter(tournament=tournament, is_special_edition=True, round_number=999).exists()
        if not r_recap_exists:
            gazette = SpecialEditionReporter.draft_special_edition(
                tournament, round_num=999, round_name="Slutmagasin & Mästaren Kronad"
            )
            triggered_editions.append(gazette)

    return triggered_editions
