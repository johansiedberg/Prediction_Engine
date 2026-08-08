from django.contrib import admin
from django.contrib.auth.models import Group as AuthGroup, User
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserCreationForm
from django.utils.html import format_html
from .models import (
    Tournament, PointSystem, Group, Team, KnockoutStage, 
    Match, MatchPrediction, Sidebet, SidebetAnswer, TournamentSubmission,
    StaticInsight, InsightEvent, StorylineMemory, DailyGazette, StyleExample, EditorialSettings,
    UserProfile, BucketCategory, BucketItem, BucketVote, BucketDream
)


class PointSystemInline(admin.StackedInline):
    model = PointSystem
    can_delete = False 
    extra = 0
    
    class Media:
        css = {
            'all': ('tournament/admin_columns.css',)
        }
    
    fieldsets = [
        ('1. Points per game', {
            'fields': (
                'match_correct_goals_per_team', 
                'match_correct_total_goals', 
                'match_correct_1x2',
            )
        }),
        ('2. Predictions of Groupstage', {
            'fields': (
                'group_correct_placement', 
                'group_correct_points', 
                'group_correct_goals_scored',
                'group_correct_goals_conceded', 
                'group_correct_goal_diff',
            )
        }),
        ('3. Predictions of Knockoutstage', {
            'fields': (
                'knockout_qualified_third', 
                'knockout_round_of_16', 
                'knockout_quarterfinal',
                'knockout_semifinal', 
                'knockout_bronze_match', 
                'knockout_final',
            )
        }),
    ]

class GroupInline(admin.TabularInline):
    model = Group
    fk_name = 'tournament'
    extra = 1
    verbose_name = "Group"
    verbose_name_plural = "2. Groups (Add Group Names First)"

class TeamInline(admin.TabularInline):
    model = Team
    fk_name = 'tournament'
    extra = 1
    fields = ('group', 'name', 'code', 'flag_preview')
    readonly_fields = ('flag_preview',)
    verbose_name = "Team"
    verbose_name_plural = "3. Teams (Assign Group & Type Name)"

    def flag_preview(self, obj):
        if obj and obj.code:
            return format_html('<img src="https://flagcdn.com/w40/{}.png" width="30" style="border-radius: 2px; box-shadow: 0 1px 3px rgba(0,0,0,0.2);" />', obj.code.lower())
        return "Auto / Ingen flagga"
    flag_preview.short_description = "Flagga"

class KnockoutStageInline(admin.TabularInline):
    model = KnockoutStage
    fk_name = 'tournament'
    extra = 1
    verbose_name = "Knockout Stage"
    verbose_name_plural = "4. Knockout Stages (Round of 16, Quarter-finals, etc.)"

class MatchInline(admin.TabularInline):
    model = Match
    fk_name = 'tournament'
    extra = 1
    verbose_name = "Match"
    verbose_name_plural = "5. Matches (Report Results & Link to Group or Stage)"
    fields = ('match_number', 'group', 'stage', 'date_time', 'home_team', 'home_goals', 'away_goals', 'away_team', 'is_finished')


class SidebetInline(admin.TabularInline):
    model = Sidebet
    fk_name = 'tournament'
    extra = 1
    verbose_name = "Bonusfråga"
    verbose_name_plural = "6. Bonusfrågor & Officiella Svar (Fråga, Poäng, Typ & Rätt Svar)"
    fields = ('question', 'points', 'question_type', 'correct_answers')


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'is_actual_knockout_open')
    list_editable = ('is_active', 'is_actual_knockout_open')
    inlines = [PointSystemInline, GroupInline, TeamInline, KnockoutStageInline, MatchInline, SidebetInline]
    filter_horizontal = ('players',)

    class Media:
        css = {
            'all': ('tournament/admin_columns.css',)
        }
        js = ('tournament/admin_enter.js',)


@admin.register(TournamentSubmission)
class TournamentSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        'player', 
        'tournament', 
        'user_created_status', 
        'user_logged_in_status', 
        'is_saved', 
        'is_verified', 
        'prediction_status_indicator'
    )
    list_filter = ('tournament', 'is_saved', 'is_verified')
    list_editable = ('is_verified',)
    search_fields = ('player__username', 'player__email')

    def changelist_view(self, request, extra_context=None):
        """Auto-sync all non-staff users into TournamentSubmission records for active tournaments efficiently."""
        tournaments = list(Tournament.objects.filter(is_active=True))
        if not tournaments:
            tournaments = list(Tournament.objects.all())

        non_staff_users = list(User.objects.filter(is_staff=False, is_superuser=False))
        if tournaments and non_staff_users:
            for tournament in tournaments:
                existing_player_ids = set(tournament.players.values_list('id', flat=True))
                missing_players = [u for u in non_staff_users if u.id not in existing_player_ids]
                if missing_players:
                    tournament.players.add(*missing_players)

                existing_sub_player_ids = set(
                    TournamentSubmission.objects.filter(tournament=tournament).values_list('player_id', flat=True)
                )
                new_subs = [
                    TournamentSubmission(tournament=tournament, player=u)
                    for u in non_staff_users if u.id not in existing_sub_player_ids
                ]
                if new_subs:
                    TournamentSubmission.objects.bulk_create(new_subs, ignore_conflicts=True)

        return super().changelist_view(request, extra_context=extra_context)

    @admin.display(description='User created', boolean=True)
    def user_created_status(self, obj):
        return obj.player is not None

    @admin.display(description='User logged in', boolean=True)
    def user_logged_in_status(self, obj):
        return obj.player.last_login is not None

    def prediction_status_indicator(self, obj):
        total_matches = Match.objects.filter(tournament=obj.tournament).count()
        user_preds = MatchPrediction.objects.filter(match__tournament=obj.tournament, player=obj.player).count()

        if user_preds == 0:
            return f"❌ Ej påbörjad (0/{total_matches} tippade)"
        elif user_preds < total_matches:
            return f"⚠️ Ofullständig ({user_preds}/{total_matches} tippade)"
        elif not obj.is_saved:
            return f"⚠️ Tippat alla ({user_preds}/{total_matches}) men EJ SPARAD"
        elif obj.is_verified:
            return "✅ Godkänd & Verifierad"
        return "✅ Sparad & redo för godkännande"
    
    prediction_status_indicator.short_description = "Status & Indikation"


@admin.register(MatchPrediction)
class MatchPredictionAdmin(admin.ModelAdmin):
    list_display = ('player', 'match', 'prediction_phase', 'home_goals', 'away_goals', 'penalty_winner')
    list_filter = ('prediction_phase', 'match__tournament')
    search_fields = ('player__username', 'match__home_team', 'match__away_team')


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = (
        'match_number', 
        'tournament', 
        'group', 
        'stage', 
        'home_team_formatted', 
        'home_goals', 
        'away_goals', 
        'away_team_formatted', 
        'is_finished'
    )
    list_filter = ('tournament', 'is_finished', 'group', 'stage')
    list_editable = ('home_goals', 'away_goals', 'is_finished')
    list_select_related = ('tournament', 'group', 'stage')
    search_fields = ('home_team', 'away_team')
    fieldsets = (
        ('Match Info', {
            'fields': ('tournament', 'match_number', 'group', 'stage', 'date_time', 'home_team', 'away_team')
        }),
        ('Match Results', {
            'fields': ('home_goals', 'away_goals', 'is_finished')
        }),
        ('Expandable Box Score Data', {
            'classes': ('collapse',),
            'fields': ('box_score_data',),
        }),
    )

    def home_team_formatted(self, obj):
        info = obj.get_home_team_info()
        if info['flag_url']:
            flag = f'<img src="{info["flag_url"]}" width="25" style="border-radius: 2px; vertical-align: middle; margin-right: 6px; box-shadow: 0 1px 2px rgba(0,0,0,0.2);" />'
            return format_html('{} {}', flag, info['display_name'])
        return info['display_name']
    home_team_formatted.short_description = "Hemmalag"

    def away_team_formatted(self, obj):
        info = obj.get_away_team_info()
        if info['flag_url']:
            flag = f'<img src="{info["flag_url"]}" width="25" style="border-radius: 2px; vertical-align: middle; margin-right: 6px; box-shadow: 0 1px 2px rgba(0,0,0,0.2);" />'
            return format_html('{} {}', flag, info['display_name'])
        return info['display_name']
    away_team_formatted.short_description = "Bortalag"






class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')

class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2'),
        }),
    )

admin.site.unregister(AuthGroup)
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

admin.site.enable_nav_sidebar = False


# --- Editorial Engine Admin Registrations ---

@admin.register(StaticInsight)
class StaticInsightAdmin(admin.ModelAdmin):
    list_display = ('category', 'player_name', 'data_point_short', 'is_published', 'tournament', 'created_at')
    list_filter = ('category', 'is_published', 'tournament')
    list_editable = ('is_published',)
    search_fields = ('player_name', 'data_point', 'llm_roast')

    def data_point_short(self, obj):
        return obj.data_point[:60] + '...' if len(obj.data_point) > 60 else obj.data_point
    data_point_short.short_description = "Data Point"


@admin.register(InsightEvent)
class InsightEventAdmin(admin.ModelAdmin):
    list_display = ('type', 'player_name', 'importance_score', 'matchday_reference', 'is_used', 'tournament', 'created_at')
    list_filter = ('type', 'is_used', 'tournament')
    list_editable = ('importance_score', 'is_used')
    search_fields = ('player_name', 'description')


@admin.register(StorylineMemory)
class StorylineMemoryAdmin(admin.ModelAdmin):
    list_display = ('player_name', 'narrative_short', 'is_active', 'tournament', 'last_updated')
    list_filter = ('is_active', 'tournament')
    list_editable = ('is_active',)
    search_fields = ('player_name', 'narrative')

    def narrative_short(self, obj):
        return obj.narrative[:60] + '...' if len(obj.narrative) > 60 else obj.narrative
    narrative_short.short_description = "Narrative"


@admin.register(DailyGazette)
class DailyGazetteAdmin(admin.ModelAdmin):
    list_display = ('publish_date', 'headline', 'tagline', 'content_format', 'tone_used', 'tournament', 'created_at')
    list_filter = ('content_format', 'tournament', 'publish_date')
    search_fields = ('headline', 'tagline', 'content')
    date_hierarchy = 'publish_date'


@admin.register(StyleExample)
class StyleExampleAdmin(admin.ModelAdmin):
    list_display = ('quote_short', 'is_active', 'created_at')
    list_filter = ('is_active',)
    list_editable = ('is_active',)

    def quote_short(self, obj):
        return obj.quote[:80] + '...' if len(obj.quote) > 80 else obj.quote
    quote_short.short_description = "Quote Example"


@admin.register(EditorialSettings)
class EditorialSettingsAdmin(admin.ModelAdmin):
    list_display = ('id', 'banned_phrases_count')

    def banned_phrases_count(self, obj):
        return f"{len(obj.banned_phrases or [])} banned phrases"
    banned_phrases_count.short_description = "Banned Phrases Count"


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'is_herrklubb_member')
    list_filter = ('is_herrklubb_member',)
    list_editable = ('is_herrklubb_member',)
    search_fields = ('user__username', 'user__first_name', 'user__last_name')


@admin.register(BucketCategory)
class BucketCategoryAdmin(admin.ModelAdmin):
    list_display = ('icon', 'name', 'order')
    list_editable = ('order',)


@admin.register(BucketItem)
class BucketItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'vote_count', 'total_points', 'is_completed', 'created_by', 'created_at')
    list_filter = ('category', 'is_completed')
    search_fields = ('title', 'description')
    list_editable = ('is_completed',)


@admin.register(BucketVote)
class BucketVoteAdmin(admin.ModelAdmin):
    list_display = ('user', 'item', 'marker', 'created_at')
    list_filter = ('marker',)
    search_fields = ('user__username', 'item__title')


@admin.register(BucketDream)
class BucketDreamAdmin(admin.ModelAdmin):
    list_display = ('user', 'item', 'created_at')
    search_fields = ('user__username', 'item__title')
