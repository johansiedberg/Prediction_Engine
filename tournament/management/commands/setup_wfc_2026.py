import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from tournament.models import (
    MasterEvent, Tournament, PointSystem, Group, Team, KnockoutStage, Match, Sidebet
)

WFC_GROUPS = {
    'Grupp A': {
        'order': 1,
        'teams': [
            {'name': 'Finland', 'code': 'fi'},
            {'name': 'Latvia', 'code': 'lv'},
            {'name': 'Switzerland', 'code': 'ch'},
            {'name': 'Norway', 'code': 'no'},
        ]
    },
    'Grupp B': {
        'order': 2,
        'teams': [
            {'name': 'Sweden', 'code': 'se'},
            {'name': 'Czech Republic', 'code': 'cz'},
            {'name': 'Slovakia', 'code': 'sk'},
            {'name': 'Germany', 'code': 'de'},
        ]
    },
    'Grupp C': {
        'order': 3,
        'teams': [
            {'name': 'Estonia', 'code': 'ee'},
            {'name': 'Slovenia', 'code': 'si'},
            {'name': 'Singapore', 'code': 'sg'},
            {'name': 'Thailand', 'code': 'th'},
        ]
    },
    'Grupp D': {
        'order': 4,
        'teams': [
            {'name': 'Denmark', 'code': 'dk'},
            {'name': 'Philippines', 'code': 'ph'},
            {'name': 'Canada', 'code': 'ca'},
            {'name': 'Japan', 'code': 'jp'},
        ]
    },
}

KNOCKOUT_STAGES = [
    {'name': 'Playoff Round (Åttondels-playoff)', 'order': 1},
    {'name': 'Kvartsfinaler', 'order': 2},
    {'name': 'Semifinaler', 'order': 3},
    {'name': 'Bronsmatch', 'order': 4},
    {'name': 'Final', 'order': 5},
]

SIDEBETS = [
    {
        'question': 'Vilket land vinner Innebandy-VM 2026?',
        'points': 10,
        'type': 'TEAM',
    },
    {
        'question': 'Vilket land tar silver (förlorar finalen)?',
        'points': 6,
        'type': 'TEAM',
    },
    {
        'question': 'Vem vinner turneringens poängliga (mål + assist)?',
        'points': 8,
        'type': 'TEXT',
    },
]

class Command(BaseCommand):
    help = 'Seeds Men\'s World Floorball Championship 2026 (Innebandy-VM Herrar 2026) in Engine Admin.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Seeding Men\'s World Floorball Championship 2026...'))
        admin_user = User.objects.filter(is_superuser=True).first() or User.objects.first()

        # 1. Master Event
        master_event, _ = MasterEvent.objects.update_or_create(
            code='iff-wfc-2026',
            defaults={
                'name': "Men's World Floorball Championship 2026",
                'is_active': True,
            }
        )

        # 2. Tournament
        tournament, _ = Tournament.objects.update_or_create(
            name='Innebandy-VM Herrar 2026',
            defaults={
                'admin': admin_user,
                'is_active': True,
                'is_paused': False,
                'has_best_thirds_table': False,
                'has_runners_up_table': False,
                'has_host_ranking_table': False,
            }
        )

        # 3. Point System
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
                'knockout_qualified_third': 2,
                'knockout_round_of_16': 3,
                'knockout_quarterfinal': 4,
                'knockout_semifinal': 5,
                'knockout_bronze_match': 5,
                'knockout_final': 8,
            }
        )

        # Reset existing tournament children to ensure clean state
        tournament.tournament_groups.all().delete()
        tournament.knockout_stages.all().delete()
        tournament.teams.all().delete()
        tournament.matches.all().delete()
        tournament.sidebets.all().delete()

        match_number = 0
        base_date = datetime.datetime(2026, 12, 5, 10, 0)

        # 4. Create Groups, Teams & Group Stage Matches
        for g_name, g_info in WFC_GROUPS.items():
            group = Group.objects.create(
                tournament=tournament,
                name=g_name,
                order=g_info['order']
            )

            team_objects = []
            for t_data in g_info['teams']:
                t_obj = Team.objects.create(
                    tournament=tournament,
                    group=group,
                    name=t_data['name'],
                    code=t_data['code']
                )
                team_objects.append(t_obj)

            # Round robin fixtures: 6 matches per group
            fixtures = [
                (team_objects[0], team_objects[1], datetime.time(13, 0)),
                (team_objects[2], team_objects[3], datetime.time(16, 0)),
                (team_objects[0], team_objects[2], datetime.time(14, 30)),
                (team_objects[1], team_objects[3], datetime.time(17, 30)),
                (team_objects[3], team_objects[0], datetime.time(15, 0)),
                (team_objects[1], team_objects[2], datetime.time(18, 0)),
            ]

            day_offsets = [0, 0, 1, 1, 2, 2]

            for idx, (h_team, a_team, kick_time) in enumerate(fixtures):
                match_number += 1
                match_day = base_date + datetime.timedelta(days=day_offsets[idx])
                naive_dt = datetime.datetime.combine(match_day.date(), kick_time)
                aware_dt = timezone.make_aware(naive_dt, timezone.get_current_timezone())

                Match.objects.create(
                    tournament=tournament,
                    group=group,
                    match_number=match_number,
                    home_team=h_team.name,
                    away_team=a_team.name,
                    date_time=aware_dt
                )

        # 5. Create Knockout Stages & Bracket Matches
        stages_dict = {}
        for s_info in KNOCKOUT_STAGES:
            stage_obj = KnockoutStage.objects.create(
                tournament=tournament,
                name=s_info['name'],
                order=s_info['order']
            )
            stages_dict[s_info['order']] = stage_obj

        # Playoff Round (Matches 25-28) - 2026-12-09
        playoff_date = datetime.datetime(2026, 12, 9, 13, 0)
        playoff_matches = [
            (25, '3rd Group A', '2nd Group D', datetime.time(13, 0)),
            (26, '4th Group A', '1st Group D', datetime.time(16, 0)),
            (27, '3rd Group B', '2nd Group C', datetime.time(16, 0)),
            (28, '4th Group B', '1st Group C', datetime.time(19, 0)),
        ]
        for m_num, h_ph, a_ph, k_time in playoff_matches:
            naive_dt = datetime.datetime.combine(playoff_date.date(), k_time)
            aware_dt = timezone.make_aware(naive_dt, timezone.get_current_timezone())
            Match.objects.create(
                tournament=tournament,
                stage=stages_dict[1],
                match_number=m_num,
                home_team=h_ph,
                away_team=a_ph,
                date_time=aware_dt
            )

        # Quarterfinals (Matches 29-32) - 2026-12-10 & 2026-12-11
        qf_matches = [
            (29, '1st Group A', 'Winner Match 25', datetime.datetime(2026, 12, 10, 16, 0)),
            (30, '1st Group B', 'Winner Match 26', datetime.datetime(2026, 12, 10, 19, 0)),
            (31, '2nd Group A', 'Winner Match 27', datetime.datetime(2026, 12, 11, 16, 0)),
            (32, '2nd Group B', 'Winner Match 28', datetime.datetime(2026, 12, 11, 19, 0)),
        ]
        for m_num, h_ph, a_ph, naive_dt in qf_matches:
            aware_dt = timezone.make_aware(naive_dt, timezone.get_current_timezone())
            Match.objects.create(
                tournament=tournament,
                stage=stages_dict[2],
                match_number=m_num,
                home_team=h_ph,
                away_team=a_ph,
                date_time=aware_dt
            )

        # Semifinals (Matches 33-34) - 2026-12-12
        sf_matches = [
            (33, 'Winner Match 29', 'Winner Match 32', datetime.datetime(2026, 12, 12, 14, 0)),
            (34, 'Winner Match 30', 'Winner Match 31', datetime.datetime(2026, 12, 12, 17, 30)),
        ]
        for m_num, h_ph, a_ph, naive_dt in sf_matches:
            aware_dt = timezone.make_aware(naive_dt, timezone.get_current_timezone())
            Match.objects.create(
                tournament=tournament,
                stage=stages_dict[3],
                match_number=m_num,
                home_team=h_ph,
                away_team=a_ph,
                date_time=aware_dt
            )

        # Bronze Match (Match 35) - 2026-12-13 13:00
        bronze_dt = timezone.make_aware(datetime.datetime(2026, 12, 13, 13, 0), timezone.get_current_timezone())
        Match.objects.create(
            tournament=tournament,
            stage=stages_dict[4],
            match_number=35,
            home_team='Loser Match 33',
            away_team='Loser Match 34',
            date_time=bronze_dt
        )

        # Final (Match 36) - 2026-12-13 17:00
        final_dt = timezone.make_aware(datetime.datetime(2026, 12, 13, 17, 0), timezone.get_current_timezone())
        Match.objects.create(
            tournament=tournament,
            stage=stages_dict[5],
            match_number=36,
            home_team='Winner Match 33',
            away_team='Winner Match 34',
            date_time=final_dt
        )

        # 6. Sidebets
        for sb in SIDEBETS:
            Sidebet.objects.create(
                tournament=tournament,
                question=sb['question'],
                points=sb['points'],
                question_type=sb['type']
            )

        self.stdout.write(self.style.SUCCESS(
            f'Successfully created and seeded "{tournament.name}" (MasterEvent: {master_event.name}) '
            f'with 16 teams, 4 groups, 36 total matches (24 group + 12 playoff/knockout), and 3 bonus sidebets!'
        ))
