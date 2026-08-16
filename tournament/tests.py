from django.test import TestCase
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
        self.assertEqual(response.status_code, 200)




