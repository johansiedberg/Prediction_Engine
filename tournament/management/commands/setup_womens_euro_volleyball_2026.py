import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from tournament.models import (
    Tournament, PointSystem, Group, Team, KnockoutStage, Match, Sidebet, TournamentSubmission
)

POOLS = {
    'Pool A': {
        'order': 1,
        'city': 'Istanbul, Turkiet',
        'teams': ['Turkiet', 'Lettland', 'Polen', 'Tyskland', 'Slovenien', 'Ungern']
    },
    'Pool B': {
        'order': 2,
        'city': 'Brno, Tjeckien',
        'teams': ['Tjeckien', 'Österrike', 'Serbien', 'Bulgarien', 'Ukraina', 'Grekland']
    },
    'Pool C': {
        'order': 3,
        'city': 'Baku, Azerbajdzjan',
        'teams': ['Azerbajdzjan', 'Portugal', 'Nederländerna', 'Belgien', 'Rumänien', 'Spanien']
    },
    'Pool D': {
        'order': 4,
        'city': 'Göteborg, Sverige',
        'teams': ['Sverige', 'Montenegro', 'Italien', 'Frankrike', 'Slovakien', 'Kroatien']
    },
}

GROUP_MATCHES = [
    # Pool A (Istanbul, Turkey) - Matches 1 to 15
    {'num': 1, 'group': 'Pool A', 'home': 'Turkiet', 'away': 'Lettland', 'date': '2026-08-21 19:00'},
    {'num': 2, 'group': 'Pool A', 'home': 'Tyskland', 'away': 'Slovenien', 'date': '2026-08-22 16:00'},
    {'num': 3, 'group': 'Pool A', 'home': 'Ungern', 'away': 'Polen', 'date': '2026-08-22 19:00'},
    {'num': 4, 'group': 'Pool A', 'home': 'Lettland', 'away': 'Tyskland', 'date': '2026-08-23 16:00'},
    {'num': 5, 'group': 'Pool A', 'home': 'Slovenien', 'away': 'Turkiet', 'date': '2026-08-23 19:00'},
    {'num': 6, 'group': 'Pool A', 'home': 'Polen', 'away': 'Lettland', 'date': '2026-08-24 16:00'},
    {'num': 7, 'group': 'Pool A', 'home': 'Turkiet', 'away': 'Ungern', 'date': '2026-08-24 19:00'},
    {'num': 8, 'group': 'Pool A', 'home': 'Ungern', 'away': 'Tyskland', 'date': '2026-08-25 16:00'},
    {'num': 9, 'group': 'Pool A', 'home': 'Polen', 'away': 'Slovenien', 'date': '2026-08-25 19:00'},
    {'num': 10, 'group': 'Pool A', 'home': 'Slovenien', 'away': 'Lettland', 'date': '2026-08-26 16:00'},
    {'num': 11, 'group': 'Pool A', 'home': 'Tyskland', 'away': 'Turkiet', 'date': '2026-08-26 19:00'},
    {'num': 12, 'group': 'Pool A', 'home': 'Polen', 'away': 'Tyskland', 'date': '2026-08-27 16:00'},
    {'num': 13, 'group': 'Pool A', 'home': 'Lettland', 'away': 'Ungern', 'date': '2026-08-27 19:00'},
    {'num': 14, 'group': 'Pool A', 'home': 'Slovenien', 'away': 'Ungern', 'date': '2026-08-28 16:00'},
    {'num': 15, 'group': 'Pool A', 'home': 'Turkiet', 'away': 'Polen', 'date': '2026-08-28 19:00'},

    # Pool B (Brno, Czech Republic) - Matches 16 to 30
    {'num': 16, 'group': 'Pool B', 'home': 'Österrike', 'away': 'Serbien', 'date': '2026-08-21 14:00'},
    {'num': 17, 'group': 'Pool B', 'home': 'Bulgarien', 'away': 'Ukraina', 'date': '2026-08-21 17:00'},
    {'num': 18, 'group': 'Pool B', 'home': 'Tjeckien', 'away': 'Grekland', 'date': '2026-08-21 20:00'},
    {'num': 19, 'group': 'Pool B', 'home': 'Ukraina', 'away': 'Grekland', 'date': '2026-08-22 16:00'},
    {'num': 20, 'group': 'Pool B', 'home': 'Österrike', 'away': 'Tjeckien', 'date': '2026-08-22 19:00'},
    {'num': 21, 'group': 'Pool B', 'home': 'Grekland', 'away': 'Bulgarien', 'date': '2026-08-23 16:00'},
    {'num': 22, 'group': 'Pool B', 'home': 'Tjeckien', 'away': 'Serbien', 'date': '2026-08-23 19:00'},
    {'num': 23, 'group': 'Pool B', 'home': 'Ukraina', 'away': 'Österrike', 'date': '2026-08-24 16:00'},
    {'num': 24, 'group': 'Pool B', 'home': 'Serbien', 'away': 'Bulgarien', 'date': '2026-08-24 19:00'},
    {'num': 25, 'group': 'Pool B', 'home': 'Grekland', 'away': 'Österrike', 'date': '2026-08-25 16:00'},
    {'num': 26, 'group': 'Pool B', 'home': 'Tjeckien', 'away': 'Ukraina', 'date': '2026-08-25 19:00'},
    {'num': 27, 'group': 'Pool B', 'home': 'Österrike', 'away': 'Bulgarien', 'date': '2026-08-26 16:00'},
    {'num': 28, 'group': 'Pool B', 'home': 'Serbien', 'away': 'Grekland', 'date': '2026-08-26 19:00'},
    {'num': 29, 'group': 'Pool B', 'home': 'Ukraina', 'away': 'Serbien', 'date': '2026-08-27 16:00'},
    {'num': 30, 'group': 'Pool B', 'home': 'Tjeckien', 'away': 'Bulgarien', 'date': '2026-08-27 19:00'},

    # Pool C (Baku, Azerbaijan) - Matches 31 to 45
    {'num': 31, 'group': 'Pool C', 'home': 'Azerbajdzjan', 'away': 'Portugal', 'date': '2026-08-21 19:00'},
    {'num': 32, 'group': 'Pool C', 'home': 'Belgien', 'away': 'Spanien', 'date': '2026-08-22 15:30'},
    {'num': 33, 'group': 'Pool C', 'home': 'Rumänien', 'away': 'Nederländerna', 'date': '2026-08-22 18:30'},
    {'num': 34, 'group': 'Pool C', 'home': 'Portugal', 'away': 'Belgien', 'date': '2026-08-23 15:30'},
    {'num': 35, 'group': 'Pool C', 'home': 'Spanien', 'away': 'Azerbajdzjan', 'date': '2026-08-23 18:30'},
    {'num': 36, 'group': 'Pool C', 'home': 'Nederländerna', 'away': 'Portugal', 'date': '2026-08-24 15:30'},
    {'num': 37, 'group': 'Pool C', 'home': 'Azerbajdzjan', 'away': 'Rumänien', 'date': '2026-08-24 18:30'},
    {'num': 38, 'group': 'Pool C', 'home': 'Rumänien', 'away': 'Belgien', 'date': '2026-08-25 15:30'},
    {'num': 39, 'group': 'Pool C', 'home': 'Nederländerna', 'away': 'Spanien', 'date': '2026-08-25 18:30'},
    {'num': 40, 'group': 'Pool C', 'home': 'Spanien', 'away': 'Portugal', 'date': '2026-08-26 15:30'},
    {'num': 41, 'group': 'Pool C', 'home': 'Belgien', 'away': 'Azerbajdzjan', 'date': '2026-08-26 18:30'},
    {'num': 42, 'group': 'Pool C', 'home': 'Nederländerna', 'away': 'Belgien', 'date': '2026-08-27 15:30'},
    {'num': 43, 'group': 'Pool C', 'home': 'Portugal', 'away': 'Rumänien', 'date': '2026-08-27 18:30'},
    {'num': 44, 'group': 'Pool C', 'home': 'Spanien', 'away': 'Rumänien', 'date': '2026-08-28 15:30'},
    {'num': 45, 'group': 'Pool C', 'home': 'Azerbajdzjan', 'away': 'Nederländerna', 'date': '2026-08-28 18:30'},

    # Pool D (Gothenburg, Sweden) - Matches 46 to 60
    {'num': 46, 'group': 'Pool D', 'home': 'Frankrike', 'away': 'Slovakien', 'date': '2026-08-21 13:00'},
    {'num': 47, 'group': 'Pool D', 'home': 'Kroatien', 'away': 'Italien', 'date': '2026-08-21 16:00'},
    {'num': 48, 'group': 'Pool D', 'home': 'Sverige', 'away': 'Montenegro', 'date': '2026-08-21 19:00'},
    {'num': 49, 'group': 'Pool D', 'home': 'Italien', 'away': 'Montenegro', 'date': '2026-08-22 15:00'},
    {'num': 50, 'group': 'Pool D', 'home': 'Slovakien', 'away': 'Sverige', 'date': '2026-08-22 18:00'},
    {'num': 51, 'group': 'Pool D', 'home': 'Frankrike', 'away': 'Kroatien', 'date': '2026-08-23 15:00'},
    {'num': 52, 'group': 'Pool D', 'home': 'Sverige', 'away': 'Italien', 'date': '2026-08-23 18:00'},
    {'num': 53, 'group': 'Pool D', 'home': 'Kroatien', 'away': 'Slovakien', 'date': '2026-08-24 16:00'},
    {'num': 54, 'group': 'Pool D', 'home': 'Montenegro', 'away': 'Frankrike', 'date': '2026-08-24 19:00'},
    {'num': 55, 'group': 'Pool D', 'home': 'Italien', 'away': 'Slovakien', 'date': '2026-08-25 16:00'},
    {'num': 56, 'group': 'Pool D', 'home': 'Sverige', 'away': 'Kroatien', 'date': '2026-08-25 19:00'},
    {'num': 57, 'group': 'Pool D', 'home': 'Frankrike', 'away': 'Italien', 'date': '2026-08-26 16:00'},
    {'num': 58, 'group': 'Pool D', 'home': 'Slovakien', 'away': 'Montenegro', 'date': '2026-08-26 19:00'},
    {'num': 59, 'group': 'Pool D', 'home': 'Kroatien', 'away': 'Montenegro', 'date': '2026-08-27 16:00'},
    {'num': 60, 'group': 'Pool D', 'home': 'Sverige', 'away': 'Frankrike', 'date': '2026-08-27 19:00'},
]

KNOCKOUT_STAGES = [
    {'name': 'Åttondelsfinaler (Round of 16)', 'order': 1},
    {'name': 'Kvartfinaler', 'order': 2},
    {'name': 'Semifinaler', 'order': 3},
    {'name': 'Bronsmatch', 'order': 4},
    {'name': 'Final', 'order': 5},
]

KNOCKOUT_MATCHES = [
    # Round of 16 (Matches 61 to 68)
    {'num': 61, 'stage': 'Åttondelsfinaler (Round of 16)', 'home': '1st Group A', 'away': '4th Group C', 'date': '2026-08-31 17:00'},
    {'num': 62, 'stage': 'Åttondelsfinaler (Round of 16)', 'home': '2nd Group C', 'away': '3rd Group A', 'date': '2026-08-31 20:00'},
    {'num': 63, 'stage': 'Åttondelsfinaler (Round of 16)', 'home': '1st Group D', 'away': '4th Group B', 'date': '2026-08-30 17:00'},
    {'num': 64, 'stage': 'Åttondelsfinaler (Round of 16)', 'home': '2nd Group B', 'away': '3rd Group D', 'date': '2026-08-30 20:00'},
    {'num': 65, 'stage': 'Åttondelsfinaler (Round of 16)', 'home': '1st Group C', 'away': '4th Group A', 'date': '2026-09-01 17:00'},
    {'num': 66, 'stage': 'Åttondelsfinaler (Round of 16)', 'home': '2nd Group A', 'away': '3rd Group C', 'date': '2026-09-01 20:00'},
    {'num': 67, 'stage': 'Åttondelsfinaler (Round of 16)', 'home': '1st Group B', 'away': '4th Group D', 'date': '2026-08-31 17:00'},
    {'num': 68, 'stage': 'Åttondelsfinaler (Round of 16)', 'home': '2nd Group D', 'away': '3rd Group B', 'date': '2026-08-31 20:00'},

    # Quarterfinals (Matches 69 to 72)
    {'num': 69, 'stage': 'Kvartfinaler', 'home': 'Winner Match 61', 'away': 'Winner Match 62', 'date': '2026-09-03 17:00'},
    {'num': 70, 'stage': 'Kvartfinaler', 'home': 'Winner Match 63', 'away': 'Winner Match 64', 'date': '2026-09-02 17:00'},
    {'num': 71, 'stage': 'Kvartfinaler', 'home': 'Winner Match 65', 'away': 'Winner Match 66', 'date': '2026-09-03 20:00'},
    {'num': 72, 'stage': 'Kvartfinaler', 'home': 'Winner Match 67', 'away': 'Winner Match 68', 'date': '2026-09-02 20:00'},

    # Semifinals (Matches 73 to 74)
    {'num': 73, 'stage': 'Semifinaler', 'home': 'Winner Match 69', 'away': 'Winner Match 70', 'date': '2026-09-05 17:00'},
    {'num': 74, 'stage': 'Semifinaler', 'home': 'Winner Match 71', 'away': 'Winner Match 72', 'date': '2026-09-05 20:00'},

    # 3rd Place & Final (Matches 75 and 76)
    {'num': 75, 'stage': 'Bronsmatch', 'home': 'Loser Match 73', 'away': 'Loser Match 74', 'date': '2026-09-06 16:00'},
    {'num': 76, 'stage': 'Final', 'home': 'Winner Match 73', 'away': 'Winner Match 74', 'date': '2026-09-06 20:00'},
]

SIDEBETS = [
    {'question': "Vilket land vinner 2026 Women's European Volleyball Championship?", 'points': 10, 'type': 'TEAM'},
    {'question': "Vilket land tar silver (2:a plats)?", 'points': 5, 'type': 'TEAM'},
    {'question': "Hur långt når Sverige (värdnation i Pool D Göteborg)?", 'points': 5, 'type': 'TEXT'},
    {'question': "Vilket lag tar flest matchpoäng totalt i gruppspelet (Pool A-D)?", 'points': 5, 'type': 'TEAM'},
    {'question': "Vilket lag vinner Pool D i Scandinavium, Göteborg?", 'points': 5, 'type': 'TEAM'},
]


class Command(BaseCommand):
    help = "Seeds 2026 Women's European Volleyball Championship (24 teams, 4 pools, 76 matches, CEV tournament format)."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding 2026 Women's European Volleyball Championship..."))
        admin_user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if not admin_user:
            self.stdout.write(self.style.ERROR('No admin user found. Create a user first.'))
            return

        tournament, _ = Tournament.objects.update_or_create(
            name="2026 Women's European Volleyball Championship",
            defaults={
                'admin': admin_user,
                'is_active': False,
                'is_paused': False,
                'has_runners_up_table': False,
                'has_host_ranking_table': False,
                'has_best_thirds_table': False,
            }
        )

        # Set logo if file exists
        logo_path = 'tournament/icons/cev_eurovolley_2026_women_logo.png'
        import os
        from django.conf import settings
        if os.path.exists(os.path.join(settings.MEDIA_ROOT, logo_path)):
            tournament.icon = logo_path
            tournament.save(update_fields=['icon'])

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
                'knockout_round_of_16': 3,
                'knockout_quarterfinal': 4,
                'knockout_semifinal': 5,
                'knockout_bronze_match': 5,
                'knockout_final': 8,
            }
        )

        # Enroll all registered players into the tournament
        all_players = User.objects.filter(is_staff=False, is_superuser=False)
        if all_players.exists():
            tournament.players.add(*all_players)
            for player in all_players:
                TournamentSubmission.objects.get_or_create(tournament=tournament, player=player)

        # Clear existing relations
        tournament.tournament_groups.all().delete()
        tournament.knockout_stages.all().delete()
        tournament.teams.all().delete()
        tournament.matches.all().delete()
        tournament.sidebets.all().delete()

        # Create Groups and Teams
        group_map = {}
        for g_name, g_info in POOLS.items():
            group = Group.objects.create(
                tournament=tournament,
                name=g_name,
                order=g_info['order']
            )
            group_map[g_name] = group

            for t_name in g_info['teams']:
                Team.objects.create(
                    tournament=tournament,
                    group=group,
                    name=t_name
                )

        # Create Group Matches
        for gm in GROUP_MATCHES:
            group = group_map.get(gm['group'])
            dt = timezone.make_aware(datetime.datetime.strptime(gm['date'], '%Y-%m-%d %H:%M'))
            Match.objects.create(
                tournament=tournament,
                group=group,
                match_number=gm['num'],
                home_team=gm['home'],
                away_team=gm['away'],
                date_time=dt
            )

        # Create Knockout Stages
        stage_map = {}
        for st in KNOCKOUT_STAGES:
            stage_obj = KnockoutStage.objects.create(
                tournament=tournament,
                name=st['name'],
                order=st['order']
            )
            stage_map[st['name']] = stage_obj

        # Create Knockout Matches
        for km in KNOCKOUT_MATCHES:
            stage = stage_map.get(km['stage'])
            dt = timezone.make_aware(datetime.datetime.strptime(km['date'], '%Y-%m-%d %H:%M'))
            Match.objects.create(
                tournament=tournament,
                stage=stage,
                match_number=km['num'],
                home_team=km['home'],
                away_team=km['away'],
                date_time=dt
            )

        # Create Sidebets
        for sb in SIDEBETS:
            Sidebet.objects.create(
                tournament=tournament,
                question=sb['question'],
                points=sb['points'],
                question_type=sb['type']
            )

        self.stdout.write(self.style.SUCCESS(
            f'Successfully seeded "2026 Women\'s European Volleyball Championship" '
            f'with 24 teams in 4 pools, 60 group matches, and 16 knockout matches (76 total matches)!'
        ))
