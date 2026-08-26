import datetime
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings, Client
from django.contrib.auth.models import User

from tournament.models import (
    Tournament, Match, MatchPrediction, TournamentSubmission,
    DailyGazette, RoundLeaderboardSnapshot, PointSystem, League, LeagueMember,
    KnockoutStage, Sidebet, ScannedTournament
)
from tournament.editorial_engine.special_edition_reporter import SpecialEditionReporter
from tournament.editorial_engine.detectors import check_and_trigger_special_editions


class SpecialEditionTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('johansiedberg', 'admin@test.com', 'password')
        self.user1 = User.objects.create_user('alice', 'alice@test.com', 'password', first_name='Alice', last_name='Smith')
        self.user2 = User.objects.create_user('bob', 'bob@test.com', 'password', first_name='Bob', last_name='Jones')

        self.tournament = Tournament.objects.create(name='Euro 2026 Test', admin=self.admin)
        self.tournament.players.add(self.user1, self.user2)

        self.point_system = PointSystem.objects.create(tournament=self.tournament)

        self.sub1, _ = TournamentSubmission.objects.get_or_create(tournament=self.tournament, player=self.user1)
        self.sub2, _ = TournamentSubmission.objects.get_or_create(tournament=self.tournament, player=self.user2)

        self.match1 = Match.objects.create(
            tournament=self.tournament,
            match_number=1,
            home_team='Sweden',
            away_team='Norway',
            home_goals=2,
            away_goals=1,
            is_finished=True
        )

        MatchPrediction.objects.create(
            match=self.match1,
            player=self.user1,
            home_goals=2,
            away_goals=1
        )
        MatchPrediction.objects.create(
            match=self.match1,
            player=self.user2,
            home_goals=1,
            away_goals=0
        )

    def test_draft_special_edition(self):
        gazette = SpecialEditionReporter.draft_special_edition(self.tournament, round_num=1)
        self.assertIsNotNone(gazette)
        self.assertTrue(gazette.is_special_edition)
        self.assertEqual(gazette.round_number, 1)
        self.assertIn("Alice", gazette.headline_top_contenders)
        self.assertIsNotNone(gazette.headline_standout_results)
        self.assertIsNotNone(gazette.headline_worst_performers)
        self.assertIsNotNone(gazette.analysis_outlook)

        snapshots = RoundLeaderboardSnapshot.objects.filter(tournament=self.tournament, round_number=1)
        self.assertEqual(snapshots.count(), 2)

    def test_trigger_special_edition_round_1(self):
        self.sub1.is_verified = True
        self.sub1.save()
        self.sub2.is_verified = True
        self.sub2.save()

        triggered = check_and_trigger_special_editions(self.tournament)
        self.assertEqual(len(triggered), 1)
        self.assertTrue(triggered[0].is_special_edition)
        self.assertEqual(triggered[0].round_number, 1)


class EngineHubTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('user1', 'u1@test.com', 'password', first_name='John', last_name='Doe')
        self.admin = User.objects.create_superuser('johansiedberg', 'admin@test.com', 'password')
        self.tournament = Tournament.objects.create(name='Test Tournament', admin=self.admin, is_active=True)
        self.league = League.objects.create(name='Test League', admin=self.admin, invite_code='ENGINE8')

    def test_hub_view_access(self):
        self.client.login(username='user1', password='password')
        response = self.client.get('/hub/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Prediction Engine Hub")
        self.assertContains(response, "Välkommen, John!")

    def test_join_league_with_invite_code(self):
        self.client.login(username='user1', password='password')
        response = self.client.post('/league/join/', {'invite_code': 'ENGINE8'}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(LeagueMember.objects.filter(league=self.league, player=self.user).exists())


class EngineAdminTournamentUpdateTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('johansiedberg', 'admin@engine.test', 'adminpass123')
        self.staff = User.objects.create_user('staff_user', 'staff@engine.test', 'staffpass123', is_staff=True)
        self.normal_user = User.objects.create_user('player1', 'p1@engine.test', 'playerpass123')
        self.tournament = Tournament.objects.create(name='Original Tournament Name', admin=self.admin)

    def test_update_tournament_name_by_admin(self):
        self.client.login(username='johansiedberg', password='adminpass123')
        response = self.client.post(
            f'/engine-admin/update-tournament/{self.tournament.id}/',
            {'name': 'UEFA Euro 2028 UK & Ireland'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost:2029'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.tournament.refresh_from_db()
        self.assertEqual(self.tournament.name, 'UEFA Euro 2028 UK & Ireland')

    def test_update_tournament_upload_images(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.login(username='johansiedberg', password='adminpass123')

        # 1x1 transparent PNG bytes
        dummy_png = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06'
            b'\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01'
            b'\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        icon_file = SimpleUploadedFile("euro28_logo.png", dummy_png, content_type="image/png")
        backdrop_file = SimpleUploadedFile("euro28_backdrop.png", dummy_png, content_type="image/png")

        response = self.client.post(
            f'/engine-admin/update-tournament/{self.tournament.id}/',
            {
                'name': 'Updated UEFA Euro 2028',
                'icon': icon_file,
                'backdrop': backdrop_file,
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost:2029'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertIsNotNone(data['tournament']['icon_url'])
        self.assertIsNotNone(data['tournament']['backdrop_url'])

        self.tournament.refresh_from_db()
        self.assertTrue(bool(self.tournament.icon))
        self.assertTrue(bool(self.tournament.backdrop))

        # Test clear images
        clear_response = self.client.post(
            f'/engine-admin/update-tournament/{self.tournament.id}/',
            {
                'name': 'Updated UEFA Euro 2028',
                'clear_icon': '1',
                'clear_backdrop': '1',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost:2029'
        )
        self.assertEqual(clear_response.status_code, 200)
        self.tournament.refresh_from_db()
        self.assertFalse(bool(self.tournament.icon))
        self.assertFalse(bool(self.tournament.backdrop))

    def test_unauthorized_user_forbidden(self):
        self.client.login(username='player1', password='playerpass123')
        response = self.client.post(
            f'/engine-admin/update-tournament/{self.tournament.id}/',
            {'name': 'Hacked Name'},
            HTTP_HOST='localhost:2029'
        )
        self.tournament.refresh_from_db()
        self.assertEqual(self.tournament.name, 'Original Tournament Name')
        self.assertNotEqual(self.tournament.name, 'Hacked Name')


class EmailUserIdentificationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='anna@exempel.se',
            email='anna@exempel.se',
            password='annapassword123',
            first_name='Anna',
            last_name='Andersson'
        )

    def test_authenticate_with_email_exact(self):
        from django.contrib.auth import authenticate
        user = authenticate(username='anna@exempel.se', password='annapassword123')
        self.assertIsNotNone(user)
        self.assertEqual(user.email, 'anna@exempel.se')

    def test_authenticate_with_email_case_insensitive(self):
        from django.contrib.auth import authenticate
        user = authenticate(username='ANNA@EXEMPEL.SE', password='annapassword123')
        self.assertIsNotNone(user)
        self.assertEqual(user.email, 'anna@exempel.se')

    def test_login_form_with_email(self):
        from tournament.forms import CustomLoginForm
        form = CustomLoginForm(data={'username': 'anna@exempel.se', 'password': 'annapassword123'})
        self.assertTrue(form.is_valid())

    def test_registration_creates_user_with_email_as_id(self):
        response = self.client.post('/register/', {
            'first_name': 'Bengt',
            'last_name': 'Bengtsson',
            'email': 'bengt@exempel.se',
            'password1': 'bengtpass123',
            'password2': 'bengtpass123',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        bengt = User.objects.filter(email='bengt@exempel.se').first()
        self.assertIsNotNone(bengt)
        self.assertEqual(bengt.username, 'bengt@exempel.se')
        self.assertEqual(bengt.first_name, 'Bengt')
        self.assertEqual(bengt.last_name, 'Bengtsson')

    def test_pool_admin_can_update_own_email(self):
        self.client.login(username='anna@exempel.se', password='annapassword123')
        response = self.client.post('/pool-admin/update-email/', {
            'email': 'anna.new@exempel.se',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'anna.new@exempel.se')
        self.assertEqual(self.user.username, 'anna.new@exempel.se')


class WANHTTPSAccessTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('wan_user', 'wan@test.com', 'password123', first_name='WAN', last_name='Tester')
        self.admin = User.objects.create_superuser('johansiedberg', 'admin@wan.test', 'adminpass123')

    def test_player_app_wan_https_access(self):
        self.client.login(username='wan_user', password='password123')
        response = self.client.get(
            '/hub/',
            HTTP_HOST='217.31.171.173:2028',
            HTTP_X_FORWARDED_PROTO='https',
            secure=True
        )
        self.assertEqual(response.status_code, 200)

    def test_engine_admin_wan_https_access(self):
        self.client.login(username='johansiedberg', password='adminpass123')
        response = self.client.get(
            '/engine-admin/',
            HTTP_HOST='217.31.171.173:2029',
            HTTP_X_FORWARDED_PROTO='https',
            secure=True
        )
class ScoutServiceTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('johansiedberg', 'scout@admin.test', 'scoutpass123')

    @patch('tournament.services.allsportdb_client.requests.get')
    def test_scrape_web_for_tournaments(self, mock_get):
        # Mock Sports response and Calendar response
        mock_sports_resp = MagicMock()
        mock_sports_resp.status_code = 200
        mock_sports_resp.json.return_value = [{'id': 1, 'name': 'Innebandy (Floorball)'}]

        mock_cal_resp = MagicMock()
        mock_cal_resp.status_code = 200
        mock_cal_resp.json.return_value = [{
            'id': 901,
            'title': 'Innebandy-VM Herrar 2026 Championship',
            'sportId': 1,
            'sportName': 'Floorball',
            'startDate': '2026-12-04',
            'endDate': '2026-12-13',
            'officialWebsite': 'https://www.floorball.sport'
        }]

        mock_get.side_effect = [mock_sports_resp, mock_cal_resp]

        from tournament.services.scout_service import scrape_web_for_tournaments
        created_cnt, updated_cnt, prospects = scrape_web_for_tournaments()
        self.assertGreater(len(prospects), 0)
        self.assertEqual(created_cnt + updated_cnt, len(prospects))

    @patch('tournament.services.allsportdb_client.requests.get')
    def test_scrape_web_with_query_filter(self, mock_get):
        mock_sports_resp = MagicMock()
        mock_sports_resp.status_code = 200
        mock_sports_resp.json.return_value = [{'id': 1, 'name': 'Floorball'}]

        mock_cal_resp = MagicMock()
        mock_cal_resp.status_code = 200
        mock_cal_resp.json.return_value = [{
            'id': 902,
            'title': 'Innebandy World Championship 2026',
            'sportId': 1,
            'sportName': 'Floorball',
            'startDate': '2026-12-04'
        }]

        mock_get.side_effect = [mock_sports_resp, mock_cal_resp]

        from tournament.services.scout_service import scrape_web_for_tournaments
        _, _, prospects = scrape_web_for_tournaments(custom_query='Innebandy')
        self.assertGreater(len(prospects), 0)
        self.assertTrue(any('Innebandy' in p.name for p in prospects))


    def test_convert_scanned_to_live_tournament_preserves_record(self):
        from tournament.services.scout_service import parse_and_save_scouted_json, convert_scanned_to_live_tournament
        from tournament.models import ScannedTournament

        sample = {
            "scouting_audit": {"completeness_grade": "GRADE_A"},
            "master_event": {"name": "Test Cup 2026", "code": "test-cup-2026", "sport": "Football"},
            "tournament_config": {"name": "Test Cup 2026", "total_teams": 4, "knockout_stages": ["Final"]},
            "groups": [{"name": "Grupp A", "teams": [{"name": "Lag 1"}, {"name": "Lag 2"}]}],
        }
        scanned, _, _ = parse_and_save_scouted_json(sample)
        self.assertEqual(scanned.status, 'NEW')

        tour, err = convert_scanned_to_live_tournament(scanned.id, self.admin)
        self.assertIsNone(err)
        self.assertIsNotNone(tour)

        scanned.refresh_from_db()
        self.assertEqual(scanned.status, 'CONVERTED')
        self.assertEqual(scanned.converted_tournament, tour)

    def test_delete_tournament_view(self):
        from tournament.models import Tournament
        tour = Tournament.objects.create(name='Tournament to Delete', admin=self.admin)
        self.client.force_login(self.admin)

        response = self.client.post(
            f'/engine-admin/delete-tournament/{tour.id}/',
            HTTP_HOST='localhost:2029'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')
        self.assertFalse(Tournament.objects.filter(id=tour.id).exists())

    def test_ignored_status_preservation_on_rescan(self):
        from tournament.services.scout_service import parse_and_save_scouted_json
        from tournament.models import ScannedTournament

        sample = {
            "scouting_audit": {"completeness_grade": "GRADE_B", "official_rules": "Regler V1"},
            "master_event": {"name": "Ignored Cup 2026", "code": "ignored-cup-2026", "sport": "Football"},
            "tournament_config": {"name": "Ignored Cup 2026", "total_teams": 4},
        }
        scanned, _, _ = parse_and_save_scouted_json(sample)
        scanned.status = 'ARCHIVED'
        scanned.save()

        # Rescan / update same tournament
        sample_v2 = {
            "scouting_audit": {"completeness_grade": "GRADE_A", "official_rules": "Regler V2"},
            "master_event": {"name": "Ignored Cup 2026", "code": "ignored-cup-2026", "sport": "Football"},
            "tournament_config": {"name": "Ignored Cup 2026", "total_teams": 4},
        }
        scanned_updated, created, _ = parse_and_save_scouted_json(sample_v2)
        self.assertFalse(created)
        self.assertEqual(scanned_updated.status, 'ARCHIVED')
        self.assertEqual(scanned_updated.official_rules, "Regler V2")

    def test_official_rules_copied_on_conversion(self):
        from tournament.services.scout_service import parse_and_save_scouted_json, convert_scanned_to_live_tournament

        sample = {
            "scouting_audit": {"completeness_grade": "GRADE_A", "official_rules": "Gruppspel: 3p vinst. Slutspel: Forlangning 2x5min."},
            "master_event": {"name": "Official Rules Cup 2026", "code": "rules-cup-2026", "sport": "Floorball", "official_source_url": "https://official.rules.sport"},
            "tournament_config": {"name": "Official Rules Cup 2026", "total_teams": 4, "knockout_stages": ["Final"]},
        }
        scanned, _, _ = parse_and_save_scouted_json(sample)
        scanned.official_rules = "Gruppspel: 3p vinst. Slutspel: Forlangning 2x5min."
        scanned.official_source_url = "https://official.rules.sport"
        scanned.save()

        tour, err = convert_scanned_to_live_tournament(scanned.id, self.admin)
        self.assertIsNone(err)
        self.assertEqual(tour.official_rules, "Gruppspel: 3p vinst. Slutspel: Forlangning 2x5min.")
        self.assertEqual(tour.official_regulations_url, "https://official.rules.sport")

    def test_scout_update_official_rules_view(self):
        from tournament.models import ScannedTournament
        scanned = ScannedTournament.objects.create(
            name="Rules Endpoint Cup",
            master_event_code="rules-endpoint-cup",
            status="NEW"
        )
        self.client.force_login(self.admin)
        response = self.client.post(
            f'/engine-admin/scout/official-rules/{scanned.id}/',
            {
                'official_rules': 'Uppdaterade officiella regler',
                'official_url': 'https://regulations.test.com'
            },
            HTTP_HOST='localhost:2029'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')

        scanned.refresh_from_db()
        self.assertEqual(scanned.official_rules, 'Uppdaterade officiella regler')
        self.assertEqual(scanned.official_source_url, 'https://regulations.test.com')

    @patch('tournament.services.allsportdb_client.requests.get')

    def test_scout_scrape_web_view(self, mock_get):
        mock_sports_resp = MagicMock()
        mock_sports_resp.status_code = 200
        mock_sports_resp.json.return_value = [{'id': 1, 'name': 'Floorball'}]

        mock_cal_resp = MagicMock()
        mock_cal_resp.status_code = 200
        mock_cal_resp.json.return_value = [{
            'id': 999,
            'title': 'World Floorball Championship 2026',
            'sportId': 1,
            'sportName': 'Floorball',
            'startDate': '2026-12-04'
        }]

        mock_get.side_effect = [mock_sports_resp, mock_cal_resp]

        self.client.force_login(self.admin)
        response = self.client.post(
            '/engine-admin/scout/scrape-now/',
            HTTP_HOST='localhost:2029'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')
        self.assertIn('Webbscanning slutförd', response.json()['message'])

    @patch('tournament.services.scout_service.requests.get')
    def test_wikipedia_year_events_crawling(self, mock_requests_get):
        from tournament.services.scout_service import fetch_and_ingest_wikipedia_year_events

        def side_effect(url, **kwargs):
            m = MagicMock()
            m.status_code = 200
            if 'mobile-sections' in url or 'api.php' in url or 'format=json' in str(kwargs.get('params', {})):
                m.json.return_value = {
                    'parse': {
                        'text': {'*': '<table class="infobox"><tr><th>Dates</th><td>15 June – 15 July 2027</td></tr></table>'}
                    }
                }
            else:
                m.content = b'<html><body><a href="./2027_World_Junior_Ice_Hockey_Championships" title="2027 World Junior Ice Hockey Championships">2027 World Junior Ice Hockey Championships</a></body></html>'
            return m

        mock_requests_get.side_effect = side_effect

        c, u, prospects = fetch_and_ingest_wikipedia_year_events(years=[2027])
        self.assertGreaterEqual(c, 1)
        self.assertEqual(len(prospects), 1)
        self.assertEqual(prospects[0].name, '2027 World Junior Ice Hockey Championships')

    def test_wikipedia_duplicate_tournament_merging(self):
        from tournament.models import ScannedTournament
        from tournament.services.scout_service import merge_duplicate_scanned_tournaments_by_wikipedia

        # Create prospect 1 (shallow)
        p1 = ScannedTournament.objects.create(
            name="World Floorball Championship 2026",
            master_event_code="wfc-2026-allsportdb",
            sport="Floorball",
            status="NEW",
            completeness_grade="GRADE_C",
            payload={
                "scouting_audit": {
                    "scouting_stage": "SHALLOW",
                    "wikipedia_url": "https://en.wikipedia.org/wiki/2026_Men's_World_Floorball_Championships"
                }
            }
        )

        # Create prospect 2 (deep scanned from Wikipedia import)
        p2 = ScannedTournament.objects.create(
            name="2026 Men's World Floorball Championships",
            master_event_code="2026-mens-world-floorball-championships",
            sport="Floorball",
            status="NEW",
            completeness_grade="GRADE_A",
            payload={
                "scouting_audit": {
                    "scouting_stage": "DEEP",
                    "wikipedia_url": "https://en.wikipedia.org/wiki/2026_Men's_World_Floorball_Championships"
                },
                "groups": [{"name": "Group A", "teams": ["Sweden", "Finland"]}]
            }
        )

        merged_cnt, retained = merge_duplicate_scanned_tournaments_by_wikipedia()
        self.assertEqual(merged_cnt, 1)
        self.assertEqual(len(retained), 1)

        # Primary retained should be p2 (since DEEP & GRADE_A)
        primary = retained[0]
        self.assertEqual(primary.id, p2.id)
        self.assertEqual(ScannedTournament.objects.filter(id=p1.id).count(), 0)
        self.assertEqual(len(primary.payload.get('groups', [])), 1)





class AllSportDBPipelineTestCase(TestCase):
    def test_h2h_sport_filtering(self):
        from tournament.services.tournament_filter import is_h2h_team_sport

        self.assertTrue(is_h2h_team_sport('Football'))
        self.assertTrue(is_h2h_team_sport('Ice Hockey'))
        self.assertTrue(is_h2h_team_sport('Floorball'))
        self.assertTrue(is_h2h_team_sport('Basketball'))
        self.assertTrue(is_h2h_team_sport('Handball'))
        self.assertTrue(is_h2h_team_sport("Women's Volleyball"))

        self.assertFalse(is_h2h_team_sport('Athletics'))
        self.assertFalse(is_h2h_team_sport('Swimming'))
        self.assertFalse(is_h2h_team_sport('Formula 1'))
        self.assertFalse(is_h2h_team_sport('Chess'))
        self.assertFalse(is_h2h_team_sport('Darts'))

    def test_championship_format_filtering(self):
        from tournament.services.tournament_filter import is_championship_or_cup_format

        # Whitelisted Cup / Championship titles
        valid1, _ = is_championship_or_cup_format('World Cup 2026')
        self.assertTrue(valid1)

        valid2, _ = is_championship_or_cup_format('EHF European Handball Championship')
        self.assertTrue(valid2)

        # Exception pattern: Champions League / Europa League
        valid3, _ = is_championship_or_cup_format('UEFA Champions League 2026/27')
        self.assertTrue(valid3)

        # Blacklisted regular round-robin league
        invalid1, _ = is_championship_or_cup_format('Premier League Regular Season')
        self.assertFalse(invalid1)

        invalid2, _ = is_championship_or_cup_format('NHL Division Games')
        self.assertFalse(invalid2)

    def test_event_grading_logic(self):
        from tournament.services.tournament_filter import evaluate_event_grade

        # Grade A: H2H sport + official site + complete teams & fixtures
        ev_grade_a = {
            'official_website': 'https://www.fifa.com/worldcup',
            'teams': [{'name': 'Sweden'}, {'name': 'Brazil'}],
            'fixtures': [{'match': 1}],
            'start_date': '2027-06-11'
        }

        grade_a, _ = evaluate_event_grade(ev_grade_a, is_h2h_sport_compatible=True)
        self.assertEqual(grade_a, 'GRADE_A')

        # Grade B: H2H sport + official site, but pending full fixtures/teams
        ev_grade_b = {
            'official_website': 'https://www.euro2028.com',
            'teams': [],
            'start_date': '2028-06-01'
        }
        grade_b, _ = evaluate_event_grade(ev_grade_b, is_h2h_sport_compatible=True)
        self.assertEqual(grade_b, 'GRADE_B')

        # Grade C: Non-H2H sport
        ev_grade_c = {
            'official_website': 'https://www.iaaf.org',
            'teams': [{'name': 'Runner A'}],
            'start_date': '2026-07-01'
        }
        grade_c, _ = evaluate_event_grade(ev_grade_c, is_h2h_sport_compatible=False)
        self.assertEqual(grade_c, 'GRADE_C')

    def test_models_creation(self):
        from tournament.models import Sport, TournamentEvent

        sport = Sport.objects.create(external_id=1, name='Ice Hockey', is_h2h_team_sport=True)
        self.assertEqual(str(sport), 'Ice Hockey (ID: 1) [H2H Compatible]')

        event = TournamentEvent.objects.create(
            external_id=101,
            sport=sport,
            title='IIHF World Championship 2026',
            start_date='2026-05-08',
            end_date='2026-05-24',
            country='Switzerland',
            city='Zurich',
            official_website='https://www.iihf.com',
            completeness_grade='GRADE_A'
        )
        self.assertEqual(event.sport, sport)
        self.assertEqual(event.completeness_grade, 'GRADE_A')

    def test_fallback_regulations_agent_hook(self):
        from tournament.services.allsportdb_client import AllSportDBClient

        client = AllSportDBClient()
        url = client.fetch_official_regulations_url('Floorball World Championship 2026')
        self.assertIn('google.com/search', url)
        self.assertIn('Floorball+World+Championship+2026', url)
        self.assertIn('official+tournament+regulations', url)


class WikipediaScoutTestCase(TestCase):
    def test_get_article_title_from_url(self):
        from tournament.services.wikipedia_scout import WikipediaScout
        ws = WikipediaScout()
        url = "https://en.wikipedia.org/wiki/2026_FIBA_Women's_Basketball_World_Cup"
        title = ws.get_article_title_from_url(url)
        self.assertEqual(title, "2026_FIBA_Women's_Basketball_World_Cup")

    @patch('tournament.services.wikipedia_scout.requests.get')
    def test_audit_tournament_page(self, mock_get):
        from tournament.services.wikipedia_scout import WikipediaScout
        ws = WikipediaScout()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'parse': {
                'sections': [
                    {'line': 'Qualified teams'},
                    {'line': 'Group A'},
                    {'line': 'Group B'},
                    {'line': 'Knockout stage'}
                ],
                'text': {'*': '<table class="infobox"><tr><th>Teams</th><td>16</td></tr></table><h3>Group A</h3><table class="wikitable"><tr><th>Team</th></tr><tr><td>Sweden</td></tr><tr><td>Finland</td></tr></table><h3>Group B</h3><table class="wikitable"><tr><th>Team</th></tr><tr><td>Czech Republic</td></tr><tr><td>Canada</td></tr></table>'}
            }
        }

        mock_get.return_value = mock_resp

        audit = ws.audit_tournament_page('2026_FIBA_Women_World_Cup')
        self.assertIsNotNone(audit)
        self.assertEqual(audit['teams_count'], 4)
        self.assertTrue(audit['draw_completed'])
        self.assertEqual(len(audit['groups']), 2)



class OfficialRegulationsVerifierTestCase(TestCase):
    @patch('tournament.services.official_regulations_verifier.requests.get')
    def test_verify_official_regulations(self, mock_get):
        from tournament.services.official_regulations_verifier import OfficialRegulationsVerifier
        verifier = OfficialRegulationsVerifier()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "Official Rules and Regulations. Group stage standings and knockout matches format."
        mock_get.return_value = mock_resp

        res = verifier.verify_official_regulations('https://www.example.org', 'Test World Cup')
        self.assertTrue(res['verified'])
        self.assertEqual(res['status'], 'VERIFIED')

    @patch('tournament.services.wikipedia_scout.requests.get')
    def test_scout_import_wikipedia_view(self, mock_get):
        admin = User.objects.create_superuser('johansiedberg', 'wiki@admin.test', 'wikipass123')
        self.client.force_login(admin)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'parse': {
                'text': {'*': '<table class="infobox"><tr><th>Teams</th><td>12</td></tr><tr><th>Host</th><td>Spain</td></tr></table>'}
            }
        }
        mock_get.return_value = mock_resp

        response = self.client.post(
            '/engine-admin/scout/import-wikipedia/',
            {'wikipedia_url': "https://en.wikipedia.org/wiki/2026_FIBA_Women's_Basketball_World_Cup"},
            HTTP_HOST='localhost:2029',
            HTTP_X_FORWARDED_PROTO='https',
            secure=True
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')

    @patch('tournament.services.wikipedia_scout.requests.get')
    def test_scout_search_specific_view(self, mock_get):
        admin = User.objects.create_superuser('johansiedberg', 'search@admin.test', 'searchpass123')
        self.client.force_login(admin)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'query': {
                'search': [{'title': "2026 FIBA Women's Basketball World Cup"}]
            },
            'parse': {
                'text': {'*': '<table class="infobox"><tr><th>Teams</th><td>16</td></tr><tr><th>Host</th><td>Germany</td></tr></table>'}
            }
        }
        mock_get.return_value = mock_resp

        response = self.client.post(
            '/engine-admin/scout/search-specific/',
            {'tournament_query': "FIBA Women's Basketball World Cup 2026"},
            HTTP_HOST='localhost:2029',
            HTTP_X_FORWARDED_PROTO='https',
            secure=True
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')

    @patch('tournament.services.wikipedia_scout.requests.get')
    def test_scout_deep_scan_one_view(self, mock_get):
        import datetime
        from tournament.models import ScannedTournament
        admin = User.objects.create_superuser('johansiedberg', 'deep@admin.test', 'deeppass123')
        self.client.force_login(admin)

        prospect = ScannedTournament.objects.create(
            name="2027 Test Tournament",
            master_event_code="2027-test-tournament",
            start_date=datetime.date(2027, 6, 1),
            end_date=datetime.date(2027, 6, 15),
            completeness_grade="GRADE_C",
            payload={
                "scouting_audit": {
                    "scouting_stage": "SHALLOW",
                    "wikipedia_url": "https://en.wikipedia.org/wiki/2027_Test_Tournament",
                    "wikipedia_title": "2027 Test Tournament"
                }
            }
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'parse': {
                'sections': [
                    {'line': 'Group A'},
                    {'line': 'Group B'},
                    {'line': 'Fixtures'}
                ],
                'text': {'*': '<table class="infobox"><tr><th>Teams</th><td>8</td></tr><tr><th>Dates</th><td>1 June – 15 June 2027</td></tr></table>'}
            }
        }
        mock_get.return_value = mock_resp

        response = self.client.post(
            f'/engine-admin/scout/deep-scan/{prospect.id}/',
            HTTP_HOST='localhost:2029',
            HTTP_X_FORWARDED_PROTO='https',
            secure=True
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('Djupscanning slutförd', data['message'])

        prospect.refresh_from_db()
        self.assertEqual(prospect.payload['scouting_audit']['scouting_stage'], 'DEEP')

    @patch('tournament.services.official_regulations_verifier.requests.get')
    def test_scout_update_official_url_view(self, mock_get):
        from tournament.models import ScannedTournament
        admin = User.objects.create_superuser('johansiedberg', 'url@admin.test', 'urlpass123')
        self.client.force_login(admin)

        prospect = ScannedTournament.objects.create(
            name="2026 UEFA Test",
            master_event_code="2026-uefa-test",
            completeness_grade="GRADE_B",
            payload={}
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Type': 'text/html'}
        mock_resp.text = "Official competition regulations for group and knockout matches"
        mock_get.return_value = mock_resp

        response = self.client.post(
            f'/engine-admin/scout/official-url/{prospect.id}/',
            {'official_url': 'https://documents.uefa.com/r/Regulations-of-the-UEFA-European-Football-Championship-2026-28-Online'},
            HTTP_HOST='localhost:2029',
            HTTP_X_FORWARDED_PROTO='https',
            secure=True
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('sparats', data['message'])

        prospect.refresh_from_db()
        self.assertEqual(prospect.official_source_url, 'https://documents.uefa.com/r/Regulations-of-the-UEFA-European-Football-Championship-2026-28-Online')
        self.assertTrue(prospect.payload['scouting_audit']['official_site_audit']['verified'])


class LLMWikipediaScoutTestCase(TestCase):
    """Tests for LLMWikipediaScout — uses mocks so no real API key is required."""

    @patch('requests.get')
    def test_fetch_wikipedia_plaintext_success(self, mock_get):
        """fetch_wikipedia_plaintext returns cleaned text from Wikipedia REST API."""
        from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'lead': {'sections': [{'text': '<p>2026 FIFA World Cup article.</p>'}]},
            'remaining': {'sections': [{'line': 'Group A', 'text': '<p>Germany, USA, Mexico, Japan</p>'}]},
        }
        mock_get.return_value = mock_resp

        scout = LLMWikipediaScout()
        result = scout._fetch_plaintext('2026 FIFA World Cup')
        self.assertIsNotNone(result)
        self.assertIn('2026 FIFA World Cup', result)
        self.assertIn('Group A', result)

    @patch('requests.get')
    def test_fetch_wikipedia_plaintext_404(self, mock_get):
        """fetch_wikipedia_plaintext returns None on non-200 response."""
        from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        scout = LLMWikipediaScout()
        result = scout._fetch_plaintext('NonExistentTournamentXYZ')
        self.assertIsNone(result)

    @patch('requests.get')
    @patch('tournament.services.wikipedia_scout.WikipediaScout.audit_tournament_page')
    @override_settings(GEMINI_API_KEY='')
    def test_audit_with_llm_falls_back_when_no_api_key(self, mock_audit, mock_get):
        """audit_with_llm falls back to HTML heuristic when GEMINI_API_KEY is not set."""
        from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'lead': {'sections': [{'text': '<p>Test article.</p>'}]},
            'remaining': {'sections': []},
        }
        mock_get.return_value = mock_resp

        mock_audit.return_value = {
            'page_title': '2026 FIFA World Cup',
            'wiki_url': 'https://en.wikipedia.org/wiki/2026_FIFA_World_Cup',
            'groups': [], 'fixtures': [], 'fixtures_count': 0, 'groups_count': 0,
            'teams_count': 48, 'scheduled_matchdays': 0,
            'fixtures_have_placeholders': False, 'draw_completed': True,
            'draw_date': '', 'advancement_rules': '', 'fixtures_completed': False,
            'knockout_stages': ['Quarterfinals', 'Semifinals', 'Final'],
            'host_country': 'USA', 'sections': [],
        }

        scout = LLMWikipediaScout()
        result = scout.audit_with_llm('2026 FIFA World Cup')
        # Fallback must have been called
        mock_audit.assert_called_once_with('2026 FIFA World Cup')
        self.assertIsNotNone(result)
        self.assertEqual(result['teams_count'], 48)

    def test_normalise_produces_correct_schema(self):
        """_normalise converts a raw Gemini dict to the canonical audit schema."""
        from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
        raw = {
            'teams_count': 24,
            'host_country': 'Poland',
            'groups': [
                {'name': 'Group A', 'teams': [{'name': 'USA'}, {'name': 'Germany'}]},
            ],
            'fixtures': [
                {
                    'home_team': 'USA', 'away_team': 'Germany',
                    'date': '12 June 2026', 'time': '18:00',
                    'venue': 'Warsaw', 'stage_or_group': 'Group A',
                    'is_placeholder': False,
                }
            ],
            'scheduled_matchdays': 0,
            'draw_completed': True,
            'draw_date': '6 March 2026',
            'advancement_rules': 'Top 2 from each group advance.',
            'knockout_stages': ['Round of 16', 'Quarterfinals', 'Semifinals', 'Final'],
            'fixtures_count': 1,
            'groups_count': 1,
            'fixtures_completed': True,
        }
        result = LLMWikipediaScout._normalise(raw, '2026 FIFA U-20 Womens World Cup', 'https://en.wikipedia.org/wiki/test')
        self.assertEqual(result['teams_count'], 24)
        self.assertEqual(result['host_country'], 'Poland')
        self.assertEqual(len(result['groups']), 1)
        self.assertEqual(len(result['fixtures']), 1)
        self.assertEqual(result['fixtures'][0]['strategy'], 'LLM_Gemini_Flash')
        self.assertTrue(result['draw_completed'])
        self.assertEqual(result['draw_date'], '6 March 2026')
        self.assertIn('Round of 16', result['knockout_stages'])

    def test_llm_date_extraction_normalisation(self):
        """_parse_date_string and _normalise extract YYYY-MM-DD dates from varied inputs."""
        from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
        self.assertEqual(LLMWikipediaScout._parse_date_string('11 June 2027'), '2027-06-11')
        self.assertEqual(LLMWikipediaScout._parse_date_string('June 11, 2027'), '2027-06-11')
        self.assertEqual(LLMWikipediaScout._parse_date_string('2027-06-11'), '2027-06-11')

        raw = {
            'tournament_start_date': '11 June 2027',
            'tournament_end_date': '19 July 2027',
            'date_reasoning': 'Main final tournament matches scheduled 11 June - 19 July 2027.',
            'teams_count': 16,
        }
        norm = LLMWikipediaScout._normalise(raw, '2027 Cup', 'https://en.wikipedia.org/wiki/2027_Cup')
        self.assertEqual(norm['start_date'], '2027-06-11')
        self.assertEqual(norm['end_date'], '2027-07-19')

    @patch('tournament.services.wikidata_scout.WikidataScout.fetch_wikidata_entity')
    @patch('tournament.services.llm_wikipedia_scout.LLMWikipediaScout.audit_with_llm')
    def test_deep_scan_retains_incomplete_date_as_grade_c(self, mock_audit, mock_wikidata):
        """_run_deep_scan_on_prospect sets Grade C and preserves prospect when start_date is unconfirmed."""
        from tournament.models import ScannedTournament
        from tournament.views.engine_admin import _run_deep_scan_on_prospect
        from tournament.services.wikipedia_scout import WikipediaScout
        from tournament.services.official_regulations_verifier import OfficialRegulationsVerifier

        mock_wikidata.return_value = {}
        prospect = ScannedTournament.objects.create(
            name="No Date Cup 2027",
            master_event_code="no-date-cup-2027",
            start_date=None,
            payload={'scouting_audit': {'wikipedia_title': 'No Date Cup 2027'}}
        )

        mock_audit.return_value = {
            'page_title': 'No Date Cup 2027',
            'tournament_start_date': '',
            'tournament_end_date': '',
            'start_date': '',
            'end_date': '',
            'teams_count': 16,
            'draw_completed': False,
            'fixtures_completed': False,
        }

        res = _run_deep_scan_on_prospect(prospect, WikipediaScout(), OfficialRegulationsVerifier())
        self.assertTrue(res['ok'])
        self.assertEqual(res['grade'], 'GRADE_C')
        self.assertTrue(ScannedTournament.objects.filter(id=prospect.id).exists())

    @patch('tournament.services.llm_wikipedia_scout.LLMWikipediaScout.audit_with_llm')
    def test_deep_scan_rejects_empty_prospect_missing_dates_fixtures_teams(self, mock_audit):
        """_run_deep_scan_on_prospect rejects and deletes prospect missing dates, fixtures, and teams."""
        from tournament.models import ScannedTournament
        from tournament.views.engine_admin import _run_deep_scan_on_prospect
        from tournament.services.wikipedia_scout import WikipediaScout
        from tournament.services.official_regulations_verifier import OfficialRegulationsVerifier

        prospect = ScannedTournament.objects.create(
            name="Empty Cup 2027",
            master_event_code="empty-cup-2027",
            start_date=None,
            payload={}
        )

        mock_audit.return_value = {
            'page_title': 'Empty Cup 2027',
            'tournament_start_date': '',
            'start_date': '',
            'teams_count': 0,
            'groups_count': 0,
            'draw_completed': False,
            'fixtures_completed': False,
        }

        res = _run_deep_scan_on_prospect(prospect, WikipediaScout(), OfficialRegulationsVerifier())
        self.assertFalse(res['ok'])
        self.assertIn('saknar datum, spelschema och lag', res['error'])
        self.assertFalse(ScannedTournament.objects.filter(id=prospect.id).exists())

    @patch('tournament.services.llm_wikipedia_scout.LLMWikipediaScout.audit_with_llm')
    def test_deep_scan_grade_b_for_missing_end_date(self, mock_audit):
        """_run_deep_scan_on_prospect assigns Grade B (not Grade A) if end_date is missing/TBD."""
        import datetime
        from tournament.models import ScannedTournament
        from tournament.views.engine_admin import _run_deep_scan_on_prospect
        from tournament.services.wikipedia_scout import WikipediaScout
        from tournament.services.official_regulations_verifier import OfficialRegulationsVerifier

        future_date = str(datetime.date.today() + datetime.timedelta(days=45))

        prospect = ScannedTournament.objects.create(
            name="2026 FIVB Volleyball Boys' U17 World Championship",
            master_event_code="2026-fivb-volleyball-u17",
            start_date=datetime.date.today() + datetime.timedelta(days=45),
            end_date=None,
            payload={}
        )

        mock_audit.return_value = {
            'page_title': "2026 FIVB Volleyball Boys' U17 World Championship",
            'tournament_start_date': future_date,
            'tournament_end_date': '',
            'start_date': future_date,
            'end_date': '',
            'draw_completed': False,
            'draw_date': '6 December 2026',
            'groups_count': 0,
            'fixtures_completed': False,
            'fixtures_count': 0,
        }

        res = _run_deep_scan_on_prospect(prospect, WikipediaScout(), OfficialRegulationsVerifier())
        self.assertTrue(res['ok'])
        # Must be Grade B because draw is pending (Väntar lottning)
        self.assertEqual(res['grade'], 'GRADE_B')
        self.assertIn('Väntar lottning', prospect.grade_reason)
        self.assertTrue(ScannedTournament.objects.filter(id=prospect.id).exists())

    @patch('tournament.services.llm_wikipedia_scout.LLMWikipediaScout.audit_with_llm')
    def test_deep_scan_rejects_past_or_ongoing_date(self, mock_audit):
        """_run_deep_scan_on_prospect deletes prospect if start_date is today or in the past."""
        import datetime
        from tournament.models import ScannedTournament
        from tournament.views.engine_admin import _run_deep_scan_on_prospect
        from tournament.services.wikipedia_scout import WikipediaScout
        from tournament.services.official_regulations_verifier import OfficialRegulationsVerifier

        past_date = str(datetime.date.today() - datetime.timedelta(days=10))

        prospect = ScannedTournament.objects.create(
            name="Past Cup 2025",
            master_event_code="past-cup-2025",
            start_date=datetime.date.today() - datetime.timedelta(days=10),
            payload={}
        )

        mock_audit.return_value = {
            'page_title': 'Past Cup 2025',
            'tournament_start_date': past_date,
            'start_date': past_date,
            'draw_completed': False,
            'fixtures_completed': False,
        }

        res = _run_deep_scan_on_prospect(prospect, WikipediaScout(), OfficialRegulationsVerifier())
        self.assertFalse(res['ok'])
        self.assertIn('är pågående eller startar inom', res['error'])
        self.assertFalse(ScannedTournament.objects.filter(id=prospect.id).exists())

    @patch('tournament.services.llm_wikipedia_scout.LLMWikipediaScout.audit_with_llm')
    def test_deep_scan_rejects_tournaments_starting_within_30_days(self, mock_audit):
        """_run_deep_scan_on_prospect rejects/deletes prospects starting within 30 days."""
        import datetime
        from tournament.models import ScannedTournament
        from tournament.views.engine_admin import _run_deep_scan_on_prospect
        from tournament.services.wikipedia_scout import WikipediaScout
        from tournament.services.official_regulations_verifier import OfficialRegulationsVerifier

        imminent_date = str(datetime.date.today() + datetime.timedelta(days=15))

        prospect = ScannedTournament.objects.create(
            name="Imminent Cup 2026",
            master_event_code="imminent-cup-2026",
            start_date=datetime.date.today() + datetime.timedelta(days=15),
            payload={}
        )

        mock_audit.return_value = {
            'page_title': 'Imminent Cup 2026',
            'tournament_start_date': imminent_date,
            'start_date': imminent_date,
            'draw_completed': False,
            'fixtures_completed': False,
        }

        res = _run_deep_scan_on_prospect(prospect, WikipediaScout(), OfficialRegulationsVerifier())
        self.assertFalse(res['ok'])
        self.assertIn('är pågående eller startar inom', res['error'])
        self.assertFalse(ScannedTournament.objects.filter(id=prospect.id).exists())

    @patch('tournament.services.llm_wikipedia_scout.LLMWikipediaScout.audit_with_llm')
    def test_deep_scan_rejects_ongoing_or_played_match_results(self, mock_audit):
        """_run_deep_scan_on_prospect deletes prospects that have played match results (e.g. 21 - 20)."""
        import datetime
        from tournament.models import ScannedTournament
        from tournament.views.engine_admin import _run_deep_scan_on_prospect
        from tournament.services.wikipedia_scout import WikipediaScout
        from tournament.services.official_regulations_verifier import OfficialRegulationsVerifier

        future_date = str(datetime.date.today() + datetime.timedelta(days=40))

        prospect = ScannedTournament.objects.create(
            name="2026 European Football Alliance season",
            master_event_code="2026-efa-season",
            start_date=datetime.date.today() + datetime.timedelta(days=40),
            payload={}
        )

        mock_audit.return_value = {
            'page_title': '2026 European Football Alliance season',
            'tournament_start_date': future_date,
            'start_date': future_date,
            'is_ongoing_or_finished': True,
            'draw_completed': True,
            'fixtures_completed': True,
        }

        res = _run_deep_scan_on_prospect(prospect, WikipediaScout(), OfficialRegulationsVerifier())
        self.assertFalse(res['ok'])
        self.assertIn('Spelade matcher/resultat hittades', res['error'])
        self.assertFalse(ScannedTournament.objects.filter(id=prospect.id).exists())

    def test_parse_date_range_benchmark_examples(self):
        """Tests parsing of date ranges from real-world Wikipedia benchmarks."""
        from tournament.services.llm_wikipedia_scout import LLMWikipediaScout

        # Example 1: 15 May – 29 August 2026
        s1, e1 = LLMWikipediaScout._parse_date_range("15 May – 29 August 2026", "")
        self.assertEqual(s1, "2026-05-15")
        self.assertEqual(e1, "2026-08-29")

        # Example 2: 19–29 August 2026
        s2, e2 = LLMWikipediaScout._parse_date_range("19–29 August 2026", "")
        self.assertEqual(s2, "2026-08-19")
        self.assertEqual(e2, "2026-08-29")

        # Example 4: 3–20 December with year inferred from page title
        s4, e4 = LLMWikipediaScout._parse_date_range("3–20 December", "", "2026 European Women's Handball Championship")
        self.assertEqual(s4, "2026-12-03")
        self.assertEqual(e4, "2026-12-20")

        # Example 5: Wikipedia Infobox Template (2027 Netball World Cup)
        s5, e5 = LLMWikipediaScout._parse_date_range("{{start and end dates|2027|08|25|2027|09|05|df=y}}", "")
        self.assertEqual(s5, "2027-08-25")
        self.assertEqual(e5, "2027-09-05")

        # Example 6: "25 August – 5 September 2027"
        s6, e6 = LLMWikipediaScout._parse_date_range("25 August – 5 September 2027", "")
        self.assertEqual(s6, "2027-08-25")
        self.assertEqual(e6, "2027-09-05")

        # Example 7: Cross-year range (2027 World Junior Ice Hockey Championships)
        s7, e7 = LLMWikipediaScout._parse_date_range("December 26, 2026 – January 5, 2027", "")
        self.assertEqual(s7, "2026-12-26")
        self.assertEqual(e7, "2027-01-05")

    def test_clean_team_name_seed_and_host_markers(self):
        """Tests cleaning of seed prefixes (A1, B2) and host markers (H)."""
        from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
        self.assertEqual(LLMWikipediaScout._clean_team_name("A1 Hungary"), "Hungary")
        self.assertEqual(LLMWikipediaScout._clean_team_name("Romania (H)"), "Romania")
        self.assertEqual(LLMWikipediaScout._clean_team_name("B2 Poland (H)"), "Poland")

    @patch('tournament.services.llm_wikipedia_scout.LLMWikipediaScout.audit_with_llm')
    def test_deep_scan_disambiguation_split_tournaments(self, mock_audit):
        """Tests that deep scanning a disambiguation page creates sub-tournament prospects."""
        from tournament.models import ScannedTournament
        from tournament.views.engine_admin import _run_deep_scan_on_prospect
        from tournament.services.wikipedia_scout import WikipediaScout
        from tournament.services.official_regulations_verifier import OfficialRegulationsVerifier

        parent = ScannedTournament.objects.create(
            name="2026 FIBA 3x3 U23 World Cup",
            master_event_code="2026-fiba-3x3-u23-world-cup",
            payload={}
        )

        mock_audit.return_value = {
            'page_title': '2026 FIBA 3x3 U23 World Cup',
            'is_disambiguation': True,
            'sub_tournaments': [
                {'name': "2026 FIBA 3x3 U23 World Cup – Men's tournament"},
                {'name': "2026 FIBA 3x3 U23 World Cup – Women's tournament"}
            ]
        }

        res = _run_deep_scan_on_prospect(parent, WikipediaScout(), OfficialRegulationsVerifier())
        self.assertTrue(res['ok'])
        self.assertEqual(res['grade'], 'GRADE_C')
        self.assertIn('Uppdelad', parent.grade_reason)

        # Check sub tournaments created
        self.assertTrue(ScannedTournament.objects.filter(name="2026 FIBA 3x3 U23 World Cup – Men's tournament").exists())
        self.assertTrue(ScannedTournament.objects.filter(name="2026 FIBA 3x3 U23 World Cup – Women's tournament").exists())


class DeepscanBlueprintTests(TestCase):
    """
    Tests for Deepscan blueprint schemas, Gemini LLM structured outputs, and SkeletonBuilder.
    """

    def test_tournament_setup_pydantic_validation(self):
        from tournament.schemas.tournament_blueprint import (
            TournamentSetup, GroupStructure, KnockoutStructure, TiebreakerRule
        )

        setup = TournamentSetup(
            tournament_name="2026 FIFA World Cup",
            sport="Football",
            host_country="USA / Canada / Mexico",
            groups=[
                GroupStructure(name="Group A", teams_count=4, teams=["USA", "Mexico", "Canada", "Costa Rica"])
            ],
            knockout_stages=[
                KnockoutStructure(stage_name="Quarterfinals", match_count=4)
            ]
        )
        self.assertEqual(setup.tournament_name, "2026 FIFA World Cup")
        self.assertEqual(setup.sport, "Football")
        self.assertEqual(len(setup.groups), 1)
        self.assertEqual(setup.tiebreaker_hierarchy[0], TiebreakerRule.H2H_POINTS)

    def test_llm_scout_blueprint_building(self):
        from tournament.services.llm_wikipedia_scout import LLMWikipediaScout
        raw_llm = {
            "tournament_name": "2026 IFF World Floorball Championship",
            "sport": "Floorball",
            "host_country": "Sweden",
            "tiebreaker_hierarchy": ["H2H_POINTS", "OVERALL_GOAL_DIFFERENCE"]
        }
        norm = {
            "page_title": "2026 Men's World Floorball Championship",
            "host_country": "Sweden",
            "groups": [
                {"name": "Group A", "teams": [{"name": "Sweden"}, {"name": "Finland"}]}
            ],
            "knockout_stages": ["Semifinals", "Final"],
            "official_rules": "Standard IFF tiebreaker rules"
        }
        bp_dict = LLMWikipediaScout._build_tournament_blueprint(raw_llm, norm)
        self.assertIn("tournament_name", bp_dict)
        self.assertEqual(bp_dict["sport"], "Floorball")
        self.assertEqual(len(bp_dict["groups"]), 1)

    def test_skeleton_builder_group_and_knockout_placeholders(self):
        from tournament.services.skeleton_builder import SkeletonBuilder
        bp = {
            "tournament_name": "2026 Floorball Championship",
            "sport": "Floorball",
            "groups_count": 4,
            "groups": [
                {"name": "Group A", "teams_count": 4, "teams": ["Sweden", "Finland"]},
                {"name": "Group B", "teams_count": 4, "teams": ["Czech Republic", "Switzerland"]},
                {"name": "Group C", "teams_count": 4, "teams": ["Latvia", "Slovakia"]},
                {"name": "Group D", "teams_count": 4, "teams": ["Norway", "Germany"]},
            ]
        }
        builder = SkeletonBuilder(bp)
        skeleton = builder.build_skeleton()

        self.assertEqual(len(skeleton["groups"]), 4)
        # Check team placeholders filled up to count
        self.assertEqual(len(skeleton["groups"][0]["teams"]), 4)
        self.assertEqual(skeleton["groups"][0]["teams"][2], "A3")

        # Check knockout bracket tree placeholders
        tree = skeleton["knockout_tree"]
        self.assertTrue(len(tree) >= 3)  # QF, SF, Finals
        qf_stage = tree[0]
        self.assertEqual(qf_stage["stage_name"], "Quarterfinals")
        self.assertEqual(qf_stage["matches"][0]["home_source"], "Winner Group A")
        self.assertEqual(qf_stage["matches"][0]["away_source"], "Runner-up Group B")

    def test_skeleton_builder_12_groups_r32(self):
        from tournament.services.skeleton_builder import SkeletonBuilder
        bp = {
            "tournament_name": "2026 FIFA World Cup",
            "sport": "Football",
            "groups_count": 12,
        }
        builder = SkeletonBuilder(bp)
        skeleton = builder.build_skeleton()

        self.assertEqual(len(skeleton["groups"]), 12)
        tree = skeleton["knockout_tree"]
        self.assertEqual(tree[0]["stage_name"], "Round of 32")
        self.assertEqual(tree[0]["match_count"], 16)
        self.assertEqual(tree[0]["matches"][0]["home_source"], "Winner Group A")

    def test_convert_scanned_to_live_tournament_with_skeleton_fallback(self):
        from django.contrib.auth import get_user_model
        from tournament.models import ScannedTournament, Tournament
        from tournament.services.scout_service import convert_scanned_to_live_tournament

        User = get_user_model()
        admin = User.objects.create_user(username="admin_test_scout", email="admin@test.com", password="password")

        scanned = ScannedTournament.objects.create(
            name="2026 Skeleton Fallback Cup",
            sport="Floorball",
            payload={}
        )
        tourn, err = convert_scanned_to_live_tournament(scanned.id, admin)
        self.assertIsNotNone(tourn)
        self.assertIsNone(err)
        self.assertEqual(tourn.tournament_groups.count(), 4)
        self.assertTrue(tourn.matches.count() > 0)

    def test_is_real_team_name_and_has_real_teams(self):
        from tournament.services.scout_service import is_real_team_name, has_real_teams

        # Placeholders / fake names should return False
        self.assertFalse(is_real_team_name("A1"))
        self.assertFalse(is_real_team_name("Lag 1"))
        self.assertFalse(is_real_team_name("Total"))
        self.assertFalse(is_real_team_name("TBD"))
        self.assertFalse(is_real_team_name("Seed 1"))
        self.assertFalse(is_real_team_name("Group A"))

        # Real team names should return True
        self.assertTrue(is_real_team_name("Sweden"))
        self.assertTrue(is_real_team_name("Mexico"))
        self.assertTrue(is_real_team_name("Real Madrid"))

        # Groups with placeholders return False
        fake_groups = [
            {"name": "Group A", "teams": [{"name": "A1"}, {"name": "A2"}, {"name": "A3"}, {"name": "A4"}]},
            {"name": "Group B", "teams": [{"name": "B1"}, {"name": "B2"}, {"name": "B3"}, {"name": "B4"}]},
        ]
        self.assertFalse(has_real_teams(fake_groups))

        # Groups with real teams return True
        real_groups = [
            {"name": "Group A", "teams": [{"name": "Sweden"}, {"name": "Finland"}, {"name": "Czech Republic"}, {"name": "Switzerland"}]},
            {"name": "Group B", "teams": [{"name": "Germany"}, {"name": "Norway"}, {"name": "Slovakia"}, {"name": "Latvia"}]},
        ]
        self.assertTrue(has_real_teams(real_groups))

    def test_deep_scan_transitions_out_of_new_status(self):
        from unittest.mock import patch
        from tournament.models import ScannedTournament
        from tournament.views.engine_admin import _run_deep_scan_on_prospect
        from tournament.services.wikipedia_scout import WikipediaScout
        from tournament.services.official_regulations_verifier import OfficialRegulationsVerifier

        prospect = ScannedTournament.objects.create(
            name="Non Existent Cup 9999",
            status="NEW",
            payload={}
        )
        self.assertEqual(prospect.status, "NEW")

        wiki_scout = WikipediaScout()
        off_verifier = OfficialRegulationsVerifier()

        with patch.object(wiki_scout, 'get_article_title_from_url', return_value=''):
            with patch.object(wiki_scout, 'search_wikipedia_article', return_value=''):
                res = _run_deep_scan_on_prospect(prospect, wiki_scout, off_verifier)

        prospect.refresh_from_db()
        self.assertFalse(res['ok'])
        self.assertNotEqual(prospect.status, "NEW")
        self.assertEqual(prospect.status, "NOT_READY")
        self.assertEqual(prospect.completeness_grade, "GRADE_C")

    def test_unified_tournament_prospect_blueprint_schema(self):
        """Tests that TournamentProspectBlueprint correctly validates and converts to legacy format."""
        from tournament.schemas.tournament_prospect_schema import (
            TournamentProspectBlueprint, ProspectMetadata, ScoutingAudit, GroupProspect, TeamEntry
        )
        bp = TournamentProspectBlueprint(
            metadata=ProspectMetadata(
                name="Euro 2028 Test",
                master_event_code="euro-2028-test",
                sport="Football",
                organizer="UEFA",
                host_country="UK & Ireland",
                start_date="2028-06-09",
                end_date="2028-07-09",
            ),
            groups=[
                GroupProspect(name="Group A", teams=[TeamEntry(name="England"), TeamEntry(name="Scotland")])
            ]
        )
        self.assertEqual(bp.metadata.name, "Euro 2028 Test")
        self.assertEqual(len(bp.groups), 1)
        self.assertEqual(bp.groups[0].teams[0].name, "England")

        legacy = bp.to_legacy_dict()
        self.assertEqual(legacy['master_event']['name'], "Euro 2028 Test")
        self.assertEqual(legacy['master_event']['sport'], "Football")
        self.assertEqual(len(legacy['groups']), 1)

    def test_web_crawl_agent_ingestion(self):
        """Tests Phase 1 WebCrawlAgent discovers events and sets status to NEW."""
        import datetime
        from unittest.mock import patch
        from tournament.services.web_crawl_agent import WebCrawlAgent
        from tournament.models import ScannedTournament

        mock_prospect = ScannedTournament.objects.create(
            name='Test Floorball WFC 2027',
            sport='Floorball',
            status='NEW',
            completeness_grade='GRADE_C',
            start_date=datetime.date(2027, 12, 1),
            end_date=datetime.date(2027, 12, 10)
        )
        with patch('tournament.services.scout_service.sync_all_scout_prospects', return_value=(1, 0, [mock_prospect])):
            agent = WebCrawlAgent(min_days_ahead=30)
            created, updated, prospects = agent.discover_and_ingest()

        self.assertGreaterEqual(created + updated, 1)
        scanned = ScannedTournament.objects.filter(name='Test Floorball WFC 2027').first()
        self.assertIsNotNone(scanned)
        self.assertEqual(scanned.status, 'NEW')
        self.assertEqual(scanned.completeness_grade, 'GRADE_C')




    def test_modular_deep_scout_execution(self):
        """Tests Phase 2 ModularDeepScout populates blueprint JSON and calculates grade."""
        from unittest.mock import patch
        from tournament.models import ScannedTournament
        from tournament.services.modular_deep_scout import ModularDeepScout

        prospect = ScannedTournament.objects.create(
            name="World Cup 2030 Test",
            sport="Football",
            status="NEW",
            payload={}
        )

        mock_audit = {
            'page_title': 'World Cup 2030 Test',
            'tournament_start_date': '2030-06-01',
            'tournament_end_date': '2030-07-01',
            'is_ongoing_or_finished': False,
            'draw_completed': True,
            'fixtures_completed': True,
            'groups': [
                {'name': 'Group A', 'teams': [{'name': 'Spain'}, {'name': 'Portugal'}, {'name': 'Morocco'}, {'name': 'Uruguay'}]},
                {'name': 'Group B', 'teams': [{'name': 'France'}, {'name': 'Argentina'}, {'name': 'Japan'}, {'name': 'Brazil'}]},
            ],
            'fixtures': [
                {'match_number': 1, 'stage_or_group': 'Group A', 'date_time': '2030-06-01 15:00', 'home_team': 'Spain', 'away_team': 'Portugal'},
                {'match_number': 2, 'stage_or_group': 'Group A', 'date_time': '2030-06-01 18:00', 'home_team': 'Morocco', 'away_team': 'Uruguay'},
                {'match_number': 3, 'stage_or_group': 'Group B', 'date_time': '2030-06-02 15:00', 'home_team': 'France', 'away_team': 'Argentina'},
                {'match_number': 4, 'stage_or_group': 'Group B', 'date_time': '2030-06-02 18:00', 'home_team': 'Japan', 'away_team': 'Brazil'},
            ]
        }

        deep_scout = ModularDeepScout()
        with patch.object(deep_scout.wiki_scout, 'get_article_title_from_url', return_value='World Cup 2030 Test'), \
             patch.object(deep_scout.wiki_scout, 'search_wikipedia_article', return_value='World Cup 2030 Test'), \
             patch.object(deep_scout.llm_scout, 'audit_with_llm', return_value=mock_audit):
            res = deep_scout.deep_scan_prospect(prospect)

        prospect.refresh_from_db()
        self.assertTrue(res['ok'])
        self.assertEqual(prospect.completeness_grade, 'GRADE_A')
        self.assertEqual(prospect.status, 'READY')
        self.assertEqual(len(prospect.payload.get('groups', [])), 2)


class PointSystemFlowTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from tournament.models import Tournament, PointSystem, League, LeaguePointSystem, Match, MatchPrediction

        User = get_user_model()
        self.admin_user = User.objects.create_superuser(username="johansiedberg", email="admin@test.com", password="password")
        self.tournament = Tournament.objects.create(name="Test World Cup 2026", admin=self.admin_user)


        self.point_system = PointSystem.objects.create(
            tournament=self.tournament,
            match_correct_1x2=4,
            match_correct_goals_per_team=2,
            match_correct_total_goals=2,
            group_correct_placement=3,
            group_correct_points=2,
            group_correct_goals_scored=1,
            group_correct_goals_conceded=1,
            group_correct_goal_diff=1,
            qualifying_table_team_qualified=5,
            knockout_round_of_32=2,
            knockout_round_of_16=4,
            knockout_quarterfinal=6,
            knockout_semifinal=8,
            knockout_bronze_match=10,
            knockout_final=10,
        )
        self.league = League.objects.create(name="Test Super Pool", admin=self.admin_user)
        self.league.tournaments.add(self.tournament)

    def test_pool_admin_inherits_engine_admin_point_system(self):
        """Verifies that LeaguePointSystem inherits default points from Tournament PointSystem on creation."""
        from tournament.models import LeaguePointSystem

        pool_ps, created = LeaguePointSystem.objects.get_or_create(league=self.league)
        if created and hasattr(self.tournament, 'point_system'):
            t_ps = self.tournament.point_system
            pool_ps.match_correct_1x2 = t_ps.match_correct_1x2
            pool_ps.match_correct_goals_per_team = t_ps.match_correct_goals_per_team
            pool_ps.match_correct_total_goals = t_ps.match_correct_total_goals
            pool_ps.group_correct_placement = t_ps.group_correct_placement
            pool_ps.group_correct_points = t_ps.group_correct_points
            pool_ps.save()

        self.assertEqual(pool_ps.match_correct_1x2, 4)
        self.assertEqual(pool_ps.match_correct_goals_per_team, 2)
        self.assertEqual(pool_ps.match_correct_total_goals, 2)
        self.assertEqual(pool_ps.group_correct_placement, 3)

    def test_exact_scoreline_prediction_scoring_calculation(self):
        """Verifies that an exact scoreline prediction (2-1 predict vs 2-1 result) awards 10 max points."""
        from tournament.models import Match, MatchPrediction
        from tournament.services.scoring import calc_pred_points_detail

        match = Match.objects.create(
            tournament=self.tournament,
            match_number=1,
            home_goals=2,
            away_goals=1,
        )
        pred = MatchPrediction(
            match=match,
            home_goals=2,
            away_goals=1,
        )

        detail = calc_pred_points_detail(pred, match, self.point_system)
        self.assertTrue(detail['exact_score'])
        self.assertEqual(detail['pts_1x2'], 4)
        self.assertEqual(detail['pts_home'], 2)
        self.assertEqual(detail['pts_away'], 2)
        self.assertEqual(detail['pts_tot_goals'], 2)
    def test_scout_to_tournament_conversion_transfers_all_5_segments(self):
        """Verifies that convert_scanned_to_live_tournament transfers all 5 blueprint segments into relational DB models."""
        from tournament.models import ScannedTournament, MasterEvent, Tournament, Group, Team, Match, PointSystem, Sidebet
        from tournament.services.scout_service import convert_scanned_to_live_tournament
        import datetime

        blueprint = {
            'head_segment': {
                'name': '2026 European Women Handball Championship',
                'sport': 'Handball',
                'master_event_code': 'ehf-euro-2026-women',
                'start_date': '2026-12-03',
                'end_date': '2026-12-20',
            },
            'general_segment': {
                'organizer': 'EHF',
                'host_country': 'Czech Republic / Poland / Romania / Slovakia / Turkey',
                'official_website_url': 'https://ehfeuro.eurohandball.com/',
                'tournament_summary': '16th European Women Handball Championship edition.',
            },
            'structure_and_rules_segment': {
                'group_stage_rules': {'points_win': 2, 'points_draw': 1, 'points_loss': 0, 'teams_advancing': 2},
                'qualifying_tables_rules': {'has_best_thirds': False, 'has_runners_up': False},
                'knockout_rules': {'extra_time_minutes': 10, 'penalty_shootouts': True},
                'official_rules_summary': 'Top 2 teams advance to Main Round with carried over points.',
            },
            'groups_and_teams_segment': {
                'groups': [
                    {
                        'name': 'Group A',
                        'order': 1,
                        'teams': [
                            {'name': 'Sweden', 'code': 'SE'},
                            {'name': 'Norway', 'code': 'NO'},
                        ]
                    },
                    {
                        'name': 'Group B',
                        'order': 2,
                        'teams': [
                            {'name': 'Denmark', 'code': 'DK'},
                            {'name': 'France', 'code': 'FR'},
                        ]
                    }
                ]
            },
            'matches_and_knockout_segment': {
                'group_matches': [
                    {
                        'match_number': 1,
                        'stage_or_group': 'Group A',
                        'home_team': 'Sweden',
                        'away_team': 'Norway',
                        'date_time': '2026-12-03T18:00:00',
                        'venue': 'Oradea Arena',
                    }
                ]
            }
        }

        prospect = ScannedTournament.objects.create(
            name="2026 European Women Handball Championship",
            sport="Handball",
            master_event_code="ehf-euro-2026-women",
            start_date=datetime.date(2026, 12, 3),
            end_date=datetime.date(2026, 12, 20),
            host_country="Czech Republic / Poland / Romania / Slovakia / Turkey",
            organizer="EHF",
            tournament_blueprint=blueprint,
            payload={
                'tournament_blueprint': blueprint,
                'sidebets_suggestions': [
                    {'question': 'Vilket lag vinner EM-guld?', 'points': 10, 'question_type': 'TEAM'}
                ]
            }
        )

        tour, err = convert_scanned_to_live_tournament(prospect.id, self.admin_user, is_active=False)
        self.assertIsNone(err)
        self.assertIsNotNone(tour)
        self.assertFalse(tour.is_active)
        self.assertEqual(tour.sport, 'Handball')
        self.assertEqual(tour.start_date, datetime.date(2026, 12, 3))
        self.assertEqual(tour.end_date, datetime.date(2026, 12, 20))
        self.assertEqual(tour.host_country, 'Czech Republic / Poland / Romania / Slovakia / Turkey')
        self.assertEqual(tour.organizer, 'EHF')
        self.assertEqual(tour.tournament_summary, '16th European Women Handball Championship edition.')
        self.assertEqual(tour.master_event.code, 'ehf-euro-2026-women')

        # Verify Groups & Teams
        self.assertEqual(tour.tournament_groups.count(), 2)
        self.assertEqual(tour.teams.count(), 4)
        se_team = tour.teams.get(name='Sweden')
        self.assertEqual(se_team.code, 'SE')

        # Verify Matches & Venue
        match1 = tour.matches.get(match_number=1)
        self.assertEqual(match1.home_team, 'Sweden')
        self.assertEqual(match1.away_team, 'Norway')
        self.assertEqual(match1.venue, 'Oradea Arena')

        # Verify Sidebets
        self.assertEqual(tour.sidebets.count(), 1)
        self.assertEqual(tour.sidebets.first().question, 'Vilket lag vinner EM-guld?')

        # Verify ScannedTournament linked & marked converted
        prospect.refresh_from_db()
        self.assertEqual(prospect.status, 'CONVERTED')
        self.assertEqual(prospect.converted_tournament, tour)

    def test_engine_admin_tournament_details_and_update_views(self):
        """Verifies details JSON view and update view in Engine Admin."""
        from django.test import Client
        import json

        client = Client()
        client.force_login(self.admin_user)

        # 1. Details endpoint
        resp = client.get(f'/engine-admin/tournament/{self.tournament.id}/details/', HTTP_HOST='localhost:2029')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['tournament']['id'], self.tournament.id)

        # 2. Update endpoint
        update_resp = client.post(
            f'/engine-admin/update-tournament/{self.tournament.id}/',
            {
                'name': 'Updated UEFA Euro 2028',
                'sport': 'Football',
                'start_date': '2028-06-09',
                'end_date': '2028-07-09',
                'host_country': 'UK & Ireland',
                'organizer': 'UEFA',
                'official_regulations_url': 'https://documents.uefa.com/euro-2028',
                'tournament_summary': 'Official 18th edition in UK & Ireland.',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost:2029'
        )
        self.assertEqual(update_resp.status_code, 200)
        u_data = update_resp.json()
        self.assertEqual(u_data['status'], 'success')

        self.tournament.refresh_from_db()
        self.assertEqual(self.tournament.name, 'Updated UEFA Euro 2028')
        self.assertEqual(self.tournament.host_country, 'UK & Ireland')
        self.assertEqual(self.tournament.organizer, 'UEFA')

    def test_engine_admin_groups_teams_and_match_saving(self):
        """Verifies groups-teams JSON view, save-team endpoint, and save-match endpoint."""
        from django.test import Client
        from tournament.models import Group, Team, Match

        grp = Group.objects.create(tournament=self.tournament, name='Group Test', order=1)
        tm = Team.objects.create(tournament=self.tournament, group=grp, name='Team Old', code='TO')
        m = Match.objects.create(tournament=self.tournament, group=grp, match_number=99, home_team='Team Old', away_team='Opponent')

        client = Client()
        client.force_login(self.admin_user)

        # 1. Groups & Teams list
        list_resp = client.get(f'/engine-admin/tournament/{self.tournament.id}/groups-teams/', HTTP_HOST='localhost:2029')
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(list_resp.json()['status'], 'success')

        # 2. Save Team
        team_resp = client.post(
            f'/engine-admin/tournament/{self.tournament.id}/save-team/',
            {'team_id': tm.id, 'name': 'Team New', 'code': 'TN'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost:2029'
        )
        self.assertEqual(team_resp.status_code, 200)
        tm.refresh_from_db()
        self.assertEqual(tm.name, 'Team New')
        self.assertEqual(tm.code, 'TN')

        # 3. Save Match
        match_resp = client.post(
            f'/engine-admin/tournament/{self.tournament.id}/save-match/',
            {
                'match_id': m.id,
                'home_team': 'Team New',
                'away_team': 'Opponent',
                'venue': 'Wembley Stadium',
                'date_time': '2028-06-10 20:00'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost:2029'
        )
        self.assertEqual(match_resp.status_code, 200)
        m.refresh_from_db()
        self.assertEqual(m.venue, 'Wembley Stadium')

    def test_tournament_publication_workflow_for_pool_admins(self):
        """Verifies that inactive tournament is in coming_tournaments and active is in available_tournaments."""
        from tournament.models import League, LeagueMember
        from django.test import Client

        league = League.objects.create(
            name="Vännernas EM-Pool",
            admin=self.admin_user
        )
        LeagueMember.objects.create(league=league, player=self.admin_user, is_verified=True)

        client = Client()
        client.force_login(self.admin_user)

        # 1. While is_active=False (Draft mode)
        self.tournament.is_active = False
        self.tournament.save()

        resp = client.get(f'/pool-admin/{league.id}/')
        self.assertEqual(resp.status_code, 200)
        coming = resp.context['coming_tournaments']
        available = resp.context['available_tournaments']
        self.assertIn(self.tournament, coming)
        self.assertNotIn(self.tournament, available)

        # 2. Publish / Activate (is_active=True)
        self.tournament.is_active = True
        self.tournament.save()

        resp2 = client.get(f'/pool-admin/{league.id}/')
        self.assertEqual(resp2.status_code, 200)
        coming2 = resp2.context['coming_tournaments']
        available2 = resp2.context['available_tournaments']

class GeminiRateLimiterTest(TestCase):
    """Tests for the 5 calls/min Gemini Rate Limiter and 429 quota backoff handling."""

    def setUp(self):
        from tournament.services.gemini_rate_limiter import GeminiRateLimiter
        GeminiRateLimiter.reset()

    def tearDown(self):
        from tournament.services.gemini_rate_limiter import GeminiRateLimiter
        GeminiRateLimiter.reset()

    @override_settings(GEMINI_MAX_CALLS_PER_MINUTE=5, GEMINI_RATE_LIMIT_WINDOW_SECONDS=60.0)
    def test_rate_limiter_permits_up_to_five_calls(self):
        from tournament.services.gemini_rate_limiter import GeminiRateLimiter
        for i in range(5):
            acquired = GeminiRateLimiter.acquire(timeout=1.0)
            self.assertTrue(acquired, f"Call {i+1} should be acquired immediately")

        status = GeminiRateLimiter.get_status()
        self.assertEqual(status['active_calls_in_window'], 5)
        self.assertEqual(status['max_calls_per_minute'], 5)
        self.assertFalse(status['in_penalty_cooldown'])

    @override_settings(GEMINI_MAX_CALLS_PER_MINUTE=5, GEMINI_RATE_LIMIT_WINDOW_SECONDS=60.0)
    def test_rate_limiter_blocks_sixth_call_on_timeout(self):
        from tournament.services.gemini_rate_limiter import GeminiRateLimiter
        for _ in range(5):
            GeminiRateLimiter.acquire(timeout=1.0)

        # 6th call with very short timeout should fail because window is 60s
        acquired = GeminiRateLimiter.acquire(timeout=0.1)
        self.assertFalse(acquired, "6th call in 60s window should time out under 5 calls/min limit")

    def test_rate_limiter_429_penalty_backoff(self):
        from tournament.services.gemini_rate_limiter import GeminiRateLimiter
        GeminiRateLimiter.record_429(backoff_seconds=10.0)
        status = GeminiRateLimiter.get_status()
        self.assertTrue(status['in_penalty_cooldown'])
        self.assertGreater(status['penalty_remaining_seconds'], 0.0)

        # Immediate acquire should fail when timeout is short
        acquired = GeminiRateLimiter.acquire(timeout=0.05)
        self.assertFalse(acquired, "Should not acquire during 429 penalty backoff")

class TeamBadgeServiceTestCase(TestCase):
    def test_resolve_team_badge_known_country(self):
        from tournament.services.team_badge_service import TeamBadgeService
        res = TeamBadgeService.resolve_team_badge("Sweden")
        self.assertEqual(res.team_type, "NATIONAL")
        self.assertEqual(res.code, "se")
        self.assertEqual(res.canonical_name, "Sweden")
        self.assertIn("se.png", res.flag_url)

    def test_resolve_team_badge_fallback(self):
        from tournament.services.team_badge_service import TeamBadgeService
        res = TeamBadgeService.resolve_team_badge("TBD")
        self.assertTrue(res.is_placeholder)
        self.assertEqual(res.team_type, "PLACEHOLDER")

    @patch('tournament.services.team_badge_service.TeamBadgeService.query_gemini_team_disambiguation')
    @patch('tournament.services.team_badge_service.TeamBadgeService.query_wikidata_club_logo')
    def test_cache_behavior(self, mock_wiki, mock_gemini):
        from tournament.services.team_badge_service import TeamBadgeService
        mock_wiki.return_value = None
        mock_gemini.return_value = None

        res1 = TeamBadgeService.resolve_team_badge("Unknown FC")
        self.assertEqual(res1.team_type, "CLUB")
        self.assertEqual(mock_wiki.call_count, 1)

        res2 = TeamBadgeService.resolve_team_badge("Unknown FC")
        self.assertEqual(res2.team_type, "CLUB")
        self.assertEqual(mock_wiki.call_count, 1)

class CacheServiceTestCase(TestCase):
    @patch('tournament.services.cache_service.timezone.now')
    def test_invalidate_tournament_cache(self, mock_now):
        from tournament.services.cache_service import invalidate_tournament_cache, get_tournament_cache_version
        from django.core.cache import cache
        import datetime
        
        t_id = 9999
        cache.delete(f"t_version_{t_id}")
        
        mock_now.return_value = datetime.datetime(2026, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        v1 = get_tournament_cache_version(t_id)
        
        mock_now.return_value = datetime.datetime(2026, 1, 1, 12, 0, 5, tzinfo=datetime.timezone.utc)
        v2 = invalidate_tournament_cache(t_id)
        
        self.assertNotEqual(v1, v2)
        v3 = get_tournament_cache_version(t_id)
        self.assertEqual(v2, v3)

    def test_cache_key_format(self):
        from tournament.services.cache_service import get_tournament_cache_version
        v = get_tournament_cache_version(8888)
        self.assertIsInstance(v, int)

class PoolAdminServiceTestCase(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from tournament.models import PoolAdminRequest, MasterEvent
        self.admin = User.objects.create_superuser('pool_tester', 'pool@test.com', 'pass')
        self.user = User.objects.create_user('pool_requester', 'req@test.com', 'pass')
        self.master_event = MasterEvent.objects.create(name='Test Event', code='test-event')
        self.request = PoolAdminRequest.objects.create(
            user=self.user,
            master_event=self.master_event,
            pool_name='My Test Pool'
        )

    def test_approve_pool_admin_request(self):
        from tournament.services.pool_admin_service import approve_pool_admin_request
        league = approve_pool_admin_request(self.request, self.admin)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, 'APPROVED')
        self.assertEqual(self.request.reviewed_by, self.admin)
        self.assertIsNotNone(self.request.league)
        self.assertEqual(league.admin, self.user)

    def test_reject_pool_admin_request(self):
        from tournament.services.pool_admin_service import reject_pool_admin_request
        reject_pool_admin_request(self.request, self.admin, "Not allowed")
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, 'REJECTED')
        self.assertEqual(self.request.rejection_reason, "Not allowed")

class LifecycleStrategyTestCase(TestCase):
    def test_determine_tournament_type(self):
        from tournament.services.lifecycle_strategy import LifecycleStrategy, TournamentType
        self.assertEqual(LifecycleStrategy.determine_tournament_type("Champions League"), TournamentType.CLUB_CONTINENTAL)
        self.assertEqual(LifecycleStrategy.determine_tournament_type("World Cup"), TournamentType.INTERNATIONAL_NATIONAL)

    def test_calculate_lifecycle_phase(self):
        from tournament.services.lifecycle_strategy import LifecycleStrategy, ScraperPhase, TournamentType
        import datetime
        today = datetime.date(2026, 8, 24)
        
        state1 = LifecycleStrategy.calculate_lifecycle_phase(
            start_date=datetime.date(2026, 9, 24),
            tournament_type=TournamentType.INTERNATIONAL_NATIONAL,
            today=today
        )
        self.assertEqual(state1.phase, ScraperPhase.PHASE_3_PRODUCTION)

        state2 = LifecycleStrategy.calculate_lifecycle_phase(
            start_date=datetime.date(2028, 9, 24),
            tournament_type=TournamentType.INTERNATIONAL_NATIONAL,
            today=today
        )
        self.assertEqual(state2.phase, ScraperPhase.PHASE_1_MACRO_META)
        
        state3 = LifecycleStrategy.calculate_lifecycle_phase(
            start_date=datetime.date(2025, 1, 1),
            tournament_type=TournamentType.INTERNATIONAL_NATIONAL,
            today=today
        )
        self.assertEqual(state3.phase, ScraperPhase.PHASE_3_PRODUCTION)
        self.assertTrue(state3.days_to_start < 0)

class EngineAdminAjaxEndpointsTestCase(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from tournament.models import Tournament
        self.admin = User.objects.create_superuser('test_admin', 'admin@test.com', 'pass123')
        self.user = User.objects.create_user('test_user', 'user@test.com', 'pass123')
        self.tournament = Tournament.objects.create(name='Test Tourney', admin=self.admin)

    def test_pool_requests_view(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/engine-admin/pool-requests/', HTTP_HOST='localhost:2029')
        self.assertEqual(resp.status_code, 200)

    def test_validate_tournament_view(self):
        self.client.force_login(self.admin)
        resp = self.client.post(f'/engine-admin/validate/{self.tournament.id}/', HTTP_X_REQUESTED_WITH='XMLHttpRequest', HTTP_HOST='localhost:2029')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('overall_status', resp.json())

    def test_simulate_tournament_view(self):
        self.client.force_login(self.admin)
        resp = self.client.post(f'/engine-admin/simulate/{self.tournament.id}/', HTTP_X_REQUESTED_WITH='XMLHttpRequest', HTTP_HOST='localhost:2029')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('status', resp.json())

    def test_reset_simulation_view(self):
        self.client.force_login(self.admin)
        resp = self.client.post(f'/engine-admin/reset-simulation/{self.tournament.id}/', HTTP_X_REQUESTED_WITH='XMLHttpRequest', HTTP_HOST='localhost:2029')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('status', resp.json())

    def test_toggle_publish_view(self):
        self.client.force_login(self.admin)
        resp = self.client.post(f'/engine-admin/toggle-publish/{self.tournament.id}/', HTTP_X_REQUESTED_WITH='XMLHttpRequest', HTTP_HOST='localhost:2029')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('status', resp.json())

    def test_non_superuser_forbidden(self):
        self.client.force_login(self.user)
        resp = self.client.post(f'/engine-admin/validate/{self.tournament.id}/', HTTP_X_REQUESTED_WITH='XMLHttpRequest', HTTP_HOST='localhost:2029')
        self.assertIn(resp.status_code, [302, 401, 403])
import unittest
from unittest.mock import patch, MagicMock
from django.test import TestCase

from tournament.services.head_discovery_agent import HeadDiscoveryAgent
from tournament.services.general_deep_scout_agent import GeneralDeepScoutAgent
from tournament.services.structure_rules_agent import StructureRulesAgent
from tournament.services.groups_teams_agent import GroupsTeamsAgent
from tournament.services.matches_knockout_agent import MatchesKnockoutAgent
from tournament.schemas.tournament_prospect_schema import GroupsAndTeamsSegment

class ScoutAgentsTestCase(TestCase):
    def test_head_discovery_agent(self):
        head = HeadDiscoveryAgent.build_head_segment(
            name="World Cup 2026",
            sport="Football",
            start_date="2026-06-11",
            discovery_source="Test"
        )
        self.assertEqual(head.name, "World Cup 2026")
        self.assertEqual(head.master_event_code, "world-cup-2026")
        self.assertEqual(head.sport, "Football")
        self.assertTrue(head.is_h2h_team_sport)
        self.assertEqual(head.start_date, "2026-06-11")

    @patch('tournament.services.gemini_scout_service.GeminiScoutService.is_available', return_value=True)
    @patch('tournament.services.gemini_scout_service.GeminiScoutService.scout_general_details')
    @patch('tournament.services.wikidata_scout.WikidataScout.fetch_wikidata_entity')
    @patch('tournament.services.official_site_scout.OfficialSiteScout.discover_official_site')
    @patch('tournament.services.emblem_scout.EmblemScout.discover_official_emblem')
    def test_general_deep_scout_agent(self, mock_emblem, mock_official, mock_wiki, mock_gemini, mock_avail):
        mock_gemini.return_value = {
            "start_date": "2026-06-11",
            "host_country": "USA",
            "logo_url": "gemini_logo.png"
        }
        mock_emblem.return_value = "emblem_logo.png"
        mock_official.return_value = "https://example.com"
        mock_wiki.return_value = {"wikidata_qid": "Q123", "official_website_url": "https://example.com"}

        agent = GeneralDeepScoutAgent()
        result = agent.build_general_segment(
            tournament_name="Test Tournament",
            audit_data={"sport": "Football"}
        )

        self.assertEqual(result.start_date, "2026-06-11")
        self.assertEqual(result.location.host_country, "USA")
        self.assertEqual(result.emblem.logo_url, "gemini_logo.png")
        self.assertEqual(result.official_website_url, "https://example.com")

    @patch('tournament.services.gemini_scout_service.GeminiScoutService.is_available', return_value=True)
    @patch('tournament.services.gemini_scout_service.GeminiScoutService.scout_structure_and_rules')
    def test_structure_rules_agent(self, mock_gemini, mock_avail):
        mock_gemini.return_value = {
            "knockout_rules": {"starting_round": "Round of 16"},
            "draw_completed": True
        }
        agent = StructureRulesAgent()
        result = agent.build_structure_rules_segment(
            tournament_name="Test Tournament"
        )
        self.assertTrue(result.general_setup.draw_completed)
        self.assertEqual(result.knockout_rules.starting_round, "Round of 16")

    @patch('tournament.services.gemini_scout_service.GeminiScoutService.is_available', return_value=True)
    @patch('tournament.services.gemini_scout_service.GeminiScoutService.scout_groups_and_teams')
    def test_groups_teams_agent(self, mock_gemini, mock_avail):
        mock_gemini.return_value = {
            "groups": [
                {"name": "Group A", "teams": ["Team 1", "Team 2"]}
            ]
        }
        agent = GroupsTeamsAgent()
        result = agent.build_groups_teams_segment(
            tournament_name="Test Tournament"
        )
        self.assertEqual(len(result.groups), 1)
        self.assertEqual(result.groups[0].name, "Group A")
        self.assertEqual(len(result.groups[0].teams), 2)
        self.assertEqual(result.groups[0].teams[0].name, "Team 1")

    @patch('tournament.services.gemini_scout_service.GeminiScoutService.is_available', return_value=True)
    @patch('tournament.services.gemini_scout_service.GeminiScoutService.scout_matches_and_knockout')
    def test_matches_knockout_agent(self, mock_gemini, mock_avail):
        mock_gemini.return_value = {
            "fixtures": [
                {"match_number": 1, "home_team": "Team 1", "away_team": "Team 2", "stage": "Group A"}
            ],
            "knockout_stages": [
                {"stage_name": "Final", "matches": [
                    {"match_number": 2, "home_team": "Winner 1", "away_team": "Winner 2"}
                ]}
            ]
        }
        agent = MatchesKnockoutAgent()
        # Create a dummy groups_segment with confirmed real teams & draw completed
        groups_seg = GroupsAndTeamsSegment(groups=[], has_real_teams=True)
        result = agent.build_matches_knockout_segment(
            audit_data={"draw_completed": True},
            tournament_name="Test Tournament",
            groups_segment=groups_seg
        )
        self.assertEqual(len(result.group_matches), 1)
        self.assertEqual(result.group_matches[0].match_number, 1)
        self.assertEqual(len(result.knockout_bracket), 1)
        self.assertEqual(result.knockout_bracket[0].stage_name, "Final")

    @patch('tournament.services.gemini_scout_service.GeminiScoutService.is_available', return_value=True)
    @patch('tournament.services.gemini_scout_service.GeminiScoutService.scout_matches_and_knockout')
    def test_ai_studio_matches_schema_normalization(self, mock_gemini, mock_avail):
        # Test Google AI Studio style nested payload with group_matches and knockout_bracket
        mock_gemini.return_value = {
            "total_matches": 66,
            "fixtures_completed": True,
            "group_matches": [
                {
                    "match_number": 1,
                    "stage_or_group": "Group A",
                    "home_team": "Saudi Arabia",
                    "away_team": "Jordan",
                    "home_team_code": "SA",
                    "away_team_code": "JO",
                    "date_time": "2027-01-07",
                    "venue": "King Fahd Stadium",
                    "is_placeholder": False
                }
            ],
            "advancement_fixtures": [
                {
                    "match_code": "R16_1",
                    "stage_name": "Round of 16",
                    "source_home": "Winner Group A",
                    "source_away": "Runner-up Group B"
                }
            ],
            "knockout_bracket": [
                {
                    "stage_name": "Quarterfinals",
                    "round_order": 1,
                    "matches": [
                        {
                            "match_code": "QF_1",
                            "stage_name": "Quarterfinals",
                            "home_team": "1A",
                            "away_team": "2B",
                            "winner_to": "SF_1",
                            "date_time": "2027-01-25",
                            "venue": "King Fahd Stadium"
                        }
                    ]
                }
            ]
        }
        agent = MatchesKnockoutAgent()
        groups_seg = GroupsAndTeamsSegment(groups=[], has_real_teams=True)
        result = agent.build_matches_knockout_segment(
            audit_data={"draw_completed": True},
            tournament_name="2027 AFC Asian Cup",
            sport="Football",
            groups_segment=groups_seg,
            tournament_meta={
                "name": "2027 AFC Asian Cup",
                "sport": "Football",
                "organizer": "AFC",
                "host_country": "Saudi Arabia",
                "start_date": "2027-01-07",
                "end_date": "2027-02-05",
                "total_teams": 24
            }
        )
        self.assertEqual(len(result.group_matches), 1)
        self.assertEqual(result.group_matches[0].home_team, "Saudi Arabia")
        self.assertEqual(result.group_matches[0].home_team_code, "sa")
        self.assertEqual(result.group_matches[0].home_team_flag_url, "https://flagcdn.com/w40/sa.png")
        self.assertEqual(len(result.advancement_fixtures), 1)
        self.assertEqual(result.advancement_fixtures[0].match_code, "R16_1")
        self.assertEqual(len(result.knockout_bracket), 1)
        self.assertEqual(result.knockout_bracket[0].matches[0].winner_to, "SF_1")


class RestScoutApiTestCase(TestCase):
    """Tests for Direct REST API Pull and Pydantic validation ingestion."""

    @patch('tournament.services.scout_service.requests.get')
    def test_fetch_and_ingest_from_api(self, mock_get):
        from tournament.services.scout_service import fetch_and_ingest_from_api
        from tournament.models import ScannedTournament
        import datetime

        today = datetime.date.today()
        future_start = (today + datetime.timedelta(days=60)).strftime("%Y-%m-%d")
        future_end = (today + datetime.timedelta(days=75)).strftime("%Y-%m-%d")

        mock_payload = {
            "tournaments": [
                {
                    "id": "tourn-fifa-wc-2027",
                    "name": "2027 FIFA Women's World Cup",
                    "sport": "Football",
                    "category": "Main",
                    "organizer": "FIFA",
                    "host_country": "Brazil",
                    "start_date": future_start,
                    "end_date": future_end,
                    "total_teams": 32,
                    "official_website_url": "https://www.fifa.com/",
                    "wikipedia_url": "https://en.wikipedia.org/wiki/2027_FIFA_Women%27s_World_Cup",
                    "prediction_engine_status": "NEW"
                }
            ]
        }

        mock_resp = mock_get.return_value
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_payload

        created, updated, prospects = fetch_and_ingest_from_api(
            api_url="http://localhost:3000/api/tournaments",
            min_runway=30,
        )

        self.assertEqual(created, 1)
        self.assertEqual(len(prospects), 1)
        prospect = ScannedTournament.objects.filter(name="2027 FIFA Women's World Cup").first()
        self.assertIsNotNone(prospect)
        self.assertEqual(prospect.sport, "Football")
        self.assertEqual(prospect.host_country, "Brazil")
        self.assertEqual(prospect.completeness_grade, "GRADE_C")

    @patch('tournament.services.scout_service.requests.get')
    def test_fetch_scout_api_management_command(self, mock_get):
        from django.core.management import call_command
        from io import StringIO
        import datetime

        today = datetime.date.today()
        future_start = (today + datetime.timedelta(days=90)).strftime("%Y-%m-%d")
        future_end = (today + datetime.timedelta(days=105)).strftime("%Y-%m-%d")

        mock_resp = mock_get.return_value
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tournaments": [
                {
                    "id": "tourn-chl-2027",
                    "name": "2027–28 Champions Hockey League",
                    "sport": "Ice Hockey",
                    "organizer": "IIHF",
                    "host_country": "Europe",
                    "start_date": future_start,
                    "end_date": future_end,
                    "total_teams": 24,
                    "official_website_url": "https://www.championshockeyleague.com/",
                    "prediction_engine_status": "NEW"
                }
            ]
        }

        out = StringIO()
        call_command("fetch_scout_api", "--url", "http://localhost:3000/api/tournaments", "--min-runway", "30", stdout=out)
        output = out.getvalue()
        self.assertIn("REST API Ingestion Completed", output)
        self.assertIn("Champions Hockey League", output)


class DateFormattingAndNormalizationTestCase(TestCase):
    """Tests that all dates are parsed and formatted as strict ISO YYYY-MM-DD."""

    def test_llm_date_string_parser_formats(self):
        from tournament.services.llm_wikipedia_scout import LLMWikipediaScout

        self.assertEqual(LLMWikipediaScout._parse_date_string("Sept 5, 2026"), "2026-09-05")
        self.assertEqual(LLMWikipediaScout._parse_date_string("3rd of August 2026"), "2026-08-03")
        self.assertEqual(LLMWikipediaScout._parse_date_string("August 3rd, 2026"), "2026-08-03")
        self.assertEqual(LLMWikipediaScout._parse_date_string("11 June 2026"), "2026-06-11")
        self.assertEqual(LLMWikipediaScout._parse_date_string("2026-06-11"), "2026-06-11")
        self.assertEqual(LLMWikipediaScout._parse_date_string("May 2026"), "2026-05-01")

    def test_matches_knockout_date_normalizer(self):
        from tournament.services.matches_knockout_agent import MatchesKnockoutAgent

        self.assertEqual(MatchesKnockoutAgent._normalize_match_date("Sept 5, 2026"), "2026-09-05")
        self.assertEqual(MatchesKnockoutAgent._normalize_match_date("3rd of August 2026", "18:00"), "2026-08-03 18:00")
        self.assertEqual(MatchesKnockoutAgent._normalize_match_date("2026-06-11 21:00"), "2026-06-11 21:00")
        self.assertEqual(MatchesKnockoutAgent._normalize_match_date("2026-06-11"), "2026-06-11")
        self.assertIsNone(MatchesKnockoutAgent._normalize_match_date("TBD"))
        self.assertIsNone(MatchesKnockoutAgent._normalize_match_date(""))


class OfficialSiteScoutAndIngestTestCase(TestCase):
    """Tests for Official Federation Portal Discovery, Source Ranking, and Ingestion Engine."""

    def test_official_source_ranking_scores(self):
        from tournament.services.official_site_scout import OfficialSiteScout

        # Official federation press release
        caf_url = "https://www.cafonline.com/afcon2025/news/the-road-to-east-africa-mapped-out-the-qualifier-draw/"
        meta_caf = OfficialSiteScout.rank_source_url(caf_url, "2027 Africa Cup of Nations")
        self.assertEqual(meta_caf["category"], "OFFICIAL_FEDERATION")
        self.assertGreaterEqual(meta_caf["score"], 85)

        # Official CONCACAF regulations
        concacaf_url = "https://www.concacaf.com/competitions/gold-cup/news/2027-concacaf-gold-cup-qualification-pathway-confirmed/"
        meta_concacaf = OfficialSiteScout.rank_source_url(concacaf_url, "CONCACAF Gold Cup")
        self.assertEqual(meta_concacaf["category"], "OFFICIAL_FEDERATION")
        self.assertGreaterEqual(meta_concacaf["score"], 85)

        # Trusted media
        bbc_url = "https://www.bbc.com/sport/football/articles/c049d97yv4qo"
        meta_bbc = OfficialSiteScout.rank_source_url(bbc_url, "2026 FIFA World Cup")
        self.assertEqual(meta_bbc["category"], "TRUSTED_MEDIA")
        self.assertGreaterEqual(meta_bbc["score"], 30)

        # Wikipedia / Wiki registries
        wiki_url = "https://en.wikipedia.org/wiki/2027_Africa_Cup_of_Nations"
        meta_wiki = OfficialSiteScout.rank_source_url(wiki_url, "2027 Africa Cup of Nations")
        self.assertEqual(meta_wiki["category"], "OPEN_REGISTRY")
        self.assertEqual(meta_wiki["score"], 20)

    @patch("requests.get")
    def test_official_page_ingestion_draw_and_groups(self, mock_get):
        from tournament.services.official_regulations_verifier import OfficialRegulationsVerifier

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.text = """
        <html>
          <body>
            <h1>TotalEnergies CAF Africa Cup of Nations 2027</h1>
            <p>The official qualifier draw concluded on 19 February 2026 in Cairo.</p>
            <p>The top 2 teams in each group will advance directly to the final tournament.</p>
            <div class="groups">
              <p>Group A: Egypt, Ghana, Uganda, Somalia</p>
              <p>Group B: Senegal, Mali, Benin, Liberia</p>
            </div>
          </body>
        </html>
        """
        mock_get.return_value = mock_resp

        verifier = OfficialRegulationsVerifier()
        result = verifier.ingest_official_page(
            "https://www.cafonline.com/afcon2027/news/draw-concluded/",
            "2027 Africa Cup of Nations"
        )
        self.assertTrue(result["verified"])
        self.assertEqual(result["draw_date"], "2026-02-19")
        self.assertTrue(result["draw_completed"])
        self.assertEqual(len(result["groups"]), 2)
        self.assertEqual(result["groups"][0]["name"], "Group A")
        self.assertEqual(len(result["groups"][0]["teams"]), 4)
        self.assertEqual(result["groups"][0]["teams"][0]["name"], "Egypt")

    def test_umbrella_brand_merging_and_deduplication(self):
        from tournament.models import ScannedTournament
        from tournament.services.scout_service import normalize_brand_key, merge_duplicate_scanned_tournaments_by_wikipedia
        from tournament.services.modular_deep_scout import ModularDeepScout
        import datetime

        # Test brand key normalization
        self.assertEqual(normalize_brand_key("UEFA Nations League"), "uefanationsleague")
        self.assertEqual(normalize_brand_key("2026–27 UEFA Nations League"), "uefanationsleague")
        self.assertEqual(normalize_brand_key("CONCACAF Gold Cup"), "concacafgoldcup")
        self.assertEqual(normalize_brand_key("2027 CONCACAF Gold Cup"), "concacafgoldcup")

        # Create concrete 2026-27 UEFA Nations League prospect
        concrete = ScannedTournament.objects.create(
            name="2026–27 UEFA Nations League",
            sport="Football",
            completeness_grade="GRADE_A",
            status="READY",
            start_date=datetime.date(2026, 9, 3),
            end_date=datetime.date(2027, 6, 13),
            payload={
                "matches_and_knockout_segment": {
                    "group_matches": [{"match_id": "M1", "round": "Matchday 1"}] * 10
                }
            }
        )

        # Create generic umbrella UEFA Nations League prospect
        umbrella = ScannedTournament.objects.create(
            name="UEFA Nations League",
            sport="Football",
            completeness_grade="GRADE_C",
            status="NOT_READY",
            official_source_url="https://www.uefa.com/uefanationsleague/",
            payload={}
        )

        # Test ModularDeepScout auto-merges generic umbrella into concrete edition
        scout = ModularDeepScout()
        res = scout.deep_scan_prospect(umbrella)

        self.assertTrue(res["ok"])
        self.assertEqual(res["merged_into"], concrete.id)
        self.assertEqual(res["target_name"], "2026–27 UEFA Nations League")
        self.assertEqual(res["grade"], "GRADE_A")

        # Verify umbrella is deleted and concrete has official_source_url merged
        self.assertFalse(ScannedTournament.objects.filter(id=umbrella.id).exists())
        concrete.refresh_from_db()
        self.assertEqual(concrete.official_source_url, "https://www.uefa.com/uefanationsleague/")


class PoolAdminTournamentConfigTestCase(TestCase):
    """Verifies tournament activation/config workspace, rules integration, 25p sidebets, and participant management."""

    def setUp(self):
        self.admin = User.objects.create_user(username='poolboss', email='boss@example.com', password='password123', first_name='Boss')
        self.admin.profile.terms_accepted = True
        self.admin.profile.save()
        self.player1 = User.objects.create_user(username='player1', email='p1@example.com', password='password123', first_name='Anna')
        self.player1.profile.terms_accepted = True
        self.player1.profile.save()
        self.player2 = User.objects.create_user(username='player2', email='p2@example.com', password='password123', first_name='Björn')
        self.player2.profile.terms_accepted = True
        self.player2.profile.save()

        self.league = League.objects.create(name='Test Poolen', admin=self.admin, invite_code='TESTP1')
        LeagueMember.objects.create(league=self.league, player=self.admin, is_verified=True)
        LeagueMember.objects.create(league=self.league, player=self.player1, is_verified=True)
        LeagueMember.objects.create(league=self.league, player=self.player2, is_verified=True)

        self.tournament = Tournament.objects.create(
            name="2026 Men's World Floorball Championship",
            sport="Floorball",
            admin=self.admin,
            start_date=datetime.date(2026, 12, 4),
            end_date=datetime.date(2026, 12, 13),
            official_rules="Topp 2 i Grupp A & B går till Kvartsfinal.",
            official_regulations_url="https://floorball.sport/wfc2026/"
        )
        self.stage_playoff = KnockoutStage.objects.create(tournament=self.tournament, name="Play-off", order=1)
        self.stage_qf = KnockoutStage.objects.create(tournament=self.tournament, name="Quarterfinals", order=2)
        self.stage_sf = KnockoutStage.objects.create(tournament=self.tournament, name="Semifinals", order=3)
        self.stage_bronze = KnockoutStage.objects.create(tournament=self.tournament, name="Bronze match", order=4)
        self.stage_final = KnockoutStage.objects.create(tournament=self.tournament, name="Final", order=5)

    def test_pool_admin_tournament_config_context_and_rounds(self):
        client = Client()
        client.force_login(self.admin)

        resp = client.get(f'/pool-admin/{self.league.id}/tournament/{self.tournament.id}/', HTTP_HOST='localhost:2028')
        self.assertEqual(resp.status_code, 200)

        # Verify context data
        self.assertIn('structure_data', resp.context)
        self.assertIn('tournament_knockout_stages', resp.context)

        struct = resp.context['structure_data']
        self.assertEqual(struct['official_rules'], "Topp 2 i Grupp A & B går till Kvartsfinal.")
        self.assertEqual(struct['official_regulations_url'], "https://floorball.sport/wfc2026/")

        stages = resp.context['tournament_knockout_stages']
        self.assertEqual(len(stages), 5)
        self.assertEqual(stages[0]['stage_name'], 'Play-off')
        self.assertEqual(stages[0]['field_name'], 'knockout_round_of_32')
        self.assertEqual(stages[1]['stage_name'], 'Quarterfinals')
        self.assertEqual(stages[1]['field_name'], 'knockout_quarterfinal')
        self.assertEqual(stages[3]['stage_name'], 'Bronze match')
        self.assertEqual(stages[3]['field_name'], 'knockout_bronze_match')
        self.assertEqual(stages[4]['stage_name'], 'Final')
        self.assertEqual(stages[4]['field_name'], 'knockout_final')

    def test_sidebet_default_points_25(self):
        # 1. Model default
        sb = Sidebet.objects.create(tournament=self.tournament, question="Vem vinner skytteligan?")
        self.assertEqual(sb.points, 25)

        # 2. View creation default
        client = Client()
        client.force_login(self.admin)
        client.post(
            f'/pool-admin/{self.league.id}/sidebet/',
            {'tournament_id': self.tournament.id, 'question': 'Egen fråga?', 'question_type': 'TEXT'},
            HTTP_HOST='localhost:2028'
        )
        created_sb = Sidebet.objects.filter(tournament=self.tournament, question='Egen fråga?').first()
        self.assertIsNotNone(created_sb)
        self.assertEqual(created_sb.points, 25)

    def test_add_player_directly_to_tournament(self):
        client = Client()
        client.force_login(self.admin)

        resp = client.post(
            f'/pool-admin/{self.league.id}/add-player/',
            {
                'first_name': 'Kalle',
                'last_name': 'Anka',
                'email': 'kalle@example.com',
                'password': 'SecretPassword123!',
                'tournament_id': self.tournament.id
            },
            HTTP_HOST='localhost:2028',
            follow=True
        )
        self.assertEqual(resp.status_code, 200)

        # Verify user created
        kalle = User.objects.get(email='kalle@example.com')
        self.assertEqual(kalle.first_name, 'Kalle')

        # Verify user NOT in pool/league members (only tournament-specific)
        self.assertFalse(LeagueMember.objects.filter(league=self.league, player=kalle).exists())

        # Verify user linked to tournament
        self.assertTrue(self.tournament.players.filter(id=kalle.id).exists())

    def test_bulk_toggle_players(self):
        client = Client()
        client.force_login(self.admin)

        # 1. Enroll all
        resp = client.post(
            f'/pool-admin/{self.league.id}/tournament/{self.tournament.id}/bulk-players/',
            {'action': 'enroll_all'},
            HTTP_HOST='localhost:2028',
            follow=True
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.tournament.players.count(), 3)

        # 2. Remove all
        resp = client.post(
            f'/pool-admin/{self.league.id}/tournament/{self.tournament.id}/bulk-players/',
            {'action': 'remove_all'},
            HTTP_HOST='localhost:2028',
            follow=True
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.tournament.players.count(), 0)

    def test_toggle_tournament_submission_verification(self):
        client = Client()
        client.force_login(self.admin)

        # Toggle on
        resp = client.post(
            f'/pool-admin/{self.league.id}/tournament/{self.tournament.id}/verify-submission/{self.player1.id}/',
            HTTP_HOST='localhost:2028',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['is_verified'])

        # Toggle off
        resp2 = client.post(
            f'/pool-admin/{self.league.id}/tournament/{self.tournament.id}/verify-submission/{self.player1.id}/',
            HTTP_HOST='localhost:2028',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertTrue(data2['success'])
        self.assertFalse(data2['is_verified'])


class MagicLinkAuthTestCase(TestCase):
    """Verifies magic link passwordless login, forced password setup, and Pool Admin magic link workflows."""

    def setUp(self):
        self.admin = User.objects.create_user(username='admin_boss', email='boss@pool.test', password='password123', first_name='Boss')
        self.admin.profile.terms_accepted = True
        self.admin.profile.save()
        self.league = League.objects.create(name='Magic Pool', admin=self.admin, invite_code='MAGIC1')
        LeagueMember.objects.create(league=self.league, player=self.admin, is_verified=True)

        self.tournament = Tournament.objects.create(
            name="World Championship 2026",
            sport="Football",
            admin=self.admin,
            start_date=datetime.date(2026, 6, 1),
            end_date=datetime.date(2026, 7, 1)
        )
        self.league.tournaments.add(self.tournament)

    def test_magic_token_generation_and_verification(self):
        from tournament.utils.magic_link import generate_magic_token, verify_magic_token
        user = User.objects.create_user(username='newbie', email='newbie@test.com', first_name='New')
        token = generate_magic_token(user, self.league.id)
        self.assertIsInstance(token, str)

        payload = verify_magic_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload['user_id'], user.id)
        self.assertEqual(payload['league_id'], self.league.id)

    def test_magic_login_forces_password_setup_for_unusable_password_user(self):
        from tournament.utils.magic_link import generate_magic_token
        user = User.objects.create(username='invited_user', email='invited@test.com', first_name='Invited')
        user.set_unusable_password()
        user.save()
        user.profile.must_set_password = True
        user.profile.save()

        token = generate_magic_token(user, self.league.id)
        client = Client()
        resp = client.get(f'/auth/magic/{token}/', HTTP_HOST='localhost:2028', follow=True)
        self.assertEqual(resp.status_code, 200)

        # Verified that user is logged in
        self.assertEqual(int(client.session['_auth_user_id']), user.id)
        # Verified that user is redirected to set_password page
        self.assertTemplateUsed(resp, 'tournament/set_password.html')

    def test_set_password_view_and_middleware(self):
        user = User.objects.create(username='setpwd_user', email='setpwd@test.com', first_name='SetPwd')
        user.set_unusable_password()
        user.save()
        user.profile.must_set_password = True
        user.profile.terms_accepted = False
        user.profile.save()

        client = Client()
        client.force_login(user)

        # 1. Middleware should block dashboard and force redirect to /auth/set-password/
        resp = client.get('/dashboard/', HTTP_HOST='localhost:2028', follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/auth/set-password/')

        # 2. Submit valid password but without accepting terms
        resp_no_terms = client.post('/auth/set-password/', {'password': 'mypassword123', 'confirm_password': 'mypassword123'}, HTTP_HOST='localhost:2028')
        self.assertEqual(resp_no_terms.status_code, 200)
        user.profile.refresh_from_db()
        self.assertFalse(user.profile.terms_accepted)
        self.assertTrue(user.profile.must_set_password)

        # 3. Submit mismatched passwords with terms
        resp_bad = client.post('/auth/set-password/', {'password': 'mypassword', 'confirm_password': 'different', 'accept_terms': 'on'}, HTTP_HOST='localhost:2028')
        self.assertEqual(resp_bad.status_code, 200)
        user.profile.refresh_from_db()
        self.assertTrue(user.profile.must_set_password)

        # 4. Submit valid password AND accept terms
        resp_good = client.post('/auth/set-password/', {'password': 'mypassword123', 'confirm_password': 'mypassword123', 'accept_terms': 'on'}, HTTP_HOST='localhost:2028', follow=True)
        self.assertEqual(resp_good.status_code, 200)

        user.refresh_from_db()
        user.profile.refresh_from_db()
        self.assertFalse(user.profile.must_set_password)
        self.assertTrue(user.profile.terms_accepted)
        self.assertIsNotNone(user.profile.terms_accepted_at)
        self.assertEqual(user.profile.terms_version, "2026-08-26")
        self.assertTrue(user.check_password('mypassword123'))

        # 5. Now dashboard is fully accessible
        resp_dash = client.get('/dashboard/', HTTP_HOST='localhost:2028')
        self.assertEqual(resp_dash.status_code, 200)

    def test_terms_page_and_registration(self):
        client = Client()

        # 1. Public Terms page works
        resp = client.get('/terms/', HTTP_HOST='localhost:2028')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "ANVÄNDARAVTAL")
        self.assertContains(resp, "TJÄNSTENS SYFTE OCH BEGRÄNSNINGAR")
        self.assertContains(resp, "Stödlinjen")
        self.assertContains(resp, "Spelpaus")

        # 2. Registration requires terms acceptance
        resp_reg_fail = client.post('/register/', {
            'first_name': 'Kalle',
            'last_name': 'Anka',
            'email': 'kalle@anka.test',
            'password1': 'secretPass123',
            'password2': 'secretPass123',
        }, HTTP_HOST='localhost:2028')
        self.assertEqual(resp_reg_fail.status_code, 200)
        self.assertFalse(User.objects.filter(email='kalle@anka.test').exists())

        # 3. Registration succeeds when terms accepted
        resp_reg_ok = client.post('/register/', {
            'first_name': 'Kalle',
            'last_name': 'Anka',
            'email': 'kalle@anka.test',
            'password1': 'secretPass123',
            'password2': 'secretPass123',
            'accept_terms': 'on'
        }, HTTP_HOST='localhost:2028', follow=True)
        self.assertEqual(resp_reg_ok.status_code, 200)

        created_user = User.objects.filter(email='kalle@anka.test').first()
        self.assertIsNotNone(created_user)
        self.assertTrue(created_user.profile.terms_accepted)
        self.assertEqual(created_user.profile.terms_version, "2026-08-26")

    def test_pool_admin_add_participant_without_password(self):
        client = Client()
        client.force_login(self.admin)

        resp = client.post(
            f'/pool-admin/{self.league.id}/add-player/',
            {
                'first_name': 'Zlatan',
                'last_name': 'Ibrahimovic',
                'email': 'zlatan@milan.test',
                'tournament_id': self.tournament.id
            },
            HTTP_HOST='localhost:2028',
            follow=True
        )
        self.assertEqual(resp.status_code, 200)

        created_user = User.objects.filter(email='zlatan@milan.test').first()
        self.assertIsNotNone(created_user)
        self.assertEqual(created_user.first_name, 'Zlatan')
        self.assertFalse(created_user.has_usable_password())
        self.assertTrue(created_user.profile.must_set_password)

    def test_pool_admin_reset_player_password_endpoint(self):
        player = User.objects.create_user(username='regular_player', email='reg@test.com', password='oldpassword123', first_name='Reg')
        self.league.members.create(player=player, is_verified=True)

        client = Client()
        client.force_login(self.admin)

        resp = client.post(
            f'/pool-admin/{self.league.id}/player/{player.id}/reset-password/',
            HTTP_HOST='localhost:2028',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertIn('/auth/magic/', data['magic_link'])

        player.profile.refresh_from_db()
        self.assertTrue(player.profile.must_set_password)






