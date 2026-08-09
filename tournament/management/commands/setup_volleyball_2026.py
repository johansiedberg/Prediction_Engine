import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from tournament.models import (
    Tournament, PointSystem, Group, Team, KnockoutStage, Match, Sidebet
)

VOLLEYBALL_GROUPS = {
    'Grupp A': {'order': 1, 'teams': ['Polen', 'Italien', 'Japan', 'Brasilien']},
    'Grupp B': {'order': 2, 'teams': ['USA', 'Frankrike', 'Slovenien', 'Serbien']},
    'Grupp C': {'order': 3, 'teams': ['Argentina', 'Tyskland', 'Kanada', 'Kuba']},
    'Grupp D': {'order': 4, 'teams': ['Nederländerna', 'Iran', 'Egypten', 'Tunisien']},
    'Grupp E': {'order': 5, 'teams': ['Kina', 'Sydkorea', 'Australien', 'Finland']},
    'Grupp F': {'order': 6, 'teams': ['Belgien', 'Turkiet', 'Tjeckien', 'Ukraina']},
    'Grupp G': {'order': 7, 'teams': ['Bulgarien', 'Qatar', 'Kamerun', 'Mexiko']},
    'Grupp H': {'order': 8, 'teams': ['Chile', 'Portugal', 'Algeriet', 'Spanien']},
}

KNOCKOUT_STAGES = [
    {'name': 'Åttondelsfinaler (Round of 16)', 'order': 1},
    {'name': 'Kvartfinaler', 'order': 2},
    {'name': 'Semifinaler', 'order': 3},
    {'name': 'Bronsmatch', 'order': 4},
    {'name': 'Final', 'order': 5},
]

SIDEBETS = [
    {'question': 'Vilket land vinner FIVB Volleyball World Championship 2026?', 'points': 10, 'type': 'TEAM'},
    {'question': 'Vilken kontinent har flest lag i semifinalerna?', 'points': 5, 'type': 'TEXT'},
]

class Command(BaseCommand):
    help = 'Seeds FIVB Volleyball World Championship 2026 (32 teams, 8 groups, 64 matches, 3-2-1-0 Volleyball Point System).'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Seeding FIVB Volleyball World Championship 2026...'))
        admin_user = User.objects.filter(is_superuser=True).first() or User.objects.first()

        tournament, _ = Tournament.objects.update_or_create(
            name='FIVB Volleyball World Championship 2026',
            defaults={'admin': admin_user, 'is_active': False}
        )

        PointSystem.objects.update_or_create(
            tournament=tournament,
            defaults={
                'match_correct_goals_per_team': 3,
                'match_correct_total_goals': 1,
                'match_correct_1x2': 3,
                'group_correct_placement': 2,
                'group_correct_points': 1,
                'group_correct_goals_scored': 1, # Set Wins
                'group_correct_goals_conceded': 1, # Set Losses
                'group_correct_goal_diff': 1, # Set Ratio
                'group_team_qualified': 0,
                'knockout_round_of_16': 3,
                'knockout_quarterfinal': 4,
                'knockout_semifinal': 5,
                'knockout_bronze_match': 5,
                'knockout_final': 8,
            }
        )

        tournament.tournament_groups.all().delete()
        tournament.knockout_stages.all().delete()
        tournament.teams.all().delete()
        tournament.matches.all().delete()
        tournament.sidebets.all().delete()

        match_count = 0
        base_date = datetime.datetime(2026, 9, 12, 17, 0)

        for g_name, g_info in VOLLEYBALL_GROUPS.items():
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
                m_date = base_date + datetime.timedelta(days=(match_count % 8), hours=(idx * 3))
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
            # Round of 16 (49 to 56)
            {'stage': 'Åttondelsfinaler (Round of 16)', 'num': 49, 'home': '1st Group A', 'away': '2nd Group B'},
            {'stage': 'Åttondelsfinaler (Round of 16)', 'num': 50, 'home': '1st Group C', 'away': '2nd Group D'},
            {'stage': 'Åttondelsfinaler (Round of 16)', 'num': 51, 'home': '1st Group E', 'away': '2nd Group F'},
            {'stage': 'Åttondelsfinaler (Round of 16)', 'num': 52, 'home': '1st Group G', 'away': '2nd Group H'},
            {'stage': 'Åttondelsfinaler (Round of 16)', 'num': 53, 'home': '1st Group B', 'away': '2nd Group A'},
            {'stage': 'Åttondelsfinaler (Round of 16)', 'num': 54, 'home': '1st Group D', 'away': '2nd Group C'},
            {'stage': 'Åttondelsfinaler (Round of 16)', 'num': 55, 'home': '1st Group F', 'away': '2nd Group E'},
            {'stage': 'Åttondelsfinaler (Round of 16)', 'num': 56, 'home': '1st Group H', 'away': '2nd Group G'},
            # Quarterfinals (57 to 60)
            {'stage': 'Kvartfinaler', 'num': 57, 'home': 'Winner Match 49', 'away': 'Winner Match 50'},
            {'stage': 'Kvartfinaler', 'num': 58, 'home': 'Winner Match 51', 'away': 'Winner Match 52'},
            {'stage': 'Kvartfinaler', 'num': 59, 'home': 'Winner Match 53', 'away': 'Winner Match 54'},
            {'stage': 'Kvartfinaler', 'num': 60, 'home': 'Winner Match 55', 'away': 'Winner Match 56'},
            # Semifinals (61 to 62)
            {'stage': 'Semifinaler', 'num': 61, 'home': 'Winner Match 57', 'away': 'Winner Match 58'},
            {'stage': 'Semifinaler', 'num': 62, 'home': 'Winner Match 59', 'away': 'Winner Match 60'},
            # Bronze & Final (63, 64)
            {'stage': 'Bronsmatch', 'num': 63, 'home': 'Loser Match 61', 'away': 'Loser Match 62'},
            {'stage': 'Final', 'num': 64, 'home': 'Winner Match 61', 'away': 'Winner Match 62'},
        ]

        for km in knockout_matches:
            st = stage_map.get(km['stage'])
            Match.objects.create(
                tournament=tournament,
                stage=st,
                match_number=km['num'],
                home_team=km['home'],
                away_team=km['away']
            )

        for sb in SIDEBETS:
            Sidebet.objects.create(tournament=tournament, question=sb['question'], points=sb['points'], question_type=sb['type'])

        self.stdout.write(self.style.SUCCESS(f'Successfully seeded "FIVB Volleyball World Championship 2026" with 32 teams, 8 groups, and 64 matches!'))
