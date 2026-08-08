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
            description="Turneringen laddar inför nästa stora drabbning i gruppspelet.",
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
                    defaults={'importance_score': 90, 'matchday_reference': match.match_number}
                )
                events_created.append(event)

        # 2. Detect Outlier Victory (exact scoreline predicted by only 1 player)
        exact_preds = [p for p in preds if p.home_goals == match.home_goals and p.away_goals == match.away_goals]
        for p in exact_preds:
            p_name = p.player.first_name + " " + p.player.last_name if p.player.first_name else p.player.username
            player_fullpotts[p_name] = player_fullpotts.get(p_name, 0) + 1

        if len(exact_preds) == 1:
            hero = exact_preds[0]
            hero_name = hero.player.first_name + " " + hero.player.last_name if hero.player.first_name else hero.player.username
            desc = f"{hero_name} var den ENDA spelaren i hela gänget som spikade det exakta resultatet {match.home_goals}-{match.away_goals} i {match.home_team} vs {match.away_team}."
            event, _ = InsightEvent.objects.get_or_create(
                tournament=tournament,
                type='OUTLIER_VICTORY',
                player_name=hero_name,
                description=desc,
                defaults={'importance_score': 95, 'matchday_reference': match.match_number}
            )
            events_created.append(event)

        # 3. Detect Goal Fest (total goals >= 4)
        if (match.home_goals + match.away_goals) >= 4:
            desc = f"Målfest i {match.home_team} vs {match.away_team}! Matchen bjöd på hela {match.home_goals + match.away_goals} mål ({match.home_goals}-{match.away_goals}), vilket rörde om hårt i tabellen."
            event, _ = InsightEvent.objects.get_or_create(
                tournament=tournament,
                type='GOAL_FEST',
                description=desc,
                defaults={'importance_score': 75, 'matchday_reference': match.match_number}
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
    Scans tournament progress and triggers Gazetta Special Editions for any reached round milestones (1-9).
    """
    from tournament.models import DailyGazette, TournamentSubmission, KnockoutStage
    from tournament.editorial_engine.special_edition_reporter import SpecialEditionReporter

    triggered_editions = []

    # Round 1: All player predictions verified
    r1_exists = DailyGazette.objects.filter(tournament=tournament, is_special_edition=True, round_number=1).exists()
    if not r1_exists:
        subs = TournamentSubmission.objects.filter(tournament=tournament)
        if subs.exists() and all(s.is_verified for s in subs):
            gazette = SpecialEditionReporter.draft_special_edition(tournament, 1)
            triggered_editions.append(gazette)

    # Group stage teams helper
    all_teams = list(tournament.teams.all())
    all_groups = list(tournament.tournament_groups.all())

    # Helper function to count finished matches played by a team
    def get_team_finished_matches_count(team):
        return Match.objects.filter(
            tournament=tournament, is_finished=True
        ).filter(Q(home_team=team.name) | Q(away_team=team.name)).count()

    # Round 2: Every team played >= 1 group match
    r2_exists = DailyGazette.objects.filter(tournament=tournament, is_special_edition=True, round_number=2).exists()
    if not r2_exists and all_teams:
        if all(get_team_finished_matches_count(t) >= 1 for t in all_teams):
            gazette = SpecialEditionReporter.draft_special_edition(tournament, 2)
            triggered_editions.append(gazette)

    # Round 3: Every team played >= 2 group matches
    r3_exists = DailyGazette.objects.filter(tournament=tournament, is_special_edition=True, round_number=3).exists()
    if not r3_exists and all_teams:
        if all(get_team_finished_matches_count(t) >= 2 for t in all_teams):
            gazette = SpecialEditionReporter.draft_special_edition(tournament, 3)
            triggered_editions.append(gazette)

    # Round 4: Every team played >= 3 group matches (Group stage complete)
    r4_exists = DailyGazette.objects.filter(tournament=tournament, is_special_edition=True, round_number=4).exists()
    if not r4_exists and all_groups:
        all_group_matches = Match.objects.filter(group__in=all_groups)
        if all_group_matches.exists() and all(m.is_finished for m in all_group_matches):
            gazette = SpecialEditionReporter.draft_special_edition(tournament, 4)
            triggered_editions.append(gazette)

    # Helper for knockout stages
    def is_knockout_stage_finished(stage_keyword):
        ks = KnockoutStage.objects.filter(tournament=tournament, name__icontains=stage_keyword).first()
        if not ks:
            return False
        matches = ks.matches.all()
        return matches.exists() and all(m.is_finished for m in matches)

    # Round 5: Round of 16 played
    r5_exists = DailyGazette.objects.filter(tournament=tournament, is_special_edition=True, round_number=5).exists()
    if not r5_exists and (is_knockout_stage_finished('16') or is_knockout_stage_finished('åttondel')):
        gazette = SpecialEditionReporter.draft_special_edition(tournament, 5)
        triggered_editions.append(gazette)

    # Round 6: Quarterfinals played
    r6_exists = DailyGazette.objects.filter(tournament=tournament, is_special_edition=True, round_number=6).exists()
    if not r6_exists and (is_knockout_stage_finished('kvart') or is_knockout_stage_finished('quarter')):
        gazette = SpecialEditionReporter.draft_special_edition(tournament, 6)
        triggered_editions.append(gazette)

    # Round 7: Semifinals played
    r7_exists = DailyGazette.objects.filter(tournament=tournament, is_special_edition=True, round_number=7).exists()
    if not r7_exists and is_knockout_stage_finished('semi'):
        gazette = SpecialEditionReporter.draft_special_edition(tournament, 7)
        triggered_editions.append(gazette)

    # Round 8: Bronze match played
    r8_exists = DailyGazette.objects.filter(tournament=tournament, is_special_edition=True, round_number=8).exists()
    if not r8_exists and (is_knockout_stage_finished('brons') or is_knockout_stage_finished('bronze')):
        gazette = SpecialEditionReporter.draft_special_edition(tournament, 8)
        triggered_editions.append(gazette)

    # Round 9: Final played
    r9_exists = DailyGazette.objects.filter(tournament=tournament, is_special_edition=True, round_number=9).exists()
    if not r9_exists and is_knockout_stage_finished('final'):
        gazette = SpecialEditionReporter.draft_special_edition(tournament, 9)
        triggered_editions.append(gazette)

    # Round 10: Full tournament re-cap
    r10_exists = DailyGazette.objects.filter(tournament=tournament, is_special_edition=True, round_number=10).exists()
    if not r10_exists and is_knockout_stage_finished('final'):
        gazette = SpecialEditionReporter.draft_special_edition(tournament, 10)
        triggered_editions.append(gazette)

    return triggered_editions

