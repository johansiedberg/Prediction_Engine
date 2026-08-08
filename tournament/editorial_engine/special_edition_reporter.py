"""
special_edition_reporter.py
---------------------------
Reporter and narrative generation engine for Gazzetta Special Editions.

Generates 4 custom sections for each of the 9 Milestone Rounds:
- HEADLINE 1: Top contenders, creating rivalry & banter between players.
- HEADLINE 2: Results that stand out (impactful scorelines, exact full-score hits).
- HEADLINE 3: Worst performing in period (biggest rank fallers & tough round analysis).
- ANALYSIS: AI Predictions of development, upcoming opportunities & threats.
"""

from django.db.models import Count, Q
from tournament.models import (
    Tournament, Match, MatchPrediction, DailyGazette, RoundLeaderboardSnapshot, TournamentSubmission
)
from tournament.editorial_engine.journalist import BEHAVIOR_DESCRIPTIONS, Journalist

MILESTONE_ROUNDS = {
    1: {'name': 'Tips Verifierade', 'code': 'VERIFIED'},
    2: {'name': 'Gruppomgång 1 Spelad', 'code': 'GROUP_1'},
    3: {'name': 'Gruppomgång 2 Spelad', 'code': 'GROUP_2'},
    4: {'name': 'Gruppomgång 3 Spelad', 'code': 'GROUP_3'},
    5: {'name': 'Åttondelsfinaler Spelade', 'code': 'R16'},
    6: {'name': 'Kvartsfinaler Spelade', 'code': 'QF'},
    7: {'name': 'Semfinaler Spelade', 'code': 'SF'},
    8: {'name': 'Bronsmatch Spelad', 'code': 'BRONZE'},
    9: {'name': 'Final Spelad', 'code': 'FINAL'},
}


class SpecialEditionReporter:

    @classmethod
    def get_player_name(cls, user) -> str:
        """Helper to get player display name."""
        if not user:
            return "Spelare"
        return f"{user.first_name} {user.last_name}".strip() if user.first_name else user.username

    @classmethod
    def calculate_leaderboard(cls, tournament: Tournament) -> list:
        """Computes current leaderboard list with player info, rank, points, and exact score hits."""
        from tournament.views import calc_pred_points_detail
        players = list(tournament.players.all())
        point_system = getattr(tournament, 'point_system', None)
        
        leaderboard = []
        for p in players:
            p_preds = MatchPrediction.objects.filter(player=p, match__tournament=tournament, match__is_finished=True)
            pts = 0
            exact_count = 0
            
            for pred in p_preds:
                m = pred.match
                detail = calc_pred_points_detail(pred, m, point_system)
                pts += detail.get('pts_total', 0)
                if m.home_goals is not None and m.away_goals is not None:
                    if pred.home_goals == m.home_goals and pred.away_goals == m.away_goals:
                        exact_count += 1

            leaderboard.append({
                'user': p,
                'name': cls.get_player_name(p),
                'points': pts,
                'exact_count': exact_count,
            })

        leaderboard.sort(key=lambda x: (x['points'], x['exact_count']), reverse=True)
        for idx, entry in enumerate(leaderboard, 1):
            entry['rank'] = idx

        return leaderboard

    @classmethod
    def snapshot_leaderboard(cls, tournament: Tournament, round_num: int, round_name: str) -> list:
        """Saves current leaderboard state to RoundLeaderboardSnapshot for historical comparison."""
        lb = cls.calculate_leaderboard(tournament)
        snapshots = []
        for entry in lb:
            snap, _ = RoundLeaderboardSnapshot.objects.update_or_create(
                tournament=tournament,
                round_number=round_num,
                player=entry['user'],
                defaults={
                    'round_name': round_name,
                    'rank': entry['rank'],
                    'points': entry['points'],
                    'exact_scores_count': entry['exact_count'],
                }
            )
            snapshots.append(snap)
        return lb

    @classmethod
    def analyze_round_changes(cls, tournament: Tournament, round_num: int, current_lb: list) -> dict:
        """Compares current round leaderboard vs previous round snapshot to find climbers and fallers."""
        prev_round_num = round_num - 1
        prev_snapshots = {
            s.player_id: s for s in RoundLeaderboardSnapshot.objects.filter(tournament=tournament, round_number=prev_round_num)
        }

        changes = []
        for entry in current_lb:
            p_id = entry['user'].id
            prev = prev_snapshots.get(p_id)
            if prev:
                rank_change = prev.rank - entry['rank'] # Positive = climbed, Negative = fell
                pts_gained = entry['points'] - prev.points
            else:
                rank_change = 0
                pts_gained = entry['points']

            changes.append({
                'user': entry['user'],
                'name': entry['name'],
                'current_rank': entry['rank'],
                'current_pts': entry['points'],
                'rank_change': rank_change,
                'pts_gained': pts_gained,
                'exact_count': entry['exact_count'],
            })

        climbers = sorted(changes, key=lambda x: (x['rank_change'], x['pts_gained']), reverse=True)
        fallers = sorted(changes, key=lambda x: (x['rank_change'], x['pts_gained']))

        return {
            'changes': changes,
            'top_climber': climbers[0] if climbers and climbers[0]['rank_change'] > 0 else None,
            'top_faller': fallers[0] if fallers and fallers[0]['rank_change'] < 0 else (fallers[0] if fallers else None),
        }

    @classmethod
    def draft_special_edition(cls, tournament: Tournament, round_num: int) -> DailyGazette:
        """Generates a complete Special Edition DailyGazette record for a given round milestone."""
        round_info = MILESTONE_ROUNDS.get(round_num, {'name': f'Omgång {round_num}', 'code': f'ROUND_{round_num}'})
        round_name = round_info['name']

        # 1. Snapshot current leaderboard
        current_lb = cls.snapshot_leaderboard(tournament, round_num, round_name)
        analysis = cls.analyze_round_changes(tournament, round_num, current_lb)

        # Identify key players
        leader = current_lb[0] if current_lb else {'name': 'Tipparen', 'points': 0}
        runner_up = current_lb[1] if len(current_lb) > 1 else None
        third_place = current_lb[2] if len(current_lb) > 2 else None
        top_faller = analysis['top_faller'] or (current_lb[-1] if current_lb else {'name': 'Jumbo'})

        leader_name = leader['name']
        runner_name = runner_up['name'] if runner_up else "Utmanaren"

        # Behavior descriptions
        leader_behavior = BEHAVIOR_DESCRIPTIONS.get(leader_name, "granskade sina tabeller med absolut lugn och självförtroende")
        runner_behavior = BEHAVIOR_DESCRIPTIONS.get(runner_name, "pressade på med aggressiva taktiska drag för att ta över förstaplatsen")

        # 2. Draft HEADLINE 1: Top Contenders & Rivalry
        pts_diff = (leader['points'] - runner_up['points']) if runner_up else 0
        if round_num == 10:
            headline_1_title = f"SLUTMAGASIN: {leader_name.upper()} KRONAS TILL SLUTGILTIG MÄSTARE I {tournament.name.upper()}!"
            headline_1_body = (
                f"Efter en episk resa fylld av dramatiska drabbningar och taktiska mästerdrag har {tournament.name} nått sin absoluta slutpunkt! "
                f"{leader_name} står stolt som den slutgiltige mästaren med magiska {leader['points']} poäng i totalkalkylen. "
                f"Under hela turneringen {leader_behavior}. "
                f"På andra plats kämpar {runner_name} tappert på {runner_up['points'] if runner_up else 0} poäng, medan {third_place['name'] if third_place else 'Tipparen'} säkrar bronsplatsen på {third_place['points'] if third_place else 0} poäng. "
                f"En historisk finalsummering där mästaren lyfts upp på tronen av alla medtävlare!"
            )
        else:
            headline_1_title = f"SPECIALMAGASIN: {leader_name} TOFFLAR TABELLTOPPEN EFTER {round_name.upper()}!"
            headline_1_body = (
                f"Den intensiva drabbningen kring förstaplatsen i {tournament.name} har nått ett nytt kapitel. "
                f"{leader_name} står stolt överst på {leader['points']} poäng efter att ha levererat en knivskarp insats. "
                f"Under perioden {leader_behavior}. "
                f"Tätt bakom lurar dock {runner_name} på {runner_up['points'] if runner_up else 0} poäng ({pts_diff}p bakom), som inte sparade på krutet då han {runner_behavior}. "
                f"Rivaliteten mellan {leader_name} och {runner_name} skapar eldfängd stämning i ligatabellen då båda vägrar ge vika en millimeter."
            )

        # 3. Draft HEADLINE 2: Results That Stand Out & Full-Score Games
        most_fullpotts = max(current_lb, key=lambda x: x['exact_count']) if current_lb else {'name': 'Ingen', 'exact_count': 0}
        if round_num == 10:
            headline_2_title = f"TURNERINGENS FULLPOTTEKSPLOISION: {most_fullpotts['name'].upper()} KRONAS TILL EXAKTHETSKUNG!"
            headline_2_body = (
                f"När hela turneringens alla matcher summeras står det klart att exaktheten varit avgörande. "
                f"Turneringens vassaste spikare blev {most_fullpotts['name']}, som mäktade med otroliga {most_fullpotts['exact_count']} exakta fullpottar under mästerskapet! "
                f"Dessa magiska fullträffar blev tungan på vågen i tabellstriden och belönade den modigaste tipparen med ovärderliga poäng."
            )
        else:
            headline_2_title = f"DRAMATISKA RESULTAT & FULLPOTTEKSPLOISION: {most_fullpotts['name']} DOMINERAR SPIKARNA!"
            headline_2_body = (
                f"Omgången har bjudit på flera anmärkningsvärda vändningar och taktiska krascher. "
                f"Det mest framstående facit stod {most_fullpotts['name']} för, som lyckats spika hela {most_fullpotts['exact_count']} exakta fullpottar i turneringen hittills! "
                f"De oväntade matchresultaten under {round_name} ställde kalkylerna på ända för flera tippare och belönade dem som vågade gå emot strömmen."
            )

        # 4. Draft HEADLINE 3: Worst Performing in Period & Fallers
        faller_name = top_faller['name']
        faller_behavior = BEHAVIOR_DESCRIPTIONS.get(faller_name, "sökte febrilt efter förklaringar till omgångens tunga bakslag")
        if round_num == 10:
            headline_3_title = f"HISTORISKA VÄNDNINGAR & TUNG REANSCHLUST FÖR {faller_name.upper()}!"
            headline_3_body = (
                f"Ingen turnering är komplett utan sina dramatiska fall och tunga bakslag. "
                f"{faller_name} kämpade hårt genom hela mästerskapet och {faller_behavior}. "
                f"Med en slutplacering som #{top_faller.get('current_rank', '-')} i tabellen är revanschlusten enorm inför nästa stora mästerskap – här laddas det om direkt!"
            )
        else:
            headline_3_title = f"TUNGT BAKSLAG FÖR {faller_name.upper()}: OMSKAKANDE FALL I TABELLEN!"
            headline_3_body = (
                f"{round_name} blev en prövningens omgång för {faller_name}, som drabbades av flera tuffa stolpe-ut-resultat. "
                f"{faller_name} {faller_behavior}. "
                f"Med en placering som #{top_faller.get('current_rank', '-')} krävs det nu en omedelbar taktisk uppryckning och modiga spikar inför kommande drabbningar om kontakten med toppen inte ska gå förlorad."
            )

        # 5. Draft ANALYSIS: AI Predictions & Future Outlook
        if round_num == 10:
            analysis_title = f"AI-LEGACY REPORT: HALL OF FAME & ETERIG GLANS"
            analysis_body = (
                f"Vår matematiska editorial-modell har slutfört den sista analysen av {tournament.name}. "
                f"Mästaren {leader_name} skrivs in i gängets Hall of Fame med högsta betyg i både taktisk precision och helgarderingar. "
                f"Vi tackar alla deltagare för en oerhört underhållande och eldfängd tippningsturnering. Vi ses i nästa mästerskap!"
            )
        else:
            analysis_title = f"AI-ANALYS & FRAMTIDA UTSIKTER: MÖJLIGHETER OCH HOT INFÖR NÄSTA ETAPP"
            analysis_body = (
                f"Vår matematiska editorial-modell har simulerat återstående spelträd i {tournament.name}. "
                f"Toppstriden mellan {leader_name} och {runner_name} bedöms fortfarande vara helt öppen, där marginalerna är rakblads-tunna. "
                f"Möjligheter uppstår för jaga-klungan ifall ledarna blir för försiktiga med sina helgarderingar, medan det största hotet för {faller_name} är ytterligare kryssresultat som spräcker målskillnads-beräkningarna. "
                f"Spänningen inför nästa fas i turneringen är nådd till sin absolut högsta punkt!"
            )

        # 6. Select 3 Featured Players for Art Director
        featured_players = [
            {'name': leader_name, 'role': 'LEADER', 'posture': 'Knee'},
            {'name': runner_name, 'role': 'RUNNER_UP', 'posture': 'Crossed-Arms'},
            {'name': faller_name, 'role': 'FALLER', 'posture': 'Point-Up'},
        ]

        full_article_content = (
            f"### {headline_1_title}\n\n{headline_1_body}\n\n"
            f"### {headline_2_title}\n\n{headline_2_body}\n\n"
            f"### {headline_3_title}\n\n{headline_3_body}\n\n"
            f"### {analysis_title}\n\n{analysis_body}"
        )

        from django.utils import timezone

        pub_date = timezone.now().date()

        gazette, _ = DailyGazette.objects.update_or_create(
            tournament=tournament,
            round_number=round_num,
            defaults={
                'publish_date': pub_date,
                'is_special_edition': True,
                'round_name': round_name,
                'content_format': 'SPECIAL_EDITION',
                'headline': headline_1_title,
                'tagline': f"Specialmagasin efter {round_name} - Toppstrid, tabellkast & AI-analys",
                'content': full_article_content,
                'headline_top_contenders': headline_1_body,
                'headline_standout_results': headline_2_body,
                'headline_worst_performers': headline_3_body,
                'analysis_outlook': analysis_body,
                'featured_players_json': featured_players,
                'primary_posture': 'Knee',
                'rival_posture': 'Crossed-Arms',
                'tone_used': 'Magasin & Taktisk Analys',
            }
        )

        return gazette
