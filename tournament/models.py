import re
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


import secrets

class MasterEvent(models.Model):
    name = models.CharField(max_length=200, help_text="Global tournament sporting event (e.g. UEFA EURO 2028)")
    code = models.SlugField(unique=True, help_text="Unique event code slug (e.g. euro-2028)")
    is_active = models.BooleanField(default=True)
    icon = models.ImageField(upload_to='events/icons/', blank=True, null=True, help_text="Global event icon/emblem")
    backdrop = models.ImageField(upload_to='events/backdrops/', blank=True, null=True, help_text="Global event header backdrop")

    def __str__(self):
        return self.name


class League(models.Model):
    master_event = models.ForeignKey(MasterEvent, on_delete=models.CASCADE, related_name='leagues', null=True, blank=True)
    name = models.CharField(max_length=200, help_text="Private friend group or commercial pool name")
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name='managed_leagues')
    invite_code = models.CharField(max_length=12, unique=True, blank=True, help_text="Unique 6-character joining code (e.g. ENGINE8)")
    is_active = models.BooleanField(default=True)
    is_actual_knockout_open = models.BooleanField(default=False, help_text="Open predictions for the actual knockout bracket after group stage ends")
    created_at = models.DateTimeField(default=timezone.now)

    # Per-League Custom Branding
    logo = models.ImageField(upload_to='leagues/logos/', blank=True, null=True, help_text="Custom friend pool emblem/logo")
    banner = models.ImageField(upload_to='leagues/banners/', blank=True, null=True, help_text="Custom friend pool header backdrop banner")
    primary_color = models.CharField(max_length=20, default='#10b981', help_text="Custom brand accent color hex code")

    def save(self, *args, **kwargs):
        if not self.invite_code:
            self.invite_code = secrets.token_hex(3).upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.invite_code})"


class LeagueMember(models.Model):
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='members')
    player = models.ForeignKey(User, on_delete=models.CASCADE, related_name='league_memberships')
    joined_at = models.DateTimeField(default=timezone.now)
    is_verified = models.BooleanField(default=False, help_text="Verified coupon by League Admin")

    class Meta:
        unique_together = ('league', 'player')

    def __str__(self):
        return f"{self.player.username} in {self.league.name}"


class Tournament(models.Model):
    name = models.CharField(max_length=200)
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name='managed_tournaments')
    players = models.ManyToManyField(User, related_name='participating_tournaments', blank=True)
    is_active = models.BooleanField(default=True)
    is_paused = models.BooleanField(default=False, help_text="Manually paused / deactivated tournament")
    is_actual_knockout_open = models.BooleanField(default=False, help_text="Open predictions for the actual knockout bracket after group stage ends")
    
    # Declarative Ranking Table Configuration (Specific to tournament rules!)
    has_runners_up_table = models.BooleanField(default=False, help_text="Builds Runners-Up ranking table across groups (e.g. Euro 2028 Qualifiers)")
    has_host_ranking_table = models.BooleanField(default=False, help_text="Builds Co-Host ranking safety net table (e.g. Euro 2028 Qualifiers)")
    has_best_thirds_table = models.BooleanField(default=False, help_text="Builds Best 3rd-placed teams ranking table (e.g. Euro 2028 Finals)")
    
    # New branding fields
    icon = models.ImageField(upload_to='tournament/icons/', blank=True, null=True, help_text="Tournament emblem/favicon")
    backdrop = models.ImageField(upload_to='tournament/backdrops/', blank=True, null=True, help_text="Header backdrop background")

    def __str__(self):
        return self.name

    def get_runners_up_ranking_table(self, user_predictions=None):
        """
        Calculates UEFA official Ranking of Second-Placed Teams.
        Only calculated if has_runners_up_table is True!
        In 5-team groups (G-L), results against the 5th-placed team are discarded
        to compare fairly against 4-team groups (A-F).
        Top 8 runners-up qualify directly; remaining 4 enter play-offs.
        """
        if not self.has_runners_up_table:
            return None
        runners_up = []
        for group in self.tournament_groups.all():
            standings = group.get_standings(user_predictions=user_predictions)
            if len(standings) >= 2:
                second_place = standings[1]
                team_obj = second_place['team']
                
                # If group has 5 teams, exclude 5th place team match results
                if len(standings) == 5:
                    fifth_place_team_name = standings[4]['team'].name
                    
                    adj_played = 0
                    adj_gf = 0
                    adj_ga = 0
                    adj_points = 0
                    adj_won = 0
                    adj_drawn = 0
                    adj_lost = 0
                    
                    for match in group.matches.all():
                        if match.home_team == fifth_place_team_name or match.away_team == fifth_place_team_name:
                            continue
                            
                        if match.home_team != team_obj.name and match.away_team != team_obj.name:
                            continue
                            
                        hg, ag = None, None
                        if user_predictions and match.id in user_predictions:
                            pred = user_predictions[match.id]
                            if pred and pred.home_goals is not None and pred.away_goals is not None:
                                hg, ag = pred.home_goals, pred.away_goals
                        elif match.home_goals is not None and match.away_goals is not None:
                            hg, ag = match.home_goals, match.away_goals
                            
                        if hg is None or ag is None:
                            continue
                            
                        adj_played += 1
                        is_home = (match.home_team == team_obj.name)
                        team_g = hg if is_home else ag
                        opp_g = ag if is_home else hg
                        
                        adj_gf += team_g
                        adj_ga += opp_g
                        
                        if team_g > opp_g:
                            adj_won += 1
                            adj_points += 3
                        elif team_g == opp_g:
                            adj_drawn += 1
                            adj_points += 1
                        else:
                            adj_lost += 1
                            
                    adj_gd = adj_gf - adj_ga
                    runners_up.append({
                        'group_name': group.name,
                        'team': team_obj,
                        'played': adj_played,
                        'won': adj_won,
                        'drawn': adj_drawn,
                        'lost': adj_lost,
                        'gf': adj_gf,
                        'ga': adj_ga,
                        'gd': adj_gd,
                        'points': adj_points,
                        'adjusted_for_5th': True,
                    })
                else:
                    runners_up.append({
                        'group_name': group.name,
                        'team': team_obj,
                        'played': second_place['played'],
                        'won': second_place['won'],
                        'drawn': second_place['drawn'],
                        'lost': second_place['lost'],
                        'gf': second_place['gf'],
                        'ga': second_place['ga'],
                        'gd': second_place['gd'],
                        'points': second_place['points'],
                        'adjusted_for_5th': False,
                    })
                    
        # Sort runners up by Points desc, GD desc, GF desc, Wins desc
        runners_up.sort(key=lambda x: (x['points'], x['gd'], x['gf'], x['won']), reverse=True)
        
        # Mark rank & qualification status
        for rank_idx, row in enumerate(runners_up, start=1):
            row['rank'] = rank_idx
            if rank_idx <= 8:
                row['status'] = 'DIREKTKVALIFICERAD'
                row['status_class'] = 'success'
                row['badge_text'] = 'Direktplats (Top 8 Tvåa)'
            else:
                row['status'] = 'PLAY-OFF'
                row['status_class'] = 'warning'
                row['badge_text'] = 'Kvalificerad till Play-off'
                
        return runners_up

    def get_host_ranking_table(self, user_predictions=None):
        """
        Calculates Ranking of Co-Host Nations (England, Ireland, Scotland, Wales).
        Determines direct qualification vs reserved host safety net spots (top 2 non-qualified hosts).
        Only calculated if has_host_ranking_table is True!
        """
        if not self.has_host_ranking_table:
            return None

        HOST_NAMES = ['England', 'Irland', 'Skottland', 'Wales', 'Republic of Ireland', 'Great Britain']
        host_rows = []
        
        for group in self.tournament_groups.all():
            standings = group.get_standings(user_predictions=user_predictions)
            for pos_idx, row in enumerate(standings, start=1):
                team = row['team']
                if any(h.lower() in team.name.lower() for h in HOST_NAMES):
                    is_group_winner = (pos_idx == 1)
                    host_rows.append({
                        'group_name': group.name,
                        'team': team,
                        'group_pos': pos_idx,
                        'is_group_winner': is_group_winner,
                        'played': row['played'],
                        'won': row['won'],
                        'drawn': row['drawn'],
                        'lost': row['lost'],
                        'gf': row['gf'],
                        'ga': row['ga'],
                        'gd': row['gd'],
                        'points': row['points'],
                    })
                    
        runners_up_table = self.get_runners_up_ranking_table(user_predictions=user_predictions) or []
        top_8_runner_up_names = {r['team'].name for r in runners_up_table if r.get('rank', 99) <= 8}
        
        for h in host_rows:
            if h['is_group_winner']:
                h['direct_qual'] = True
                h['qual_reason'] = 'Gruppetta (Direktplats)'
            elif h['team'].name in top_8_runner_up_names:
                h['direct_qual'] = True
                h['qual_reason'] = 'Top 8 Grupptvåa (Direktplats)'
            else:
                h['direct_qual'] = False
                h['qual_reason'] = 'Kvalificerade ej direkt via grupp'

        host_rows.sort(key=lambda x: (x['direct_qual'], x['points'], x['gd'], x['gf']), reverse=True)
        
        safety_spots_awarded = 0
        for idx, h in enumerate(host_rows, start=1):
            h['rank'] = idx
            if h['direct_qual']:
                h['final_status'] = 'DIREKTKVALIFICERAD'
                h['status_class'] = 'success'
            elif safety_spots_awarded < 2:
                safety_spots_awarded += 1
                h['final_status'] = 'VÄRDNATIONS-SAFETY NET'
                h['status_class'] = 'info'
                h['qual_reason'] = 'Tilldelad Värdnationsgaranti (Top 2 Värdland)'
            else:
                h['final_status'] = 'PLAY-OFF / UTSLAGEN'
                h['status_class'] = 'warning'
                
        return host_rows

    def get_best_thirds_ranking_table(self, user_predictions=None):
        """
        Calculates Ranking of 3rd-Placed Teams across groups (e.g. Euro 2028 Finals).
        Only calculated if has_best_thirds_table is True!
        """
        if not self.has_best_thirds_table:
            return None

        third_places = []
        for group in self.tournament_groups.all():
            standings = group.get_standings(user_predictions=user_predictions)
            if len(standings) >= 3:
                third_place = standings[2]
                third_places.append({
                    'group_name': group.name,
                    'team': third_place['team'],
                    'played': third_place['played'],
                    'won': third_place['won'],
                    'drawn': third_place['drawn'],
                    'lost': third_place['lost'],
                    'gf': third_place['gf'],
                    'ga': third_place['ga'],
                    'gd': third_place['gd'],
                    'points': third_place['points'],
                })

        third_places.sort(key=lambda x: (x['points'], x['gd'], x['gf'], x['won']), reverse=True)

        for rank_idx, row in enumerate(third_places, start=1):
            row['rank'] = rank_idx
            if rank_idx <= 4:
                row['status'] = 'KVALIFICERAD (R16)'
                row['status_class'] = 'success'
                row['badge_text'] = 'Vidare till Åttondelsfinal (Bästa 3:a)'
            else:
                row['status'] = 'UTSLAGEN'
                row['status_class'] = 'danger'
                row['badge_text'] = 'Utslagen (Ej bland 4 bästa 3:or)'

        return third_places


class PointSystem(models.Model):
    tournament = models.OneToOneField(Tournament, on_delete=models.CASCADE, related_name='point_system')
    
    # Match Scoring
    match_correct_goals_per_team = models.IntegerField(default=3)
    match_correct_total_goals = models.IntegerField(default=1)
    match_correct_1x2 = models.IntegerField(default=3)
    
    # 1. Regular Group Tables Scoring (Default: Points for rank, pts, GF, GA, GD. 0 for team qualified)
    group_correct_placement = models.IntegerField(default=2, help_text="Points for exact rank in regular group table")
    group_correct_points = models.IntegerField(default=1, help_text="Points for correct group points")
    group_correct_goals_scored = models.IntegerField(default=1, help_text="Points for correct GF in group table")
    group_correct_goals_conceded = models.IntegerField(default=1, help_text="Points for correct GA in group table")
    group_correct_goal_diff = models.IntegerField(default=1, help_text="Points for correct GD (+/-) in group table")
    group_team_qualified = models.IntegerField(default=0, help_text="Points for team qualified from regular group table (Default 0)")
    
    # 2. Qualifying / Special Ranking Tables Scoring (Hosts, Best Thirds, Runners-Up, Overall Rankings)
    qualifying_table_team_qualified = models.IntegerField(default=5, help_text="Points for predicting team qualified from special ranking table (Default 5)")
    qualifying_table_exact_rank = models.IntegerField(default=0, help_text="Points for exact rank in special ranking table (Default 0)")
    qualifying_table_points = models.IntegerField(default=0, help_text="Points for correct points in special ranking table (Default 0)")
    qualifying_table_goals_scored = models.IntegerField(default=0, help_text="Points for correct GF in special ranking table (Default 0)")
    qualifying_table_goals_conceded = models.IntegerField(default=0, help_text="Points for correct GA in special ranking table (Default 0)")
    qualifying_table_goal_diff = models.IntegerField(default=0, help_text="Points for correct GD in special ranking table (Default 0)")
    
    # Knockout Stage Scoring
    knockout_qualified_third = models.IntegerField(default=2)
    knockout_round_of_16 = models.IntegerField(default=3)
    knockout_quarterfinal = models.IntegerField(default=4)
    knockout_semifinal = models.IntegerField(default=5)
    knockout_bronze_match = models.IntegerField(default=0)
    knockout_final = models.IntegerField(default=8)

    def __str__(self):
        return f"Point System for {self.tournament.name}"


class LeaguePointSystem(models.Model):
    """Allows Pool Admin to customize points or set points = 0 for any parameter for their individual pool."""
    league = models.OneToOneField(League, on_delete=models.CASCADE, related_name='custom_point_system')
    
    # Match Scoring
    match_correct_goals_per_team = models.IntegerField(default=3)
    match_correct_total_goals = models.IntegerField(default=1)
    match_correct_1x2 = models.IntegerField(default=3)
    
    # Regular Group Tables Scoring
    group_correct_placement = models.IntegerField(default=2)
    group_correct_points = models.IntegerField(default=1)
    group_correct_goals_scored = models.IntegerField(default=1)
    group_correct_goals_conceded = models.IntegerField(default=1)
    group_correct_goal_diff = models.IntegerField(default=1)
    group_team_qualified = models.IntegerField(default=0)
    
    # Qualifying / Special Ranking Tables Scoring
    qualifying_table_team_qualified = models.IntegerField(default=5)
    qualifying_table_exact_rank = models.IntegerField(default=0)
    qualifying_table_points = models.IntegerField(default=0)
    qualifying_table_goals_scored = models.IntegerField(default=0)
    qualifying_table_goals_conceded = models.IntegerField(default=0)
    qualifying_table_goal_diff = models.IntegerField(default=0)
    
    # Knockout Stage Scoring
    knockout_round_of_16 = models.IntegerField(default=3)
    knockout_quarterfinal = models.IntegerField(default=4)
    knockout_semifinal = models.IntegerField(default=5)
    knockout_final = models.IntegerField(default=8)

    def __str__(self):
        return f"Custom Point System for Pool: {self.league.name}"


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
    'south africa': 'za',
    'qatar': 'qa',
    'paraguay': 'py',
    'saudi arabia': 'sa',
    'peru': 'pe',
    'algeria': 'dz',
    'ecuador': 'ec',
    'ivory coast': 'ci',
    'iran': 'ir',
    'egypt': 'eg',
    'tunisia': 'tn',
    'sydafrika': 'za',
    'saudiarabien': 'sa',
    'algeriet': 'dz',
    'elfenbenskusten': 'ci',
    'egypten': 'eg',
    'tunisien': 'tn',

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
    'ukraina': 'ua',
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
        if self.name:
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

    def get_avatar_url(self):
        if self.avatar and hasattr(self.avatar, 'url'):
            return self.avatar.url
        return None

    def __str__(self):
        return f"Profil för {self.user.username}"


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


class BannedPhrase(models.Model):
    phrase = models.CharField(max_length=100, unique=True, help_text="Banned word or cliché phrase (e.g. 'bollen är rund')")
    reason = models.CharField(max_length=200, blank=True, help_text="Why this phrase is prohibited")

    def __str__(self):
        return self.phrase


class PlayerPersona(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='persona', null=True, blank=True)
    full_name = models.CharField(max_length=100, help_text="Player full name")
    nickname = models.CharField(max_length=100, help_text="Editorial nickname (e.g. 'Presidenten', 'Statistikern')")
    occupation = models.CharField(max_length=150, blank=True, help_text="Occupation or persona background")
    preferred_roast_style = models.CharField(max_length=100, default="Dry Scandinavian Sarcasm", help_text="Roast style directive for AI editorial engine")
    avatar_filename = models.CharField(max_length=100, blank=True, null=True, help_text="Base avatar image file name")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.full_name} ({self.nickname})"


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




