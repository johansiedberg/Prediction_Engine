import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from tournament.models import (
    Tournament, PointSystem, Group, Team, KnockoutStage, Match
)

WORLD_CUP_2026_STRUCTURE = {
    'Grupp A': {'order': 1, 'teams': ['Mexiko', 'Danmark', 'Sydafrika', 'Sydkorea']},
    'Grupp B': {'order': 2, 'teams': ['Kanada', 'Schweiz', 'Qatar', 'Colombia']},
    'Grupp C': {'order': 3, 'teams': ['USA', 'Paraguay', 'Australien', 'Turkiet']},
    'Grupp D': {'order': 4, 'teams': ['Brasilien', 'Kroatien', 'Nigeria', 'Japan']},
    'Grupp E': {'order': 5, 'teams': ['Argentina', 'Österrike', 'Marocko', 'Ukraina']},
    'Grupp F': {'order': 6, 'teams': ['Frankrike', 'Polen', 'Chile', 'Saudiarabien']},
    'Grupp G': {'order': 7, 'teams': ['England', 'Sverige', 'Senegal', 'Peru']},
    'Grupp H': {'order': 8, 'teams': ['Spanien', 'Uruguay', 'Skottland', 'Algeriet']},
    'Grupp I': {'order': 9, 'teams': ['Tyskland', 'Ecuador', 'Elfenbenskusten', 'Iran']},
    'Grupp J': {'order': 10, 'teams': ['Nederländerna', 'Portugal', 'Kamerun', 'Egypten']},
    'Grupp K': {'order': 11, 'teams': ['Belgien', 'Italien', 'Serbien', 'Tunisien']},
    'Grupp L': {'order': 12, 'teams': ['Tjeckien', 'Ghana', 'Norge', 'Wales']},
}

KNOCKOUT_STAGES = [
    {'name': 'Sextondelsfinaler (Round of 32)', 'order': 1},
    {'name': 'Åttondelsfinaler (Round of 16)', 'order': 2},
    {'name': 'Kvartfinaler', 'order': 3},
    {'name': 'Semifinaler', 'order': 4},
    {'name': 'Bronsmatch', 'order': 5},
    {'name': 'Final', 'order': 6},
]

class Command(BaseCommand):
    help = 'Seeds FIFA World Cup 2026 tournament with 48 National Teams across 12 Groups (A-L), Group fixtures, and Knockout Stage structure.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Initializing FIFA World Cup 2026 setup...'))

        admin_user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if not admin_user:
            self.stdout.write(self.style.ERROR('No admin user found.'))
            return

        tournament, created = Tournament.objects.get_or_create(
            name='FIFA World Cup 2026',
            defaults={
                'admin': admin_user,
                'is_active': False
            }
        )

        PointSystem.objects.get_or_create(
            tournament=tournament,
            defaults={
                'match_correct_goals_per_team': 3,
                'match_correct_total_goals': 1,
                'match_correct_1x2': 3,
                'group_correct_placement': 2,
                'knockout_final': 8
            }
        )

        match_count = 0
        base_date = datetime.datetime(2026, 6, 11, 18, 0)

        for g_name, g_info in WORLD_CUP_2026_STRUCTURE.items():
            group, _ = Group.objects.get_or_create(
                tournament=tournament,
                name=g_name,
                defaults={'order': g_info['order']}
            )

            team_objs = []
            for t_name in g_info['teams']:
                team, _ = Team.objects.get_or_create(
                    tournament=tournament,
                    name=t_name,
                    defaults={'group': group}
                )
                team_objs.append(team)

            # Generate group matches (Round robin 6 matches per 4-team group)
            fixtures = [
                (team_objs[0], team_objs[1]), (team_objs[2], team_objs[3]),
                (team_objs[0], team_objs[2]), (team_objs[1], team_objs[3]),
                (team_objs[0], team_objs[3]), (team_objs[1], team_objs[2]),
            ]

            for idx, (h, a) in enumerate(fixtures):
                match_count += 1
                m_date = base_date + datetime.timedelta(days=(match_count % 14), hours=(idx * 3))
                Match.objects.get_or_create(
                    tournament=tournament,
                    group=group,
                    match_number=match_count,
                    defaults={
                        'home_team': h.name,
                        'away_team': a.name,
                        'date_time': m_date
                    }
                )

        # Create Knockout Stages
        for st in KNOCKOUT_STAGES:
            KnockoutStage.objects.get_or_create(
                tournament=tournament,
                name=st['name'],
                defaults={'order': st['order']}
            )

        self.stdout.write(self.style.SUCCESS(f'Successfully created "FIFA World Cup 2026" with 48 National Teams, 12 Groups, and {match_count} matches!'))
