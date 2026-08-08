import re
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Tournament(models.Model):
    name = models.CharField(max_length=200)
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name='managed_tournaments')
    players = models.ManyToManyField(User, related_name='participating_tournaments', blank=True)
    is_active = models.BooleanField(default=True)
    is_actual_knockout_open = models.BooleanField(default=False, help_text="Open predictions for the actual knockout bracket after group stage ends")
    
    # New branding fields
    icon = models.ImageField(upload_to='tournament/icons/', blank=True, null=True, help_text="Tournament emblem/favicon")
    backdrop = models.ImageField(upload_to='tournament/backdrops/', blank=True, null=True, help_text="Header backdrop background")

    def __str__(self):
        return self.name


class PointSystem(models.Model):
    tournament = models.OneToOneField(Tournament, on_delete=models.CASCADE, related_name='point_system')
    
    match_correct_goals_per_team = models.IntegerField(default=3)
    match_correct_total_goals = models.IntegerField(default=1)
    match_correct_1x2 = models.IntegerField(default=3)
    
    group_correct_placement = models.IntegerField(default=2)
    group_correct_points = models.IntegerField(default=1)
    group_correct_goals_scored = models.IntegerField(default=1)
    group_correct_goals_conceded = models.IntegerField(default=1)
    group_correct_goal_diff = models.IntegerField(default=1)
    
    knockout_qualified_third = models.IntegerField(default=2)
    knockout_round_of_16 = models.IntegerField(default=3)
    knockout_quarterfinal = models.IntegerField(default=4)
    knockout_semifinal = models.IntegerField(default=5)
    knockout_bronze_match = models.IntegerField(default=0)
    knockout_final = models.IntegerField(default=8)

    def __str__(self):
        return f"Point System for {self.tournament.name}"


class Group(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='tournament_groups')
    name = models.CharField(max_length=50)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return f"{self.name} ({self.tournament.name})"

    def get_standings(self, user_predictions=None):
        """Calculates live or predicted group table standings."""
        teams = self.teams.all()
        standings = {team.name: {
            'team': team,
            'played': 0,
            'won': 0,
            'drawn': 0,
            'lost': 0,
            'gf': 0,
            'ga': 0,
            'gd': 0,
            'points': 0
        } for team in teams}

        for match in self.matches.all():
            ht, at = match.home_team, match.away_team
            hg, ag = None, None

            if user_predictions and match.id in user_predictions:
                pred = user_predictions[match.id]
                if pred and pred.home_goals is not None and pred.away_goals is not None:
                    hg, ag = pred.home_goals, pred.away_goals
            elif match.home_goals is not None and match.away_goals is not None:
                hg, ag = match.home_goals, match.away_goals

            if hg is None or ag is None:
                continue

            if ht in standings:
                standings[ht]['played'] += 1
                standings[ht]['gf'] += hg
                standings[ht]['ga'] += ag

            if at in standings:
                standings[at]['played'] += 1
                standings[at]['gf'] += ag
                standings[at]['ga'] += hg

            if ht in standings and at in standings:
                if hg > ag:
                    standings[ht]['won'] += 1
                    standings[ht]['points'] += 3
                    standings[at]['lost'] += 1
                elif hg < ag:
                    standings[at]['won'] += 1
                    standings[at]['points'] += 3
                    standings[ht]['lost'] += 1
                else:
                    standings[ht]['drawn'] += 1
                    standings[ht]['points'] += 1
                    standings[at]['drawn'] += 1
                    standings[at]['points'] += 1

        for data in standings.values():
            data['gd'] = data['gf'] - data['ga']

        sorted_standings = sorted(
            standings.values(),
            key=lambda x: (x['points'], x['gd'], x['gf'], x['won']),
            reverse=True
        )
        return sorted_standings


COUNTRY_CODE_MAP = {
    # English names
    'sweden': 'se',
    'england': 'gb-eng',
    'united kingdom': 'gb',
    'great britain': 'gb',
    'wales': 'gb-wls',
    'scotland': 'gb-sct',
    'northern ireland': 'gb-nir',
    'france': 'fr',
    'germany': 'de',
    'spain': 'es',
    'italy': 'it',
    'portugal': 'pt',
    'netherlands': 'nl',
    'belgium': 'be',
    'denmark': 'dk',
    'norway': 'no',
    'finland': 'fi',
    'iceland': 'is',
    'poland': 'pl',
    'croatia': 'hr',
    'ukraine': 'ua',
    'switzerland': 'ch',
    'austria': 'at',
    'hungary': 'hu',
    'czech republic': 'cz',
    'czechia': 'cz',
    'slovakia': 'sk',
    'serbia': 'rs',
    'romania': 'ro',
    'turkey': 'tr',
    'türkiye': 'tr',
    'greece': 'gr',
    'albania': 'al',
    'slovenia': 'si',
    'georgia': 'ge',
    'brazil': 'br',
    'argentina': 'ar',
    'uruguay': 'uy',
    'colombia': 'co',
    'chile': 'cl',
    'mexico': 'mx',
    'united states': 'us',
    'usa': 'us',
    'canada': 'ca',
    'japan': 'jp',
    'south korea': 'kr',
    'australia': 'au',
    'morocco': 'ma',
    'senegal': 'sn',
    'cameroon': 'cm',
    'ghana': 'gh',
    'nigeria': 'ng',
    'bulgaria': 'bg',
    'republic of ireland': 'ie',
    'ireland': 'ie',
    'montenegro': 'me',
    'malta': 'mt',
    'bosnia and herzegovina': 'ba',
    'bosnia': 'ba',
    'north macedonia': 'mk',
    'macedonia': 'mk',
    'kosovo': 'xk',
    'luxembourg': 'lu',
    'armenia': 'am',
    'azerbaijan': 'az',
    'cyprus': 'cy',
    'estonia': 'ee',
    'faroe islands': 'fo',
    'latvia': 'lv',
    'lithuania': 'lt',
    'moldova': 'md',
    'kazakhstan': 'kz',
    'andorra': 'ad',
    'gibraltar': 'gi',
    'liechtenstein': 'li',
    'san marino': 'sm',
    'belarus': 'by',

    # Swedish names
    'sverige': 'se',
    'tyskland': 'de',
    'frankrike': 'fr',
    'spanien': 'es',
    'italien': 'it',
    'nederländerna': 'nl',
    'belgien': 'be',
    'österrike': 'at',
    'schweiz': 'ch',
    'tjeckien': 'cz',
    'slovakien': 'sk',
    'kroatien': 'hr',
    'nordirland': 'gb-nir',
    'skottland': 'gb-sct',
    'turkiet': 'tr',
    'grekland': 'gr',
    'ungern': 'hu',
    'irland': 'ie',
    'bulgarien': 'bg',
    'norge': 'no',
    'danmark': 'dk',
    'finland': 'fi',
    'island': 'is',
    'polen': 'pl',
    'serbien': 'rs',
    'bosnien och hercegovina': 'ba',
    'bosnien': 'ba',
    'nordmakedonien': 'mk',
    'luxemburg': 'lu',
    'armenien': 'am',
    'azerbajdzjan': 'az',
    'cypern': 'cy',
    'estland': 'ee',
    'färöarna': 'fo',
    'lettland': 'lv',
    'litauen': 'lt',
    'moldavien': 'md',
    'kazakstan': 'kz',
}



class Team(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='teams')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, null=True, blank=True, related_name='teams')
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10, blank=True, null=True, help_text="Auto-detected from name if left blank")

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.code and self.name:
            clean_name = self.name.strip().lower()
            if clean_name in COUNTRY_CODE_MAP:
                self.code = COUNTRY_CODE_MAP[clean_name]
        super().save(*args, **kwargs)

    @property
    def flag_url(self):
        if self.code:
            return f"https://flagcdn.com/w40/{self.code.lower()}.png"
        return ""


class KnockoutStage(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='knockout_stages')
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return f"{self.name} ({self.tournament.name})"


class Match(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='matches')
    match_number = models.PositiveIntegerField(blank=True, null=True)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='matches', blank=True, null=True)
    stage = models.ForeignKey(KnockoutStage, on_delete=models.CASCADE, related_name='matches', blank=True, null=True)
    date_time = models.DateTimeField(blank=True, null=True)
    home_team = models.CharField(max_length=100)
    away_team = models.CharField(max_length=100)
    home_goals = models.PositiveIntegerField(null=True, blank=True)
    away_goals = models.PositiveIntegerField(null=True, blank=True)
    is_finished = models.BooleanField(default=False)
    box_score_data = models.JSONField(default=dict, blank=True, help_text="JSON payload containing goals, card events, and period timestamps")

    class Meta:
        ordering = ['match_number']

    def __str__(self):
        home_info = self.get_home_team_info()
        away_info = self.get_away_team_info()
        if self.match_number:
            return f"Match {self.match_number}: {home_info['display_name']} vs {away_info['display_name']}"
        return f"{home_info['display_name']} vs {away_info['display_name']}"

    def get_home_team_info(self, user_predictions=None):
        return self._resolve_team(self.home_team, user_predictions)

    def get_away_team_info(self, user_predictions=None):
        return self._resolve_team(self.away_team, user_predictions)

    def _resolve_team(self, team_str, user_predictions=None):
        if not team_str:
            return {'name': '-', 'code': '', 'flag_url': '', 'display_name': '-'}
        
        team_str_clean = team_str.strip()
        
        # 1. Match Winner/Loser knockout dependencies (e.g. "Winner Match 37", "Loser Match 49")
        m_kw = re.match(r'^(Winner|Loser|Vinnare|Förlorare)\s+(?:Match\s+)?(\d+)$', team_str_clean, re.IGNORECASE)
        if m_kw:
            role, match_num = m_kw.group(1).lower(), int(m_kw.group(2))
            ref_match = self.tournament.matches.filter(match_number=match_num).first()
            if ref_match:
                winner_info = None
                loser_info = None

                if user_predictions and ref_match.id in user_predictions:
                    pred = user_predictions[ref_match.id]
                    if pred and pred.home_goals is not None and pred.away_goals is not None:
                        h_info = ref_match.get_home_team_info(user_predictions)
                        a_info = ref_match.get_away_team_info(user_predictions)
                        if pred.home_goals > pred.away_goals:
                            winner_info, loser_info = h_info, a_info
                        elif pred.away_goals > pred.home_goals:
                            winner_info, loser_info = a_info, h_info
                        else:
                            if pred.penalty_winner == a_info['name']:
                                winner_info, loser_info = a_info, h_info
                            else:
                                winner_info, loser_info = h_info, a_info

                if not winner_info and ref_match.is_finished and ref_match.home_goals is not None and ref_match.away_goals is not None:
                    if ref_match.home_goals > ref_match.away_goals:
                        winner_info = ref_match.get_home_team_info()
                        loser_info = ref_match.get_away_team_info()
                    elif ref_match.away_goals > ref_match.home_goals:
                        winner_info = ref_match.get_away_team_info()
                        loser_info = ref_match.get_home_team_info()

                target_info = winner_info if role in ('winner', 'vinnare') else loser_info
                if target_info and target_info['name'] and target_info['name'] != '-':
                    return {
                        'name': target_info['name'],
                        'code': target_info['code'],
                        'flag_url': target_info['flag_url'],
                        'display_name': f"{target_info['name']} ({team_str_clean})"
                    }

        # 2. Match Group placeholder codes (e.g. "A1", "B2", "L5")
        m = re.match(r'^([A-L])([1-5])$', team_str_clean, re.IGNORECASE)

        if m:
            group_code, idx = m.group(1).upper(), int(m.group(2))
            group = self.tournament.tournament_groups.filter(name__icontains=group_code).first()
            if group:
                standings = group.get_standings(user_predictions)
                if 0 <= idx - 1 < len(standings):
                    t = standings[idx - 1]['team']
                    return {
                        'name': t.name,
                        'code': t.code,
                        'flag_url': t.flag_url,
                        'display_name': f"{t.name} ({team_str_clean})"
                    }
                else:
                    teams = list(group.teams.all())
                    if 0 <= idx - 1 < len(teams):
                        t = teams[idx - 1]
                        return {
                            'name': t.name,
                            'code': t.code,
                            'flag_url': t.flag_url,
                            'display_name': f"{t.name} ({team_str_clean})"
                        }

        # 3. Third-place combination placeholders (e.g. "3DEF", "3ADEF", "3ABCD", "3ABC", "DEF3")
        m_third = re.match(r'^(3?([A-F]{2,4})3?)$', team_str_clean, re.IGNORECASE)
        if m_third:
            group_letters = m_third.group(2).upper()
            thirds = []
            for g_let in group_letters:
                grp = self.tournament.tournament_groups.filter(name__icontains=g_let).first()
                if grp:
                    st = grp.get_standings(user_predictions)
                    if len(st) >= 3:
                        thirds.append(st[2])
            if thirds:
                thirds.sort(key=lambda x: (x['points'], x['gd'], x['gf'], x['won']), reverse=True)
                t = thirds[0]['team']
                return {
                    'name': t.name,
                    'code': t.code,
                    'flag_url': t.flag_url,
                    'display_name': f"{t.name} ({team_str_clean})"
                }

        # 3. Direct Team model match in tournament
        team = self.tournament.teams.filter(name__iexact=team_str_clean).first()
        if team:
            return {
                'name': team.name,
                'code': team.code,
                'flag_url': team.flag_url,
                'display_name': team.name
            }
        
        # 4. Fallback using country code map
        clean_key = team_str_clean.lower()
        if clean_key in COUNTRY_CODE_MAP:
            code = COUNTRY_CODE_MAP[clean_key]
            return {
                'name': team_str_clean,
                'code': code,
                'flag_url': f"https://flagcdn.com/w40/{code}.png",
                'display_name': team_str_clean
            }

        return {
            'name': team_str_clean,
            'code': '',
            'flag_url': '',
            'display_name': team_str_clean
        }




class MatchPrediction(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='predictions')
    player = models.ForeignKey(User, on_delete=models.CASCADE, related_name='match_predictions')
    PHASE_CHOICES = (
        ('INITIAL_BRACKET', 'Initial Pre-Tournament Bracket'),
        ('ACTUAL_KNOCKOUT', 'Actual Knockout Stage Phase'),
    )
    prediction_phase = models.CharField(max_length=20, choices=PHASE_CHOICES, default='INITIAL_BRACKET', help_text="Phase when prediction was submitted")
    home_goals = models.PositiveIntegerField(default=0)
    away_goals = models.PositiveIntegerField(default=0)
    penalty_winner = models.CharField(max_length=100, blank=True, null=True, help_text="Tiebreaker winner team name")

    def __str__(self):
        return f"{self.player.username} - Match {self.match.match_number}"


class Sidebet(models.Model):
    QUESTION_TYPES = (
        ('TEAM', 'Välj lag (dropdown)'),
        ('TEXT', 'Fritext (t.ex. spelarnamn)'),
    )

    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='sidebets')
    question = models.CharField(max_length=255, verbose_name="Fråga")
    points = models.PositiveIntegerField(default=5, verbose_name="Poäng för rätt svar")
    question_type = models.CharField(max_length=10, choices=QUESTION_TYPES, default='TEXT', verbose_name="Frågetyp")
    correct_answers = models.TextField(blank=True, null=True, verbose_name="Rätt svar", help_text="Anges av admin. Separera flera giltiga/oavgjorda svar med kommatecken (t.ex. Mbappé, Isak, Haaland)")

    def get_correct_answers_list(self):
        if not self.correct_answers:
            return []
        return [a.strip().lower() for a in self.correct_answers.split(',') if a.strip()]

    def is_answer_correct(self, user_answer_str):
        if not user_answer_str or not self.correct_answers:
            return False
        user_clean = user_answer_str.strip().lower()
        valid_answers = self.get_correct_answers_list()
        return user_clean in valid_answers

    class Meta:
        verbose_name = "Bonusfråga"
        verbose_name_plural = "Bonusfrågor"

    def __str__(self):
        return f"{self.question} ({self.points}p)"


class SidebetAnswer(models.Model):
    sidebet = models.ForeignKey(Sidebet, on_delete=models.CASCADE, related_name='answers')
    player = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sidebet_answers')
    answer = models.CharField(max_length=255, verbose_name="Svar")

    class Meta:
        unique_together = ('sidebet', 'player')
        verbose_name = "Spelarens bonussvar"
        verbose_name_plural = "Spelarnas bonussvar"

    def __str__(self):
        return f"{self.player.username} - {self.sidebet.question}: {self.answer}"


class TournamentSubmission(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='submissions')
    player = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tournament_submissions')
    is_saved = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('tournament', 'player')

    def __str__(self):
        status = "Verified" if self.is_verified else ("Saved" if self.is_saved else "Pending")
        return f"{self.player.username} - {self.tournament.name} [{status}]"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True, verbose_name="Profilbild / Avatar")
    last_selected_tournament = models.ForeignKey(Tournament, on_delete=models.SET_NULL, null=True, blank=True, related_name='selected_by_profiles')
    is_herrklubb_member = models.BooleanField(default=False, help_text="True if user is one of the 11 original Herrklubben members")

    def get_avatar_url(self):
        if self.avatar and hasattr(self.avatar, 'url'):
            return self.avatar.url
        return None

    def __str__(self):
        return f"Profil för {self.user.username} (Herrklubb: {self.is_herrklubb_member})"


from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver


@receiver(post_save, sender=User)
def auto_create_user_profile(sender, instance, created, **kwargs):
    UserProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def auto_add_user_to_active_tournaments(sender, instance, created, **kwargs):
    """Automatically enroll new players into active tournaments and create submission records."""
    if created:
        active_tournaments = Tournament.objects.filter(is_active=True)
        for t in active_tournaments:
            t.players.add(instance)
            TournamentSubmission.objects.get_or_create(tournament=t, player=instance)


@receiver(m2m_changed, sender=Tournament.players.through)
def auto_create_submission_for_tournament_players(sender, instance, action, pk_set, **kwargs):
    """Ensure TournamentSubmission is created when players are added to a tournament."""
    if action == "post_add":
        for player_id in pk_set:
            TournamentSubmission.objects.get_or_create(
                tournament=instance,
                player_id=player_id
            )


# --- Editorial Engine Models ---

class StaticInsight(models.Model):
    CATEGORY_CHOICES = (
        ('CONSENSUS_ALERT', 'Konsensusvarning'),
        ('CERTIFIED_MADNESS', 'Verifierad Galenskap'),
        ('LONE_WOLF', 'Ensam Varg'),
        ('DELUSION_INDEX', 'Övermodsindex'),
        ('GENERAL', 'Allmän Insikt'),
    )

    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='static_insights', null=True, blank=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='GENERAL')
    player_name = models.CharField(max_length=100, blank=True, null=True)
    data_point = models.TextField(help_text="Factual summary, e.g., '12 of 13 players have Spain winning Group C.'")
    llm_roast = models.TextField(help_text="LLM-generated Swedish joke/commentary")
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Static Insight (Almanac)"
        verbose_name_plural = "Static Insights (Almanac)"

    def __str__(self):
        return f"[{self.category}] {self.player_name or 'General'}: {self.data_point[:40]}"


class InsightEvent(models.Model):
    TYPE_CHOICES = (
        ('ELIMINATION', 'Utslagning'),
        ('BIG_MOVER', 'Klassklättrare / Raskt Fall'),
        ('PREDICTION_AGED_POORLY', 'Tips Som Åldrades Dåligt'),
        ('FAILED_BANKER', 'Spikkrasch'),
        ('OUTLIER_VICTORY', 'Soloseger'),
        ('GENERAL_DRAMA', 'Omgångsdrama'),
    )

    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='insight_events', null=True, blank=True)
    type = models.CharField(max_length=50, choices=TYPE_CHOICES, default='GENERAL_DRAMA')
    player_name = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(help_text="Event details, e.g., 'Lucas dropped from 1st to 5th place.'")
    importance_score = models.IntegerField(default=50, help_text="Score from 0-100 indicating narrative importance")
    matchday_reference = models.IntegerField(null=True, blank=True, help_text="Matchday number or reference")
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ['-importance_score', '-created_at']
        verbose_name = "Insight Event"
        verbose_name_plural = "Insight Events"

    def __str__(self):
        return f"[{self.type}] {self.player_name or 'General'} (Score: {self.importance_score})"


class StorylineMemory(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='storyline_memories', null=True, blank=True)
    player_name = models.CharField(max_length=100)
    narrative = models.TextField(help_text="Ongoing story arc, e.g., 'Lucas heavily backed Belgium, but they failed.'")
    last_updated = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-last_updated']
        verbose_name = "Storyline Memory"
        verbose_name_plural = "Storyline Memories"

    def __str__(self):
        return f"{self.player_name}: {self.narrative[:40]}"


class DailyGazette(models.Model):
    FORMAT_CHOICES = (
        ('STANDARD_COLUMN', 'Standardkrönika'),
        ('WINNERS_LOSERS', 'Vinnare & Förlorare'),
        ('INTERVIEW', 'Exklusiv Intervju'),
        ('PUB_QUOTES', 'Citat från Puben'),
        ('SPECIAL_EDITION', 'Specialutgåva Omgång'),
    )

    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='daily_gazettes', null=True, blank=True)
    publish_date = models.DateField(db_index=True)
    headline = models.CharField(max_length=255, help_text="Bold headline in Swedish")
    tagline = models.CharField(max_length=255, help_text="Sub-headline / hook in Swedish")
    image_url = models.CharField(max_length=500, blank=True, null=True, help_text="Path or URL to generated visual asset")
    image_prompt = models.TextField(blank=True, null=True, help_text="Audit log of image prompt used")
    content_format = models.CharField(max_length=50, choices=FORMAT_CHOICES, default='STANDARD_COLUMN')
    content = models.TextField(help_text="Full daily article in Swedish")
    tone_used = models.CharField(max_length=100, blank=True, null=True, help_text="e.g. Dry Scandinavian, Tabloid, Pub Quotes")
    structured_data = models.JSONField(default=dict, blank=True, help_text="Structured layout payload: top_story, events_grid, day_summary")
    primary_posture = models.CharField(max_length=50, blank=True, null=True, help_text="Posture key for primary avatar, e.g. 'Knee'")
    rival_posture = models.CharField(max_length=50, blank=True, null=True, help_text="Posture key for rival avatar, always 'Rival-left'")
    
    # Special Edition fields for 9 Milestone Rounds
    is_special_edition = models.BooleanField(default=False)
    round_number = models.IntegerField(null=True, blank=True, help_text="Round milestone 1 to 9")
    round_name = models.CharField(max_length=100, blank=True, null=True)
    headline_top_contenders = models.TextField(blank=True, null=True, help_text="HEADLINE 1: Top contenders, rivalry & banter")
    headline_standout_results = models.TextField(blank=True, null=True, help_text="HEADLINE 2: Impactful match results & full scores")
    headline_worst_performers = models.TextField(blank=True, null=True, help_text="HEADLINE 3: Fallers & worst performers in period")
    analysis_outlook = models.TextField(blank=True, null=True, help_text="ANALYSIS: AI predictions of opportunities & threats")
    featured_players_json = models.JSONField(default=list, blank=True, help_text="List of 3 featured player names & postures")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-publish_date', '-created_at']
        verbose_name = "Daily Gazette Edition"
        verbose_name_plural = "Daily Gazette Editions"

    def __str__(self):
        prefix = f"[Special R{self.round_number}] " if self.is_special_edition else ""
        return f"{prefix}{self.publish_date} - {self.headline}"


class RoundLeaderboardSnapshot(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='round_snapshots')
    round_number = models.IntegerField(help_text="Round milestone 1-9")
    round_name = models.CharField(max_length=100)
    player = models.ForeignKey(User, on_delete=models.CASCADE, related_name='round_snapshots')
    rank = models.IntegerField()
    points = models.IntegerField()
    exact_scores_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['round_number', 'rank']
        unique_together = ('tournament', 'round_number', 'player')

    def __str__(self):
        return f"Round {self.round_number} ({self.round_name}) - #{self.rank} {self.player.username} ({self.points}p)"


class StyleExample(models.Model):
    quote = models.TextField(help_text="Hand-written Swedish roast example for LLM tone calibration")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Style Example (Tone Calibration)"
        verbose_name_plural = "Style Examples (Tone Calibration)"

    def __str__(self):
        return f"Quote: {self.quote[:50]}"


class EditorialSettings(models.Model):
    banned_phrases = models.JSONField(default=list, help_text="List of overused phrases forbidden in LLM prompts")

    class Meta:
        verbose_name = "Editorial Settings"
        verbose_name_plural = "Editorial Settings"

    def __str__(self):
        return f"Editorial Settings ({len(self.banned_phrases or [])} banned phrases)"


# --- HERRKLUBBEN BUCKET LIST MODELS ---


class BucketCategory(models.Model):
    name = models.CharField(max_length=100)
    icon = models.CharField(max_length=10, default="🪣")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = "Bucket Category"
        verbose_name_plural = "Bucket Categories"

    def __str__(self):
        return f"{self.icon} {self.name}"

    @property
    def open_items(self):
        return self.items.filter(is_completed=False).order_by('title')


class BucketItem(models.Model):
    title = models.CharField(max_length=200)
    category = models.ForeignKey(BucketCategory, on_delete=models.CASCADE, related_name='items')
    description = models.TextField(blank=True, help_text="Valfri beskrivning av aktiviteten")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_bucket_items')
    is_completed = models.BooleanField(default=False)
    completed_date = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @property
    def total_points(self):
        pts = 0
        for v in self.votes.all():
            if v.marker == 'SVART':
                pts += 100
            elif v.marker == 'GRON':
                pts += 50
            elif v.marker == 'ROD':
                pts += 25
        return pts

    @property
    def vote_count(self):
        return self.votes.values('user').distinct().count()

    @property
    def count_svart(self):
        return self.votes.filter(marker='SVART').count()

    @property
    def count_gron(self):
        return self.votes.filter(marker='GRON').count()

    @property
    def count_rod(self):
        return self.votes.filter(marker='ROD').count()

    @property
    def is_planerad(self):
        return self.vote_count >= 6 and not self.is_completed

    @property
    def dream_users(self):
        return [d.user for d in self.dreams.select_related('user').all()]


class BucketVote(models.Model):
    MARKER_CHOICES = [
        ('SVART', 'Svart Marker (100)'),
        ('GRON', 'Grön Marker (50)'),
        ('ROD', 'Röd Marker (25)'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bucket_votes')
    item = models.ForeignKey(BucketItem, on_delete=models.CASCADE, related_name='votes')
    marker = models.CharField(max_length=10, choices=MARKER_CHOICES)
    created_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Bucket Vote"
        verbose_name_plural = "Bucket Votes"

    def __str__(self):
        return f"{self.user.username} -> {self.item.title} ({self.marker})"


class BucketDream(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bucket_dreams')
    item = models.ForeignKey(BucketItem, on_delete=models.CASCADE, related_name='dreams')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Bucket Dream (Högsta Dröm)"
        verbose_name_plural = "Bucket Dreams (Högsta Dröm)"

    def __str__(self):
        return f"🪣 {self.user.username}'s Högsta Dröm -> {self.item.title}"


class UserUnavailability(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='unavailabilities')
    start_date = models.DateField(verbose_name="Startdatum")
    end_date = models.DateField(verbose_name="Slutdatum")
    reason = models.CharField(max_length=255, blank=True, null=True, verbose_name="Anledning (Valfritt)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['start_date']
        verbose_name = "Hinder / Frånvaro"
        verbose_name_plural = "Hinder / Frånvaro"

    def __str__(self):
        return f"{self.user.username}: {self.start_date} - {self.end_date}"


class HerrklubbEvent(models.Model):
    title = models.CharField(max_length=200, verbose_name="Aktivitetsnamn")
    category = models.ForeignKey(BucketCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='events')
    description = models.TextField(blank=True, verbose_name="Beskrivning")
    event_date = models.DateField(null=True, blank=True, verbose_name="Startdatum")
    end_date = models.DateField(null=True, blank=True, verbose_name="Slutdatum")
    event_time = models.TimeField(null=True, blank=True, verbose_name="Tid")
    location = models.CharField(max_length=255, blank=True, null=True, verbose_name="Plats")
    coordinators = models.ManyToManyField(User, related_name='coordinated_events', blank=True, verbose_name="Samordnare")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_events')
    is_active = models.BooleanField(default=True, help_text="Visas som Nästa Event")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['event_date', '-created_at']
        verbose_name = "Herrklubb Event"
        verbose_name_plural = "Herrklubb Events"

    def __str__(self):
        return f"Event: {self.title} ({self.event_date or 'Inget datum'})"

