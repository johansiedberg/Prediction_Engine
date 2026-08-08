import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from tournament.models import (
    Tournament, PointSystem, Group, Team, KnockoutStage, Match, Sidebet, TournamentSubmission
)

GROUPS_DATA = {
    'Group A': {
        'order': 1,
        'teams': ['A1', 'A2', 'A3', 'A4'] # Pure placeholders (Seeding pending draw)
    },
    'Group B': {
        'order': 2,
        'teams': ['B1', 'B2', 'B3', 'B4'] # Pure placeholders (Seeding pending draw)
    },
    'Group C': {
        'order': 3,
        'teams': ['C1', 'C2', 'C3', 'C4'] # Pure placeholders (Seeding pending draw)
    },
    'Group D': {
        'order': 4,
        'teams': ['D1', 'D2', 'D3', 'D4'] # Pure placeholders (Seeding pending draw)
    },
    'Group E': {
        'order': 5,
        'teams': ['E1', 'E2', 'E3', 'E4'] # Pure placeholders (Seeding pending draw)
    },
    'Group F': {
        'order': 6,
        'teams': ['F1', 'F2', 'F3', 'F4'] # Pure placeholders (Seeding pending draw)
    },
    'Group G': {
        'order': 7,
        'teams': ['G1', 'G2', 'G3', 'G4', 'G5'] # Pure placeholders (Seeding pending draw)
    },
    'Group H': {
        'order': 8,
        'teams': ['H1', 'H2', 'H3', 'H4', 'H5'] # Pure placeholders (Seeding pending draw)
    },
    'Group I': {
        'order': 9,
        'teams': ['I1', 'I2', 'I3', 'I4', 'I5'] # Pure placeholders (Seeding pending draw)
    },
    'Group J': {
        'order': 10,
        'teams': ['J1', 'J2', 'J3', 'J4', 'J5'] # Pure placeholders (Seeding pending draw)
    },
    'Group K': {
        'order': 11,
        'teams': ['K1', 'K2', 'K3', 'K4', 'K5'] # Pure placeholders (Seeding pending draw)
    },
    'Group L': {
        'order': 12,
        'teams': ['L1', 'L2', 'L3', 'L4', 'L5'] # Pure placeholders (Seeding pending draw)
    },
}


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
        'question': 'Hur många av de 4 värdnationerna (England, Irland, Skottland, Wales) kvalificerar sig direkt?',
        'points': 5,
        'question_type': 'TEXT',
    },
    {
        'question': 'Vilket lag blir den högst rankade grupptvåan (efter borträkning av 5:e lag)?',
        'points': 5,
        'question_type': 'TEAM',
    },
    {
        'question': 'Vilket lag kniper sista platsen till Euro 2028 via playoff-väg A?',
        'points': 5,
        'question_type': 'TEAM',
    },
]


class Command(BaseCommand):
    help = 'Seeds the UEFA EURO 2028 Qualifying Tournament with 54 teams across 12 groups, host nations, point system, and play-offs.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Initializing UEFA EURO 2028 Qualifying Tournament setup...'))

        admin_user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if not admin_user:
            self.stdout.write(self.style.ERROR('No admin user found in database. Create a superuser first.'))
            return



        # Create or update Euro 2028 Qualifying Tournament
        tournament, created = Tournament.objects.update_or_create(
            name='UEFA Euro 2028 Qualifying',
            defaults={
                'admin': admin_user,
                'is_active': True,
            }
        )

        status_str = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f'{status_str} Tournament: "{tournament.name}" (ID: {tournament.id})'))

        # Configure Point System
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
                'knockout_round_of_16': 3,
                'knockout_quarterfinal': 4,
                'knockout_semifinal': 5,
                'knockout_final': 8,
            }
        )
        self.stdout.write(self.style.SUCCESS('Point System configured.'))

        # Add all existing non-staff users to tournament
        all_players = User.objects.filter(is_staff=False, is_superuser=False)
        if all_players.exists():
            tournament.players.add(*all_players)
            for player in all_players:
                TournamentSubmission.objects.get_or_create(tournament=tournament, player=player)
            self.stdout.write(self.style.SUCCESS(f'Enrolled {all_players.count()} players into tournament.'))

        # Purge existing groups, teams, matches, knockout stages, and sidebets
        tournament.tournament_groups.all().delete()
        tournament.knockout_stages.all().delete()
        tournament.teams.all().delete()
        tournament.matches.all().delete()
        tournament.sidebets.all().delete()
        self.stdout.write(self.style.NOTICE('Purged all old groups, teams, matches, knockout stages, and sidebets for Euro 2028 Qualifying.'))


        # Seed Groups & Teams (Pure Placeholders A1..L5)
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

            # Generate Round-Robin Matches for this group
            for i in range(len(group_teams)):
                for j in range(i + 1, len(group_teams)):
                    t1, t2 = group_teams[i], group_teams[j]
                    
                    # Home match t1 vs t2
                    Match.objects.get_or_create(
                        tournament=tournament,
                        group=group_obj,
                        home_team=t1.name,
                        away_team=t2.name,
                        defaults={'match_number': match_counter}
                    )
                    match_counter += 1

                    # Away match t2 vs t1
                    Match.objects.get_or_create(
                        tournament=tournament,
                        group=group_obj,
                        home_team=t2.name,
                        away_team=t1.name,
                        defaults={'match_number': match_counter}
                    )
                    match_counter += 1

        self.stdout.write(self.style.SUCCESS(f'Seeded 12 Groups (A to L), {total_teams_count} Teams, and {match_counter - 1} Group Matches.'))

        # Seed Play-off Stages and Knockout Matches
        stage_map = {}
        for stage_info in PLAYOFF_STAGES:
            stage_obj, _ = KnockoutStage.objects.update_or_create(
                tournament=tournament,
                name=stage_info['name'],
                defaults={'order': stage_info['order']}
            )
            stage_map[stage_info['name']] = stage_obj
        self.stdout.write(self.style.SUCCESS('Seeded Play-off Stages.'))

        # Seed Knockout Matches using "Winner Match..." Placeholders (Path A, Path B, Path C)
        playoff_matches = [
            # Path A
            {'stage': 'Play-off Semifinals (March 2028)', 'match_number': 193, 'home': 'Path A Semi 1 (Pot 1)', 'away': 'Path A Semi 1 (Pot 4)'},
            {'stage': 'Play-off Semifinals (March 2028)', 'match_number': 194, 'home': 'Path A Semi 2 (Pot 2)', 'away': 'Path A Semi 2 (Pot 3)'},
            {'stage': 'Play-off Finals (March 2028)', 'match_number': 195, 'home': 'Winner Match 193', 'away': 'Winner Match 194'},
            # Path B
            {'stage': 'Play-off Semifinals (March 2028)', 'match_number': 196, 'home': 'Path B Semi 1 (Pot 1)', 'away': 'Path B Semi 1 (Pot 4)'},
            {'stage': 'Play-off Semifinals (March 2028)', 'match_number': 197, 'home': 'Path B Semi 2 (Pot 2)', 'away': 'Path B Semi 2 (Pot 3)'},
            {'stage': 'Play-off Finals (March 2028)', 'match_number': 198, 'home': 'Winner Match 196', 'away': 'Winner Match 197'},
            # Path C
            {'stage': 'Play-off Semifinals (March 2028)', 'match_number': 199, 'home': 'Path C Semi 1 (Pot 1)', 'away': 'Path C Semi 1 (Pot 4)'},
            {'stage': 'Play-off Semifinals (March 2028)', 'match_number': 200, 'home': 'Path C Semi 2 (Pot 2)', 'away': 'Path C Semi 2 (Pot 3)'},
            {'stage': 'Play-off Finals (March 2028)', 'match_number': 201, 'home': 'Winner Match 199', 'away': 'Winner Match 200'},
        ]


        for pm in playoff_matches:
            st = stage_map.get(pm['stage'])
            Match.objects.update_or_create(
                tournament=tournament,
                match_number=pm['match_number'],
                defaults={
                    'stage': st,
                    'home_team': pm['home'],
                    'away_team': pm['away'],
                }
            )
        self.stdout.write(self.style.SUCCESS('Seeded Knockout Play-off Matches with "Winner Match..." placeholders.'))

        # Seed Sidebets (Bonus Questions)
        for sb_info in SIDEBETS_DATA:
            Sidebet.objects.get_or_create(
                tournament=tournament,
                question=sb_info['question'],
                defaults={
                    'points': sb_info['points'],
                    'question_type': sb_info['question_type']
                }
            )
        self.stdout.write(self.style.SUCCESS('Seeded Bonus Questions (Sidebets).'))

        self.stdout.write(self.style.SUCCESS('Successfully completed UEFA EURO 2028 Qualifying Tournament setup!'))

