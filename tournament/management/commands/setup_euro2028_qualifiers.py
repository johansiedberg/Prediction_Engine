import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from tournament.models import (
    Tournament, PointSystem, Group, Team, KnockoutStage, Match, Sidebet, TournamentSubmission
)

GROUPS_DATA = {
    'Grupp A': {'order': 1, 'teams': ['A1', 'A2', 'A3', 'A4']},
    'Grupp B': {'order': 2, 'teams': ['B1', 'B2', 'B3', 'B4']},
    'Grupp C': {'order': 3, 'teams': ['C1', 'C2', 'C3', 'C4']},
    'Grupp D': {'order': 4, 'teams': ['D1', 'D2', 'D3', 'D4']},
    'Grupp E': {'order': 5, 'teams': ['E1', 'E2', 'E3', 'E4']},
    'Grupp F': {'order': 6, 'teams': ['F1', 'F2', 'F3', 'F4']},
    'Grupp G': {'order': 7, 'teams': ['G1', 'G2', 'G3', 'G4', 'G5']},
    'Grupp H': {'order': 8, 'teams': ['H1', 'H2', 'H3', 'H4', 'H5']},
    'Grupp I': {'order': 9, 'teams': ['I1', 'I2', 'I3', 'I4', 'I5']},
    'Grupp J': {'order': 10, 'teams': ['J1', 'J2', 'J3', 'J4', 'J5']},
    'Grupp K': {'order': 11, 'teams': ['K1', 'K2', 'K3', 'K4', 'K5']},
    'Grupp L': {'order': 12, 'teams': ['L1', 'L2', 'L3', 'L4', 'L5']},
}

MD_DATES_4TEAMS = [
    datetime.datetime(2027, 3, 25, 20, 45),  # MD 1
    datetime.datetime(2027, 3, 28, 20, 45),  # MD 2
    datetime.datetime(2027, 6, 10, 20, 45),  # MD 3
    datetime.datetime(2027, 6, 13, 20, 45),  # MD 4
    datetime.datetime(2027, 9, 2, 20, 45),   # MD 5
    datetime.datetime(2027, 9, 5, 20, 45),   # MD 6
]

MD_DATES_5TEAMS = [
    datetime.datetime(2027, 3, 25, 20, 45),  # MD 1
    datetime.datetime(2027, 3, 28, 20, 45),  # MD 2
    datetime.datetime(2027, 6, 10, 20, 45),  # MD 3
    datetime.datetime(2027, 6, 13, 20, 45),  # MD 4
    datetime.datetime(2027, 9, 2, 20, 45),   # MD 5
    datetime.datetime(2027, 9, 5, 20, 45),   # MD 6
    datetime.datetime(2027, 10, 7, 20, 45),  # MD 7
    datetime.datetime(2027, 10, 10, 20, 45), # MD 8
    datetime.datetime(2027, 11, 11, 20, 45), # MD 9
    datetime.datetime(2027, 11, 14, 20, 45), # MD 10
]

PLAYOFF_STAGES = [
    {'name': 'Play-off Semifinals (March 2028)', 'order': 1},
    {'name': 'Play-off Finals (March 2028)', 'order': 2},
]

SIDEBETS_DATA = [
    {
        'question': 'Vilket lag tar flest poäng totalt i kvalgruppspelet?',
        'points': 5,
        'question_type': 'TEAM',
    },
    {
        'question': 'Hur många av de 4 värdnationerna (England, Irland, Skottland, Wales) kvalificerar sig direkt till EURO 2028?',
        'points': 5,
        'question_type': 'TEXT',
    },
    {
        'question': 'Vilket lag blir den bäst rankade grupptvåan (efter borträkning av 5:e placerade laget)?',
        'points': 5,
        'question_type': 'TEAM',
    },
    {
        'question': 'Vilket lag kniper sista slutspelsplatsen via Playoff Väg A?',
        'points': 5,
        'question_type': 'TEAM',
    },
]


class Command(BaseCommand):
    help = 'Seeds EURO 2028 Qualifier tournament with 54 placeholder teams (A1-L5 pending Dec 2026 draw), host safety net, runners-up rankings, and play-offs.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Initializing EURO 2028 Qualifier setup with pure pre-draw placeholders...'))

        admin_user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if not admin_user:
            self.stdout.write(self.style.ERROR('No admin user found in database. Create a superuser first.'))
            return

        tournament, created = Tournament.objects.update_or_create(
            name='EURO 2028 Qualifier',
            defaults={
                'admin': admin_user,
                'is_active': False,
                'is_paused': False,
                'has_runners_up_table': True,
                'has_host_ranking_table': True,
                'has_best_thirds_table': False,
            }
        )

        PointSystem.objects.update_or_create(
            tournament=tournament,
            defaults={
                'match_correct_goals_per_team': 3,
                'match_correct_total_goals': 1,
                'match_correct_1x2': 3,
                'group_correct_placement': 2,
                'group_correct_points': 1,
                'group_correct_goals_scored': 1,
                'group_correct_goals_conceded': 1,
                'group_correct_goal_diff': 1,
                'group_team_qualified': 0,
                'qualifying_table_team_qualified': 5,
                'qualifying_table_exact_rank': 0,
                'qualifying_table_points': 0,
                'qualifying_table_goals_scored': 0,
                'qualifying_table_goals_conceded': 0,
                'qualifying_table_goal_diff': 0,
                'knockout_round_of_16': 3,
                'knockout_quarterfinal': 4,
                'knockout_semifinal': 5,
                'knockout_final': 8,
            }
        )

        all_players = User.objects.filter(is_staff=False, is_superuser=False)
        if all_players.exists():
            tournament.players.add(*all_players)
            for player in all_players:
                TournamentSubmission.objects.get_or_create(tournament=tournament, player=player)

        tournament.tournament_groups.all().delete()
        tournament.knockout_stages.all().delete()
        tournament.teams.all().delete()
        tournament.matches.all().delete()
        tournament.sidebets.all().delete()

        total_teams_count = 0
        match_counter = 1

        for g_name, g_info in GROUPS_DATA.items():
            group_obj, _ = Group.objects.update_or_create(
                tournament=tournament,
                name=g_name,
                defaults={'order': g_info['order']}
            )

            group_teams = []
            for team_name in g_info['teams']:
                team_obj, _ = Team.objects.update_or_create(
                    tournament=tournament,
                    name=team_name,
                    defaults={'group': group_obj}
                )
                group_teams.append(team_obj)
                total_teams_count += 1

            num_teams = len(group_teams)
            dates_list = MD_DATES_4TEAMS if num_teams == 4 else MD_DATES_5TEAMS

            match_idx = 0
            for i in range(num_teams):
                for j in range(i + 1, num_teams):
                    t1, t2 = group_teams[i], group_teams[j]
                    
                    # Home match t1 vs t2
                    d1 = dates_list[match_idx % len(dates_list)] + datetime.timedelta(hours=(match_counter % 3))
                    Match.objects.create(
                        tournament=tournament,
                        group=group_obj,
                        home_team=t1.name,
                        away_team=t2.name,
                        match_number=match_counter,
                        date_time=d1
                    )
                    match_counter += 1
                    match_idx += 1

                    # Away match t2 vs t1
                    d2 = dates_list[match_idx % len(dates_list)] + datetime.timedelta(hours=(match_counter % 3))
                    Match.objects.create(
                        tournament=tournament,
                        group=group_obj,
                        home_team=t2.name,
                        away_team=t1.name,
                        match_number=match_counter,
                        date_time=d2
                    )
                    match_counter += 1
                    match_idx += 1

        stage_map = {}
        for stage_info in PLAYOFF_STAGES:
            stage_obj, _ = KnockoutStage.objects.update_or_create(
                tournament=tournament,
                name=stage_info['name'],
                defaults={'order': stage_info['order']}
            )
            stage_map[stage_info['name']] = stage_obj

        playoff_semi_date = datetime.datetime(2028, 3, 23, 20, 45)
        playoff_final_date = datetime.datetime(2028, 3, 28, 20, 45)

        first_ko_num = match_counter
        playoff_matches = [
            # Path A
            {'stage': 'Play-off Semifinals (March 2028)', 'match_number': first_ko_num, 'home': 'Path A Semi 1 (Pot 1)', 'away': 'Path A Semi 1 (Pot 4)', 'date': playoff_semi_date},
            {'stage': 'Play-off Semifinals (March 2028)', 'match_number': first_ko_num + 1, 'home': 'Path A Semi 2 (Pot 2)', 'away': 'Path A Semi 2 (Pot 3)', 'date': playoff_semi_date},
            {'stage': 'Play-off Finals (March 2028)', 'match_number': first_ko_num + 2, 'home': f'Winner Match {first_ko_num}', 'away': f'Winner Match {first_ko_num + 1}', 'date': playoff_final_date},
            # Path B
            {'stage': 'Play-off Semifinals (March 2028)', 'match_number': first_ko_num + 3, 'home': 'Path B Semi 1 (Pot 1)', 'away': 'Path B Semi 1 (Pot 4)', 'date': playoff_semi_date + datetime.timedelta(hours=1)},
            {'stage': 'Play-off Semifinals (March 2028)', 'match_number': first_ko_num + 4, 'home': 'Path B Semi 2 (Pot 2)', 'away': 'Path B Semi 2 (Pot 3)', 'date': playoff_semi_date + datetime.timedelta(hours=1)},
            {'stage': 'Play-off Finals (March 2028)', 'match_number': first_ko_num + 5, 'home': f'Winner Match {first_ko_num + 3}', 'away': f'Winner Match {first_ko_num + 4}', 'date': playoff_final_date + datetime.timedelta(hours=1)},
            # Path C
            {'stage': 'Play-off Semifinals (March 2028)', 'match_number': first_ko_num + 6, 'home': 'Path C Semi 1 (Pot 1)', 'away': 'Path C Semi 1 (Pot 4)', 'date': playoff_semi_date + datetime.timedelta(hours=2)},
            {'stage': 'Play-off Semifinals (March 2028)', 'match_number': first_ko_num + 7, 'home': 'Path C Semi 2 (Pot 2)', 'away': 'Path C Semi 2 (Pot 3)', 'date': playoff_semi_date + datetime.timedelta(hours=2)},
            {'stage': 'Play-off Finals (March 2028)', 'match_number': first_ko_num + 8, 'home': f'Winner Match {first_ko_num + 6}', 'away': f'Winner Match {first_ko_num + 7}', 'date': playoff_final_date + datetime.timedelta(hours=2)},
        ]

        for pm in playoff_matches:
            st = stage_map.get(pm['stage'])
            Match.objects.create(
                tournament=tournament,
                match_number=pm['match_number'],
                stage=st,
                home_team=pm['home'],
                away_team=pm['away'],
                date_time=pm['date']
            )

        for sb_info in SIDEBETS_DATA:
            Sidebet.objects.get_or_create(
                tournament=tournament,
                question=sb_info['question'],
                defaults={
                    'points': sb_info['points'],
                    'question_type': sb_info['question_type']
                }
            )

        self.stdout.write(self.style.SUCCESS(f'Successfully configured "EURO 2028 Qualifier" with {total_teams_count} pre-draw placeholders (A1-L5)!'))
