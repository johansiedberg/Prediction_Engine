import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from tournament.models import (
    Tournament, PointSystem, Group, Team, KnockoutStage, Match, Sidebet
)

RUGBY_CONFERENCES = {
    'Northern Hemisphere (Six Nations)': {
        'order': 1,
        'teams': ['England', 'Frankrike', 'Irland', 'Italien', 'Skottland', 'Wales']
    },
    'Southern Hemisphere (SANZAAR + Invited)': {
        'order': 2,
        'teams': ['Argentina', 'Australien', 'Nya Zeeland', 'Sydafrika', 'Fiji', 'Japan']
    },
}

FINALS_WEEKEND_STAGES = [
    {'name': 'Finals Weekend (Twickenham, London)', 'order': 1},
]

SIDEBETS = [
    {'question': 'Vilket lag vinner den historiska första upplagan av Nations Championship Rugby 2026?', 'points': 10, 'type': 'TEAM'},
    {'question': 'Vilken konferens samlar flest matchpoäng totalt (Norra eller Södra halvklotet)?', 'points': 5, 'type': 'TEXT'},
]

class Command(BaseCommand):
    help = 'Seeds Nations Championship Rugby 2026 (12 teams, 2 Conferences, 36 Cross-Conference Matches + 6 Finals Weekend Matches).'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Seeding Nations Championship Rugby 2026...'))
        admin_user = User.objects.filter(is_superuser=True).first() or User.objects.first()

        tournament, _ = Tournament.objects.update_or_create(
            name='Nations Championship Rugby 2026',
            defaults={'admin': admin_user, 'is_active': False}
        )

        PointSystem.objects.update_or_create(
            tournament=tournament,
            defaults={
                'match_correct_goals_per_team': 4, # Rugby Points per match
                'match_correct_total_goals': 1,
                'match_correct_1x2': 4, # Win = 4 pts
                'group_correct_placement': 2,
                'group_correct_points': 1,
                'group_correct_goals_scored': 1, # Tries scored
                'group_correct_goals_conceded': 1,
                'group_correct_goal_diff': 1,
                'group_team_qualified': 0,
                'knockout_round_of_16': 0,
                'knockout_quarterfinal': 0,
                'knockout_semifinal': 0,
                'knockout_final': 10, # Grand Final Winner
            }
        )

        tournament.tournament_groups.all().delete()
        tournament.knockout_stages.all().delete()
        tournament.teams.all().delete()
        tournament.matches.all().delete()
        tournament.sidebets.all().delete()

        # Create 2 Conferences
        north_grp, _ = Group.objects.get_or_create(tournament=tournament, name='Northern Hemisphere', defaults={'order': 1})
        south_grp, _ = Group.objects.get_or_create(tournament=tournament, name='Southern Hemisphere', defaults={'order': 2})

        north_teams = []
        for t_name in RUGBY_CONFERENCES['Northern Hemisphere (Six Nations)']['teams']:
            team, _ = Team.objects.get_or_create(tournament=tournament, name=t_name, defaults={'group': north_grp})
            north_teams.append(team)

        south_teams = []
        for t_name in RUGBY_CONFERENCES['Southern Hemisphere (SANZAAR + Invited)']['teams']:
            team, _ = Team.objects.get_or_create(tournament=tournament, name=t_name, defaults={'group': south_grp})
            south_teams.append(team)

        # 36 Cross-Conference Matches (July Window: 18 matches, Nov Window: 18 matches)
        match_count = 0
        base_date = datetime.datetime(2026, 7, 4, 15, 0)

        for n_team in north_teams:
            for s_team in south_teams:
                match_count += 1
                m_date = base_date + datetime.timedelta(days=(match_count * 3))
                Match.objects.create(
                    tournament=tournament,
                    group=north_grp,
                    match_number=match_count,
                    home_team=n_team.name,
                    away_team=s_team.name,
                    date_time=m_date
                )

        # Finals Weekend (6 Placement Matches at Twickenham)
        fw_stage, _ = KnockoutStage.objects.get_or_create(
            tournament=tournament, name='Finals Weekend (Twickenham, London)', defaults={'order': 1}
        )

        finals_matches = [
            {'num': 37, 'home': '1st Northern Conference', 'away': '1st Southern Conference', 'title': 'Championship Grand Final (1st Place)'},
            {'num': 38, 'home': '2nd Northern Conference', 'away': '2nd Southern Conference', 'title': 'Bronze Final (3rd Place)'},
            {'num': 39, 'home': '3rd Northern Conference', 'away': '3rd Southern Conference', 'title': '5th Place Play-off'},
            {'num': 40, 'home': '4th Northern Conference', 'away': '4th Southern Conference', 'title': '7th Place Play-off'},
            {'num': 41, 'home': '5th Northern Conference', 'away': '5th Southern Conference', 'title': '9th Place Play-off'},
            {'num': 42, 'home': '6th Northern Conference', 'away': '6th Southern Conference', 'title': '11th Place Play-off'},
        ]

        for fm in finals_matches:
            Match.objects.create(
                tournament=tournament,
                stage=fw_stage,
                match_number=fm['num'],
                home_team=fm['home'],
                away_team=fm['away']
            )

        for sb in SIDEBETS:
            Sidebet.objects.create(tournament=tournament, question=sb['question'], points=sb['points'], question_type=sb['type'])

        self.stdout.write(self.style.SUCCESS(f'Successfully seeded "Nations Championship Rugby 2026" with 12 teams, 2 Conferences, 36 Cross-Conference Matches, and 6 Finals Weekend Matches!'))
