from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.contrib.auth.models import User

from tournament.models import (
    Tournament, Match, MatchPrediction, TournamentSubmission,
    DailyGazette, RoundLeaderboardSnapshot, PointSystem, League, LeagueMember
)
from tournament.editorial_engine.special_edition_reporter import SpecialEditionReporter
from tournament.editorial_engine.detectors import check_and_trigger_special_editions


class SpecialEditionTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', 'admin@test.com', 'password')
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
        self.admin = User.objects.create_superuser('admin', 'admin@test.com', 'password')
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
        self.admin = User.objects.create_superuser('admin_user', 'admin@engine.test', 'adminpass123')
        self.staff = User.objects.create_user('staff_user', 'staff@engine.test', 'staffpass123', is_staff=True)
        self.normal_user = User.objects.create_user('player1', 'p1@engine.test', 'playerpass123')
        self.tournament = Tournament.objects.create(name='Original Tournament Name', admin=self.admin)

    def test_update_tournament_name_by_admin(self):
        self.client.login(username='admin_user', password='adminpass123')
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
        self.client.login(username='staff_user', password='staffpass123')

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
        self.admin = User.objects.create_superuser('wan_admin', 'admin@wan.test', 'adminpass123')

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
        self.client.login(username='wan_admin', password='adminpass123')
        response = self.client.get(
            '/engine-admin/',
            HTTP_HOST='217.31.171.173:2029',
            HTTP_X_FORWARDED_PROTO='https',
            secure=True
        )
class ScoutServiceTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('scout_admin', 'scout@admin.test', 'scoutpass123')

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
        admin = User.objects.create_superuser('wiki_admin', 'wiki@admin.test', 'wikipass123')
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
        self.assertIn('importerades', data['message'])

    @patch('tournament.services.wikipedia_scout.requests.get')
    def test_scout_deep_scan_one_view(self, mock_get):
        import datetime
        from tournament.models import ScannedTournament
        admin = User.objects.create_superuser('deep_admin', 'deep@admin.test', 'deeppass123')
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
        admin = User.objects.create_superuser('url_admin', 'url@admin.test', 'urlpass123')
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

    @patch('tournament.services.llm_wikipedia_scout.LLMWikipediaScout.audit_with_llm')
    def test_deep_scan_rejects_missing_date(self, mock_audit):
        """_run_deep_scan_on_prospect deletes prospect and fails if start_date is missing."""
        from tournament.models import ScannedTournament
        from tournament.views.engine_admin import _run_deep_scan_on_prospect
        from tournament.services.wikipedia_scout import WikipediaScout
        from tournament.services.official_regulations_verifier import OfficialRegulationsVerifier

        prospect = ScannedTournament.objects.create(
            name="No Date Cup 2027",
            master_event_code="no-date-cup-2027",
            start_date=None,
            payload={}
        )

        mock_audit.return_value = {
            'page_title': 'No Date Cup 2027',
            'tournament_start_date': '',
            'tournament_end_date': '',
            'start_date': '',
            'end_date': '',
            'draw_completed': False,
            'fixtures_completed': False,
        }

        res = _run_deep_scan_on_prospect(prospect, WikipediaScout(), OfficialRegulationsVerifier())
        self.assertFalse(res['ok'])
        self.assertIn('Turneringar utan datum läggs inte till', res['error'])
        self.assertFalse(ScannedTournament.objects.filter(id=prospect.id).exists())

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
        self.assertIn('pågående eller avslutad', res['error'])
        self.assertFalse(ScannedTournament.objects.filter(id=prospect.id).exists())




