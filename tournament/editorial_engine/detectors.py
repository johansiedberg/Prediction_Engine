import random
from django.db.models import Q
from tournament.models import (
    Tournament, Match, MatchPrediction, InsightEvent
)


def detect_daily_events(tournament: Tournament, matchday_number: int = None):
    """
    Tier 1 Deterministic Event Detector for Section 2 (The Daily Gazette).
    Scans completed matches and prediction results on a matchday to discover & rank InsightEvent records.
    """
    events_created = []
    
    # Query finished matches
    finished_matches = Match.objects.filter(tournament=tournament, is_finished=True)
    if matchday_number:
        finished_matches = finished_matches.filter(match_number=matchday_number)

    if not finished_matches.exists():
        # Fallback event if no match finished yet
        event, _ = InsightEvent.objects.get_or_create(
            tournament=tournament,
            type='GENERAL_DRAMA',
            description="Turneringen laddar inför nästa stora drabbning i mästerskapet.",
            defaults={'importance_score': 30, 'matchday_reference': matchday_number or 1}
        )
        return [event]

    # Track player exact score counts on this matchday
    player_fullpotts = {}

    for match in finished_matches:
        preds = MatchPrediction.objects.filter(match=match)
        total_preds = preds.count()
        if total_preds == 0:
            continue

        actual_home_win = match.home_goals > match.away_goals
        actual_draw = match.home_goals == match.away_goals

        # 1. Detect Failed Banker (where >= 60% predicted a home win that failed)
        if actual_draw or not actual_home_win:
            expected_home_win = sum(1 for p in preds if p.home_goals > p.away_goals)
            if total_preds > 0 and (expected_home_win / total_preds) >= 0.60:
                desc = f"{expected_home_win} av {total_preds} spelare förväntade sig att {match.home_team} skulle ta tre poäng, men matchen slutade {match.home_goals}-{match.away_goals}."
                event, _ = InsightEvent.objects.get_or_create(
                    tournament=tournament,
                    type='FAILED_BANKER',
                    description=desc,
                    defaults={'importance_score': 90, 'matchday_reference': match.match_number or 1}
                )
                events_created.append(event)

        # 2. Detect Outlier Victory (exact scoreline predicted by only 1 player)
        exact_preds = [p for p in preds if p.home_goals == match.home_goals and p.away_goals == match.away_goals]
        for p in exact_preds:
            p_name = p.player.get_full_name() if p.player.get_full_name() else (
                f"{p.player.first_name} {p.player.last_name}".strip() if p.player.first_name else p.player.email
            )
            player_fullpotts[p_name] = player_fullpotts.get(p_name, 0) + 1

        if len(exact_preds) == 1:
            hero = exact_preds[0]
            hero_name = hero.player.get_full_name() if hero.player.get_full_name() else (
                f"{hero.player.first_name} {hero.player.last_name}".strip() if hero.player.first_name else hero.player.email
            )
            desc = f"{hero_name} var den ENDA spelaren i hela gänget som spikade det exakta resultatet {match.home_goals}-{match.away_goals} i {match.home_team} vs {match.away_team}."
            event, _ = InsightEvent.objects.get_or_create(
                tournament=tournament,
                type='OUTLIER_VICTORY',
                player_name=hero_name,
                description=desc,
                defaults={'importance_score': 95, 'matchday_reference': match.match_number or 1}
            )
            events_created.append(event)

        # 3. Detect Goal Fest (total goals >= 4)
        if (match.home_goals + match.away_goals) >= 4:
            desc = f"Målfest i {match.home_team} vs {match.away_team}! Matchen bjöd på hela {match.home_goals + match.away_goals} mål ({match.home_goals}-{match.away_goals}), vilket rörde om hårt i tabellen."
            event, _ = InsightEvent.objects.get_or_create(
                tournament=tournament,
                type='GOAL_FEST',
                description=desc,
                defaults={'importance_score': 75, 'matchday_reference': match.match_number or 1}
            )
            events_created.append(event)

    # 4. Detect Multiple Fullpotts (2+ exact scorelines by one player)
    for p_name, count in player_fullpotts.items():
        if count >= 2:
            desc = f"{p_name} storspelade i omgången och spikade hela {count} exakta fullpottar!"
            event, _ = InsightEvent.objects.get_or_create(
                tournament=tournament,
                type='THREE_FULLPOTTS',
                player_name=p_name,
                description=desc,
                defaults={'importance_score': 92, 'matchday_reference': matchday_number or 1}
            )
            events_created.append(event)

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
