from django.test import TestCase
from django.contrib.auth.models import User
from tournament.models import (
    Tournament, Match, MatchPrediction, TournamentSubmission,
    DailyGazette, RoundLeaderboardSnapshot, PointSystem
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


class HerrklubbTestCase(TestCase):
    def setUp(self):
        self.member = User.objects.create_user('member1', 'm1@test.com', 'password')
        self.member.profile.is_herrklubb_member = True
        self.member.profile.save()

        self.external_user = User.objects.create_user('external', 'ext@test.com', 'password')

        from tournament.models import BucketCategory, BucketItem, BucketVote, BucketDream
        self.cat = BucketCategory.objects.create(name='Sport', icon='⚽', order=1)
        self.item1 = BucketItem.objects.create(title='Serie A Fotbollsresa', category=self.cat)
        self.item2 = BucketItem.objects.create(title='Formel 1', category=self.cat)

    def test_marker_point_values(self):
        from tournament.models import BucketVote
        BucketVote.objects.create(user=self.member, item=self.item1, marker='SVART')
        self.assertEqual(self.item1.total_points, 100)
        self.assertEqual(self.item1.vote_count, 1)
        self.assertFalse(self.item1.is_planerad)

    def test_majority_threshold_to_planerad(self):
        from tournament.models import BucketVote
        # Create 6 distinct members and vote on item1
        for i in range(6):
            u = User.objects.create_user(f'user_{i}', f'u{i}@test.com', 'password')
            u.profile.is_herrklubb_member = True
            u.profile.save()
            BucketVote.objects.create(user=u, item=self.item1, marker='ROD')

        self.assertEqual(self.item1.vote_count, 6)
        self.assertTrue(self.item1.is_planerad)

    def test_freed_votes_on_completion(self):
        from tournament.models import BucketVote
        vote = BucketVote.objects.create(user=self.member, item=self.item1, marker='SVART')
        self.item1.is_completed = True
        self.item1.save()

        # Active votes count for uncompleted items
        active_votes = BucketVote.objects.filter(user=self.member, item__is_completed=False)
        self.assertEqual(active_votes.count(), 0)

    def test_herrklubb_access_control(self):
        # External user should be blocked from /herrklubb/
        self.client.login(username='external', password='password')
        response = self.client.get('/herrklubb/')
        self.assertEqual(response.status_code, 302) # redirected to /predictions/


