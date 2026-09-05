import os
from django.test import TestCase
from django.contrib.auth.models import User
from tournament.models import Tournament, Match, MatchPrediction, DailyGazette, StaticInsight, StyleExample, EditorialSettings, BannedPhrase
from tournament.editorial_engine.copywriter import Copywriter
from tournament.editorial_engine.journalist import Journalist
from tournament.editorial_engine.compiler import is_toarps_pool, get_player_nick_or_name, FORMAT_TYPES
from tournament.editorial_engine.posture_engine import resolve_portrait_url, resolve_posture_path
from tournament.editorial_engine.special_edition_reporter import SpecialEditionReporter


class EditorialEngineImprovementsTest(TestCase):
    """Test suite covering editorial pipeline enhancements."""

    def test_v2_syntax_enforcement(self):
        """Verify expanded Swedish V2 verb-second fronting patterns are auto-corrected."""
        # Standard Inför
        text1 = "Inför matchstart Krantz drog igång diskussionen."
        self.assertEqual(Copywriter.enforce_swedish_v2_syntax(text1), "Inför matchstart drog Krantz igång diskussionen.")

        # Därefter
        text2 = "Därefter Siedberg analyserade tabelläget."
        self.assertEqual(Copywriter.enforce_swedish_v2_syntax(text2), "Därefter analyserade Siedberg tabelläget.")

        # I halvtid
        text3 = "I halvtid Dahl manade på gänget."
        self.assertEqual(Copywriter.enforce_swedish_v2_syntax(text3), "I halvtid manade Dahl på gänget.")

        # Efter matchen
        text4 = "Efter matchen Larsson summerade resultatet med ett leende."
        self.assertEqual(Copywriter.enforce_swedish_v2_syntax(text4), "Efter matchen summerade Larsson resultatet med ett leende.")

    def test_semantic_contradiction_auditing(self):
        """Verify contradiction phrases are flipped based on polarity."""
        leader_draft = {
            'top_story': "Efter omgången tvingades ledaren räkna in en tung omgång som skakade om.",
            'headline': "LEDAR-TRIUMF",
            'tagline': "Analys • Toppen",
            'event2_text': "Stabil insats.",
            'event3_text': "Gott resultat.",
            'polarity': 'LEADER_TRIUMPH',
        }
        polished_leader = Copywriter.audit_and_correct(leader_draft)
        self.assertIn("starka omgång", polished_leader['top_story'])
        self.assertNotIn("tung omgång", polished_leader['top_story'])

        faller_draft = {
            'top_story': "Efter raset har spelaren kopplat ett starkt grepp om jumboplatsen.",
            'headline': "TUNGT FALL",
            'tagline': "Analys • Botten",
            'event2_text': "Bakslag.",
            'event3_text': "Stolpe ut.",
            'polarity': 'FALLER_COLLAPSE',
        }
        polished_faller = Copywriter.audit_and_correct(faller_draft)
        self.assertIn("hamnat i ett pressat läge", polished_faller['top_story'])
        self.assertNotIn("kopplat ett starkt grepp", polished_faller['top_story'])

    def test_cached_bold_player_names(self):
        """Verify ensure_bold_player_names works with and without cached_names."""
        text = "Johan Siedberg och Mikael Dahl diskuterade taktik."
        bolded = Copywriter.ensure_bold_player_names(text)
        self.assertIn("**Johan Siedberg**", bolded)
        self.assertIn("**Mikael Dahl**", bolded)

        cached_list = ["Johan Siedberg", "Mikael Dahl"]
        bolded_cached = Copywriter.ensure_bold_player_names(text, cached_names=cached_list)
        self.assertEqual(bolded, bolded_cached)

    def test_lru_cache_on_posture_and_portrait(self):
        """Verify resolve_portrait_url and resolve_posture_path have lru_cache."""
        self.assertTrue(hasattr(resolve_portrait_url, 'cache_info'))
        self.assertTrue(hasattr(resolve_posture_path, 'cache_info'))

        # Call multiple times to verify cache hits
        resolve_portrait_url("Nonexistent Player Test")
        info_before = resolve_portrait_url.cache_info()
        resolve_portrait_url("Nonexistent Player Test")
        info_after = resolve_portrait_url.cache_info()
        self.assertGreater(info_after.hits, info_before.hits)

    def test_polarity_detection_and_wiring(self):
        """Verify detect_narrative_polarity classifies leader and faller descriptions accurately."""
        pol_lead = Journalist.detect_narrative_polarity(
            headline_desc="Johan Siedberg leder ligan och kopplat grepp med 100p",
            headline_type="IS_TOURNAMENT_LEADER",
            primary_nick="Szabo"
        )
        self.assertEqual(pol_lead, 'LEADER_TRIUMPH')

        pol_fall = Journalist.detect_narrative_polarity(
            headline_desc="Mikael Dahl rasade i tabellen efter en tuff period med 0 fullpottar",
            headline_type="FAILED_BANKER",
            primary_nick="Dahl"
        )
        self.assertEqual(pol_fall, 'FALLER_COLLAPSE')

        pol_duel = Journalist.detect_narrative_polarity(
            headline_desc="Stenhård kamp i toppen mellan två herrar",
            headline_type="RIVALRY_DUEL",
            primary_nick="Szabo",
            rival_nick="Dahl"
        )
        self.assertEqual(pol_duel, 'HEAD_TO_HEAD_DUEL')

    def test_centralized_compiler_helpers(self):
        """Verify centralized pool and player nickname resolution."""
        t_toarp = Tournament(name="Toarps Herrklubb Fotbolls-EM 2026")
        self.assertTrue(is_toarps_pool(t_toarp))

        t_comm = Tournament(name="Allmänna EM-Tipset 2026")
        self.assertFalse(is_toarps_pool(t_comm))

        u = User(first_name="Johan", last_name="Siedberg", email="johan@example.com")
        nick_toarp = get_player_nick_or_name(u, is_toarp=True)
        self.assertEqual(nick_toarp, "Szabo")

        nick_comm = get_player_nick_or_name(u, is_toarp=False)
        self.assertEqual(nick_comm, "Johan")

    def test_tournament_finale_generation(self):
        """Verify draft_tournament_finale_edition creates the complete 5-section Grand Finale."""
        admin = User.objects.create_superuser(username="test_admin", email="admin@example.com", password="password")
        t = Tournament.objects.create(name="Toarps Herrklubb Final Test", admin=admin)
        u1 = User.objects.create_user(username="u1", first_name="Johan", last_name="Siedberg")
        u2 = User.objects.create_user(username="u2", first_name="Mikael", last_name="Dahl")
        u3 = User.objects.create_user(username="u3", first_name="Andreas", last_name="Larsson")
        t.players.add(u1, u2, u3)

        # Create a match and predictions so leaderboard has points
        m = Match.objects.create(
            tournament=t,
            home_team="Spanien",
            away_team="England",
            home_goals=2,
            away_goals=1,
            is_finished=True
        )
        MatchPrediction.objects.create(player=u1, match=m, home_goals=2, away_goals=1)
        MatchPrediction.objects.create(player=u2, match=m, home_goals=1, away_goals=0)
        MatchPrediction.objects.create(player=u3, match=m, home_goals=0, away_goals=2)

        finale_gazette = SpecialEditionReporter.draft_tournament_finale_edition(t, round_num=999)
        self.assertIsNotNone(finale_gazette)
        self.assertTrue(finale_gazette.is_special_edition)
        self.assertEqual(finale_gazette.content_format, 'TOURNAMENT_FINALE')
        self.assertIn("GULDETS VÄG", finale_gazette.headline)
        
        # Verify 5 mandatory sections exist in content
        self.assertIn("Podiets Slutstrid", finale_gazette.content)
        self.assertIn("Träsleven & Skammens Bokslut", finale_gazette.content)
        self.assertIn("Skuggpriserna", finale_gazette.content)
        self.assertIn("Almanackans Slutdom", finale_gazette.content)
        self.assertIn("Det Sista Slutbetyget", finale_gazette.content)
