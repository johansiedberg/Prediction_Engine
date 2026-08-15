import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from tournament.models import (
    Tournament, PointSystem, Group, Team, KnockoutStage, Match, Sidebet, TournamentSubmission
)

EURO_2028_GROUPS = {
    'Grupp A': {'order': 1, 'teams': ['A1', 'A2', 'A3', 'A4']},
    'Grupp B': {'order': 2, 'teams': ['B1', 'B2', 'B3', 'B4']},
    'Grupp C': {'order': 3, 'teams': ['C1', 'C2', 'C3', 'C4']},
    'Grupp D': {'order': 4, 'teams': ['D1', 'D2', 'D3', 'D4']},
    'Grupp E': {'order': 5, 'teams': ['E1', 'E2', 'E3', 'E4']},
    'Grupp F': {'order': 6, 'teams': ['F1', 'F2', 'F3', 'F4']},
}

KNOCKOUT_STAGES = [
    {'name': 'Åttondelsfinaler (Round of 16)', 'order': 1},
    {'name': 'Kvartfinaler', 'order': 2},
    {'name': 'Semifinaler', 'order': 3},
    {'name': 'Final', 'order': 4},
]

SIDEBETS = [
    {'question': 'Vilket land vinner UEFA EURO 2028?', 'points': 10, 'type': 'TEAM'},
    {'question': 'Vilket lag tar flest poäng totalt i gruppspelet?', 'points': 5, 'type': 'TEAM'},
    {'question': 'Vilket land gör flest mål under hela turneringen?', 'points': 5, 'type': 'TEAM'},
    {'question': 'Hur många av de 4 värdnationerna (England, Skottland, Wales, Irland) når minst kvartsfinal?', 'points': 5, 'type': 'TEXT'},
]


class Command(BaseCommand):
    help = 'Seeds EURO 2028 Final Tournament with 24 pre-draw placeholder teams (A1-F4), Best-Thirds table, and 51 matches.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Initializing EURO 2028 Final Tournament setup with pre-draw placeholders...'))
        admin_user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if not admin_user:
            self.stdout.write(self.style.ERROR('No admin user found in database. Create a superuser first.'))
            return

        tournament, created = Tournament.objects.update_or_create(
            name='EURO 2028',
            defaults={
                'admin': admin_user,
                'is_active': False,
                'is_paused': False,
                'has_runners_up_table': False,
                'has_host_ranking_table': False,
                'has_best_thirds_table': True,
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

        match_count = 0
        base_date = datetime.datetime(2028, 6, 9, 21, 0)

        # Seed 6 Groups, 24 Placeholder Teams, and 36 Group Matches
        for g_name, g_info in EURO_2028_GROUPS.items():
            group, _ = Group.objects.get_or_create(
                tournament=tournament, name=g_name, defaults={'order': g_info['order']}
            )

            t_objs = []
            for t_name in g_info['teams']:
                team, _ = Team.objects.get_or_create(
                    tournament=tournament, name=t_name, defaults={'group': group}
                )
                t_objs.append(team)

            fixtures = [
                (t_objs[0], t_objs[1]), (t_objs[2], t_objs[3]),
                (t_objs[0], t_objs[2]), (t_objs[1], t_objs[3]),
                (t_objs[0], t_objs[3]), (t_objs[1], t_objs[2]),
            ]

            for idx, (h, a) in enumerate(fixtures):
                match_count += 1
                m_date = base_date + datetime.timedelta(days=(match_count // 3), hours=((idx % 3) * 3))
                Match.objects.create(
                    tournament=tournament,
                    group=group,
                    match_number=match_count,
                    home_team=h.name,
                    away_team=a.name,
                    date_time=m_date
                )

        stage_map = {}
        for st in KNOCKOUT_STAGES:
            stage_obj, _ = KnockoutStage.objects.get_or_create(
                tournament=tournament, name=st['name'], defaults={'order': st['order']}
            )
            stage_map[st['name']] = stage_obj

        knockout_matches = [
            # Round of 16 (24 June - 27 June 2028)
            {'stage': 'Åttondelsfinaler (Round of 16)', 'num': 37, 'home': '2nd Group A', 'away': '2nd Group B', 'date': datetime.datetime(2028, 6, 24, 18, 0)},
            {'stage': 'Åttondelsfinaler (Round of 16)', 'num': 38, 'home': '1st Group A', 'away': '2nd Group C', 'date': datetime.datetime(2028, 6, 24, 21, 0)},
            {'stage': 'Åttondelsfinaler (Round of 16)', 'num': 39, 'home': '1st Group C', 'away': '3rd Group D/E/F', 'date': datetime.datetime(2028, 6, 25, 18, 0)},
            {'stage': 'Åttondelsfinaler (Round of 16)', 'num': 40, 'home': '1st Group B', 'away': '3rd Group A/D/E/F', 'date': datetime.datetime(2028, 6, 25, 21, 0)},
            {'stage': 'Åttondelsfinaler (Round of 16)', 'num': 41, 'home': '1st Group E', 'away': '3rd Group A/B/C/D', 'date': datetime.datetime(2028, 6, 26, 18, 0)},
            {'stage': 'Åttondelsfinaler (Round of 16)', 'num': 42, 'home': '1st Group F', 'away': '2nd Group E', 'date': datetime.datetime(2028, 6, 26, 21, 0)},
            {'stage': 'Åttondelsfinaler (Round of 16)', 'num': 43, 'home': '1st Group D', 'away': '3rd Group B/C/F', 'date': datetime.datetime(2028, 6, 27, 18, 0)},
            {'stage': 'Åttondelsfinaler (Round of 16)', 'num': 44, 'home': '2nd Group D', 'away': '2nd Group F', 'date': datetime.datetime(2028, 6, 27, 21, 0)},
            # Quarterfinals (30 June - 1 July 2028)
            {'stage': 'Kvartfinaler', 'num': 45, 'home': 'Winner Match 37', 'away': 'Winner Match 39', 'date': datetime.datetime(2028, 6, 30, 18, 0)},
            {'stage': 'Kvartfinaler', 'num': 46, 'home': 'Winner Match 38', 'away': 'Winner Match 42', 'date': datetime.datetime(2028, 6, 30, 21, 0)},
            {'stage': 'Kvartfinaler', 'num': 47, 'home': 'Winner Match 40', 'away': 'Winner Match 41', 'date': datetime.datetime(2028, 7, 1, 18, 0)},
            {'stage': 'Kvartfinaler', 'num': 48, 'home': 'Winner Match 43', 'away': 'Winner Match 44', 'date': datetime.datetime(2028, 7, 1, 21, 0)},
            # Semifinals (4 July - 5 July 2028)
            {'stage': 'Semifinaler', 'num': 49, 'home': 'Winner Match 45', 'away': 'Winner Match 46', 'date': datetime.datetime(2028, 7, 4, 21, 0)},
            {'stage': 'Semifinaler', 'num': 50, 'home': 'Winner Match 47', 'away': 'Winner Match 48', 'date': datetime.datetime(2028, 7, 5, 21, 0)},
            # Final (9 July 2028)
            {'stage': 'Final', 'num': 51, 'home': 'Winner Match 49', 'away': 'Winner Match 50', 'date': datetime.datetime(2028, 7, 9, 21, 0)},
        ]

        for km in knockout_matches:
            st = stage_map.get(km['stage'])
            Match.objects.create(
                tournament=tournament,
                stage=st,
                match_number=km['num'],
                home_team=km['home'],
                away_team=km['away'],
                date_time=km['date']
            )

        for sb in SIDEBETS:
            Sidebet.objects.create(tournament=tournament, question=sb['question'], points=sb['points'], question_type=sb['type'])

        self.stdout.write(self.style.SUCCESS(f'Successfully seeded "EURO 2028" with 24 pre-draw placeholders (A1-F4) and 51 matches!'))
