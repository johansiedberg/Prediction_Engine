import secrets
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from tournament.models import League, LeagueMember, Tournament, PoolAdminRequest, MasterEvent, TournamentSubmission, Sidebet, LeaguePointSystem, UserProfile
from tournament.services.pool_admin_service import get_player_progress_matrix


@login_required
def pool_admin_hub_view(request):
    """Mina Pooler Hub: Overview of all pools managed by the user with direct creation modal."""
    if request.user.is_superuser:
        managed_leagues = League.objects.all().prefetch_related('members', 'tournaments').order_by('-created_at')
    else:
        managed_leagues = League.objects.filter(admin=request.user).prefetch_related('members', 'tournaments').order_by('-created_at')

    pending_request = PoolAdminRequest.objects.filter(user=request.user, status='PENDING').first()

    leagues_data = []
    for l in managed_leagues:
        active_t_count = l.tournaments.filter(is_active=True).count()
        members_count = l.members.count()
        verified_count = l.members.filter(is_verified=True).count()
        leagues_data.append({
            'league': l,
            'active_t_count': active_t_count,
            'members_count': members_count,
            'verified_count': verified_count,
        })

    context = {
        'leagues_data': leagues_data,
        'managed_leagues': managed_leagues,
        'pending_request': pending_request,
    }
    return render(request, 'tournament/pool_admin_hub.html', context)


@login_required
@require_POST
def create_pool_direct_view(request):
    """Allows an approved pool admin or superuser to directly create a new pool."""
    pool_name = request.POST.get('pool_name', '').strip()
    description = request.POST.get('description', '').strip()
    invite_code = request.POST.get('invite_code', '').strip().upper()
    primary_color = request.POST.get('primary_color', '#10b981').strip()

    if not pool_name:
        messages.error(request, "Vänligen ange ett namn på din pool.")
        return redirect('pool_admin_hub')

    if invite_code:
        if League.objects.filter(invite_code=invite_code).exists():
            messages.error(request, f"Pool ID '{invite_code}' används redan. Välj en annan unik kod.")
            return redirect('pool_admin_hub')
    else:
        invite_code = secrets.token_hex(3).upper()
        while League.objects.filter(invite_code=invite_code).exists():
            invite_code = secrets.token_hex(3).upper()

    league = League.objects.create(
        name=pool_name,
        description=description,
        admin=request.user,
        invite_code=invite_code,
        primary_color=primary_color,
    )

    if 'logo' in request.FILES:
        league.logo = request.FILES['logo']
        league.save()

    # Automatically add creator as verified member
    LeagueMember.objects.create(
        league=league,
        player=request.user,
        is_verified=True
    )

    messages.success(request, f"Poolen '{pool_name}' (ID: {invite_code}) har skapats!")
    return redirect('pool_admin_dashboard', league_id=league.id)


@login_required
@require_POST
def update_pool_admin_email_view(request):
    """Allows a pool admin to change the email address of their own account."""
    from django.db.models import Q
    new_email = request.POST.get('email', '').strip().lower()
    next_url = request.POST.get('next', '').strip() or request.META.get('HTTP_REFERER') or '/pool-admin/'

    if not new_email or '@' not in new_email or '.' not in new_email:
        messages.error(request, "Vänligen ange en giltig e-postadress.")
        return redirect(next_url)

    # Check if another user is already using this email or username
    conflict = User.objects.filter(
        Q(email__iexact=new_email) | Q(username__iexact=new_email)
    ).exclude(id=request.user.id).exists()

    if conflict:
        messages.error(request, f"Det finns redan ett konto registrerat med e-postadressen '{new_email}'.")
        return redirect(next_url)

    request.user.email = new_email
    request.user.username = new_email
    request.user.save(update_fields=['email', 'username'])

    messages.success(request, f"Din e-postadress har ändrats till '{new_email}'.")
    return redirect(next_url)


@ensure_csrf_cookie
def request_pool_admin_view(request):
    """Pool-Admin portal page: allows existing Pool-Admins to log in OR new Pool-Admins to apply/create an account."""
    from django.contrib.auth.models import User as DjangoUser
    from django.contrib.auth import authenticate, login

    pending_request = None
    if request.user.is_authenticated:
        pending_request = PoolAdminRequest.objects.filter(user=request.user, status='PENDING').first()

    if request.method == 'POST':
        action = request.POST.get('action', 'apply')

        if action == 'login':
            # Pool-Admin Login handler
            uname = request.POST.get('username', '').strip() or request.POST.get('email', '').strip()
            pwd = request.POST.get('password', '').strip()
            user = authenticate(request, username=uname, password=pwd)
            if user is None:
                # Try by email
                user_obj = DjangoUser.objects.filter(email__iexact=uname).first()
                if user_obj:
                    user = authenticate(request, username=user_obj.username, password=pwd)

            if user is not None:
                login(request, user, backend='tournament.backends.EmailAuthBackend')
                # Check if user owns a league
                user_league = League.objects.filter(admin=user).first()
                if user_league:
                    messages.success(request, f"Välkommen tillbaka, {user.first_name or user.email}!")
                    return redirect('pool_admin_hub')
                else:
                    messages.info(request, "Välkommen! Din Pool-Admin ansökan behandlas eller har inte aktiverats än.")
                    return redirect('request_pool_admin')
            else:
                messages.error(request, "Felaktig e-postadress eller lösenord.")
                return redirect('request_pool_admin')

        else:
            # Pool-Admin Apply / Create Account handler
            pool_name = request.POST.get('pool_name', '').strip()
            description = request.POST.get('description', '').strip()
            master_event_id = request.POST.get('master_event')

            if not pool_name:
                messages.error(request, "Vänligen ange ett namn på din tippningspool.")
                return redirect('request_pool_admin')

            user = request.user
            if not user.is_authenticated:
                first_name = request.POST.get('first_name', '').strip()
                last_name = request.POST.get('last_name', '').strip()
                email = request.POST.get('email', '').strip().lower()
                password = request.POST.get('password', '').strip()

                if not first_name or not email or not password:
                    messages.error(request, "Förnamn, e-postadress och lösenord krävs.")
                    return redirect('request_pool_admin')

                existing_user = DjangoUser.objects.filter(email__iexact=email).first()
                if existing_user:
                    user = existing_user
                else:
                    username = email.lower()
                    user = DjangoUser.objects.create_user(
                        username=username,
                        email=email,
                        password=password,
                        first_name=first_name,
                        last_name=last_name or ''
                    )
                login(request, user, backend='tournament.backends.EmailAuthBackend')

            master_event = None
            if master_event_id:
                master_event = MasterEvent.objects.filter(id=master_event_id).first()

            PoolAdminRequest.objects.create(
                user=user,
                pool_name=pool_name,
                description=description,
                master_event=master_event
            )
            messages.success(request, f"Tack {user.first_name}! Din ansökan om att starta '{pool_name}' har skickats in och behandlas nu.")
            return redirect('hub')

    master_events = MasterEvent.objects.filter(is_active=True)
    return render(request, 'tournament/request_pool_admin.html', {
        'master_events': master_events,
        'pending_request': pending_request
    })


@login_required
def pool_admin_dashboard_view(request, league_id):
    """Individual Pool Dashboard: Members list & active pool tournaments with visual tournament browser."""
    league = get_object_or_404(League, id=league_id)

    if league.admin != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("Du har inte behörighet att administrera denna liga.")

    # Synchronize session so global header and player views stay aligned with currently administered pool
    request.session['active_league_id'] = league.id

    # All user's managed leagues for fast header switcher
    if request.user.is_superuser:
        all_managed_leagues = League.objects.all().order_by('name')
    else:
        all_managed_leagues = League.objects.filter(admin=request.user).order_by('name')

    # Tournaments active in THIS pool
    pool_tournaments = league.tournaments.filter(is_active=True).prefetch_related('sidebets', 'players')
    pool_tournament_ids = set(pool_tournaments.values_list('id', flat=True))

    # All globally active tournaments in engine (Available for this pool)
    available_tournaments = Tournament.objects.filter(is_active=True).exclude(id__in=pool_tournament_ids)

    # Paused / Inactive / Coming tournaments in engine
    coming_tournaments = Tournament.objects.filter(is_active=False)

    # Members in this pool
    members = list(league.members.all().select_related('player').order_by('player__first_name', 'player__email'))
    from tournament.utils.magic_link import build_magic_login_url
    for m in members:
        m.magic_link = build_magic_login_url(request, m.player, league.id)

    # Check if admin is enrolled as player
    is_admin_enrolled = league.members.filter(player=request.user).exists()

    context = {
        'league': league,
        'all_managed_leagues': all_managed_leagues,
        'pool_tournaments': pool_tournaments,
        'available_tournaments': available_tournaments,
        'coming_tournaments': coming_tournaments,
        'members': members,
        'is_admin_enrolled': is_admin_enrolled,
    }
    return render(request, 'tournament/pool_admin.html', context)


@login_required
def pool_admin_tournament_config_view(request, league_id, tournament_id):
    """Dedicated configuration workspace for a single tournament inside a pool."""
    from tournament.models import LeaguePointSystem, Sidebet, ScannedTournament, KnockoutStage
    from tournament.services.format_blueprint_service import FormatBlueprintService
    league = get_object_or_404(League, id=league_id)

    if league.admin != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("Du har inte behörighet att administrera denna liga.")

    # Synchronize session so global header and player views stay aligned with currently administered pool
    request.session['active_league_id'] = league.id

    tournament = get_object_or_404(Tournament, id=tournament_id)
    is_active_in_pool = league.tournaments.filter(id=tournament.id).exists()

    point_system, created = LeaguePointSystem.objects.get_or_create(league=league)
    if created and hasattr(tournament, 'point_system') and tournament.point_system:
        t_ps = tournament.point_system
        point_system.match_correct_1x2 = t_ps.match_correct_1x2
        point_system.match_correct_goals_per_team = t_ps.match_correct_goals_per_team
        point_system.match_correct_total_goals = t_ps.match_correct_total_goals
        point_system.group_correct_placement = t_ps.group_correct_placement
        point_system.group_correct_points = t_ps.group_correct_points
        point_system.group_correct_goals_scored = t_ps.group_correct_goals_scored
        point_system.group_correct_goals_conceded = t_ps.group_correct_goals_conceded
        point_system.group_correct_goal_diff = t_ps.group_correct_goal_diff
        point_system.group_team_qualified = t_ps.group_team_qualified
        point_system.qualifying_table_team_qualified = t_ps.qualifying_table_team_qualified
        point_system.qualifying_table_exact_rank = t_ps.qualifying_table_exact_rank
        point_system.qualifying_table_points = t_ps.qualifying_table_points
        point_system.qualifying_table_goals_scored = t_ps.qualifying_table_goals_scored
        point_system.qualifying_table_goals_conceded = t_ps.qualifying_table_goals_conceded
        point_system.qualifying_table_goal_diff = t_ps.qualifying_table_goal_diff
        point_system.knockout_round_of_32 = t_ps.knockout_round_of_32
        point_system.knockout_round_of_16 = t_ps.knockout_round_of_16
        point_system.knockout_quarterfinal = t_ps.knockout_quarterfinal
        point_system.knockout_semifinal = t_ps.knockout_semifinal
        point_system.knockout_bronze_match = t_ps.knockout_bronze_match
        point_system.knockout_final = t_ps.knockout_final
        point_system.save()

    # Retrieve linked prospect from Engine Admin (ScannedTournament) or format blueprint
    scanned = (
        ScannedTournament.objects.filter(converted_tournament=tournament).first() or
        ScannedTournament.objects.filter(name__iexact=tournament.name).first()
    )
    bp = FormatBlueprintService.get_canonical_blueprint(tournament.name, tournament.sport) or {}
    scanned_payload = scanned.payload if (scanned and isinstance(scanned.payload, dict)) else {}

    # Extract or infer groups count & teams count
    groups_count = tournament.tournament_groups.count()
    if groups_count == 0 and scanned and scanned.payload and scanned.payload.get('groups'):
        groups_count = len(scanned.payload.get('groups'))
    elif groups_count == 0 and bp.get('groups_count'):
        groups_count = bp.get('groups_count')

    teams_count = tournament.teams.count()
    if teams_count == 0 and tournament.tournament_groups.exists():
        teams_count = tournament.tournament_groups.values('teams').distinct().count()
    if teams_count == 0 and scanned and scanned.payload and scanned.payload.get('groups'):
        teams_count = sum(len(g.get('teams', [])) for g in scanned.payload.get('groups'))
    elif teams_count == 0 and bp.get('teams_count'):
        teams_count = bp.get('teams_count')

    adv_logic = scanned_payload.get('advancement_logic') or {}
    teams_per_group_adv = adv_logic.get('teams_per_group_advancing') or (2 if groups_count > 0 else 0)

    has_best_thirds = tournament.has_best_thirds_table or adv_logic.get('has_best_thirds_table', False)
    best_thirds_count = adv_logic.get('best_third_placed_advancing', 4) if has_best_thirds else 0

    has_runners_up = tournament.has_runners_up_table or adv_logic.get('has_runners_up_table', False)
    runners_up_count = adv_logic.get('runners_up_advancing', 8) if has_runners_up else 0

    # Group stage points (win / draw / loss)
    pts_sys = scanned_payload.get('points_system') or {}
    points_win = pts_sys.get('win') if pts_sys.get('win') is not None else (bp.get('points_win') if bp.get('points_win') is not None else (2 if 'floorball' in tournament.sport.lower() or 'basketball' in tournament.sport.lower() else 3))
    points_draw = pts_sys.get('draw') if pts_sys.get('draw') is not None else (bp.get('points_draw') if bp.get('points_draw') is not None else (1 if 'floorball' in tournament.sport.lower() or 'football' in tournament.sport.lower() else 0))
    points_loss = pts_sys.get('loss') if pts_sys.get('loss') is not None else (bp.get('points_loss') if bp.get('points_loss') is not None else 0)

    # Tiebreaker hierarchy
    tiebreakers = (
        scanned_payload.get('tiebreakers') or
        bp.get('tiebreakers') or
        [
            'Inbördes möten (Poäng)',
            'Inbördes målskillnad',
            'Inbördes gjorda mål',
            'Total målskillnad',
            'Gjorda mål totalt',
            'Disciplinpoäng (Fair Play)',
            'Lottning'
        ]
    )

    # Match format description
    match_fmt = scanned_payload.get('match_format') or {}
    reg_min = match_fmt.get('regular_time_minutes', 90)
    extra_min = match_fmt.get('extra_time_minutes', 30)
    if 'floorball' in tournament.sport.lower() or 'innebandy' in tournament.sport.lower():
        match_format_summary = "Ordinarie speltid 3x20 min. Vid oavgjort i slutspel: 10 min sudden death följt av 5 straffar per lag."
    elif 'handball' in tournament.sport.lower() or 'handboll' in tournament.sport.lower():
        match_format_summary = "Ordinarie speltid 2x30 min. Vid oavgjort i slutspel: Förlängning (2x5 min) följt av 7-meterskast (straffar)."
    elif 'hockey' in tournament.sport.lower():
        match_format_summary = "Ordinarie speltid 3x20 min. Vid oavgjort: Sudden death övertid (3-mot-3 / 4-mot-4) följt av straffar."
    elif 'basket' in tournament.sport.lower():
        match_format_summary = "Ordinarie speltid 4x10 min. Vid oavgjort: Förlängning (5 min) tills en vinnare koras."
    else:
        match_format_summary = f"Ordinarie speltid {reg_min} min. Vid oavgjort i slutspel: Förlängning ({extra_min} min) följt av Straffsparksläggning."

    # Qualifying summary
    if has_best_thirds and best_thirds_count > 0:
        qualifying_summary = f"Ranking av 3:or: De {best_thirds_count} bästa 3:orna avancerar till slutspel."
    elif has_runners_up and runners_up_count > 0:
        qualifying_summary = f"Kvaltabell för 2:or: De {runners_up_count} bästa grupptvåorna avancerar."
    elif groups_count > 0:
        qualifying_summary = f"Direktavancemang: Topp {teams_per_group_adv} per grupp avancerar till slutspelet."
    else:
        qualifying_summary = "Enligt officiella föreskrifter."

    # Knockout stages mapping
    stages_qs = tournament.knockout_stages.all().order_by('order', 'id')
    stages_list = list(stages_qs)

    def _clean_stage_name(stage_name):
        low = stage_name.lower()
        if 'second group' in low or 'andra grupp' in low or 'mellanrunda' in low or 'main round' in low:
            return 'Andra gruppspelet'
        elif '32' in low or 'play-off' in low or 'playoff' in low or 'sextondel' in low:
            return 'Sextondelsfinal'
        elif '16' in low or 'åttondel' in low or 'eighth' in low:
            return 'Åttondelsfinal'
        elif 'quarter' in low or 'kvarts' in low or 'qf' in low:
            return 'Kvartsfinal'
        elif 'semi' in low or 'sf' in low:
            return 'Semifinal'
        elif 'bronze' in low or '3rd' in low or '3:e' in low or 'tredje' in low or 'brons' in low:
            return 'Bronsmatch'
        elif 'final' in low or 'guld' in low:
            return 'Final'
        else:
            return stage_name

    knockout_stages_list = []
    if stages_list:
        for s in stages_list:
            knockout_stages_list.append(_clean_stage_name(s.name))
        first_stage = knockout_stages_list[0]
        knockout_summary = f"Startar med {first_stage} ({len(stages_list)} slutspelsomgångar)."
    else:
        knockout_stages_list = ['Åttondelsfinal', 'Kvartsfinal', 'Semifinal', 'Final']
        knockout_summary = "Slutspelsträd enligt officiellt spelschema."

    def _map_stage(stage_name, default_order=0):
        low = stage_name.lower()
        if '32' in low or 'play-off' in low or 'playoff' in low or 'sextondel' in low:
            return 'knockout_round_of_32', 'Play-off / Sextondelsfinal', getattr(point_system, 'knockout_round_of_32', 2)
        elif '16' in low or 'åttondel' in low or 'eighth' in low:
            return 'knockout_round_of_16', 'Åttondelsfinal', getattr(point_system, 'knockout_round_of_16', 4)
        elif 'quarter' in low or 'kvarts' in low or 'qf' in low:
            return 'knockout_quarterfinal', 'Kvartsfinal', getattr(point_system, 'knockout_quarterfinal', 6)
        elif 'semi' in low or 'sf' in low:
            return 'knockout_semifinal', 'Semifinal', getattr(point_system, 'knockout_semifinal', 8)
        elif 'bronze' in low or '3rd' in low or '3:e' in low or 'tredje' in low:
            return 'knockout_bronze_match', 'Bronsmatch (3:e pris)', getattr(point_system, 'knockout_bronze_match', 10)
        elif 'final' in low or 'guld' in low:
            return 'knockout_final', 'Finalmatch', getattr(point_system, 'knockout_final', 10)
        else:
            return 'knockout_quarterfinal', stage_name, getattr(point_system, 'knockout_quarterfinal', 6)

    tournament_knockout_stages = []
    if stages_list:
        for idx, s in enumerate(stages_list):
            f_name, label, val = _map_stage(s.name, idx)
            tournament_knockout_stages.append({
                'stage': s,
                'stage_name': s.name,
                'field_name': f_name,
                'label': f"{label} Bonus",
                'value': val,
            })
    else:
        default_stages = [
            ('knockout_round_of_16', 'Åttondelsfinal Bonus', point_system.knockout_round_of_16),
            ('knockout_quarterfinal', 'Kvartsfinal Bonus', point_system.knockout_quarterfinal),
            ('knockout_semifinal', 'Semifinal Bonus', point_system.knockout_semifinal),
            ('knockout_final', 'Bronsmatch & Final Bonus', point_system.knockout_final),
        ]
        for f_name, label, val in default_stages:
            tournament_knockout_stages.append({
                'stage': None,
                'stage_name': label,
                'field_name': f_name,
                'label': label,
                'value': val,
            })

    official_rules = (
        tournament.official_rules or
        (scanned.official_rules if scanned else '') or
        bp.get('official_rules_summary', '') or
        "Officiella turneringsregler och föreskrifter enligt arrangörens officiella regelbok."
    )
    official_regulations_url = (
        tournament.official_regulations_url or
        (scanned.official_source_url if scanned else '')
    )

    structure_data = {
        'groups_count': groups_count,
        'teams_count': teams_count,
        'teams_per_group_advancing': teams_per_group_adv,
        'qualifying_summary': qualifying_summary,
        'knockout_summary': knockout_summary,
        'knockout_stages': knockout_stages_list,
        'points_win': points_win,
        'points_draw': points_draw,
        'points_loss': points_loss,
        'match_format_summary': match_format_summary,
        'tiebreakers': tiebreakers,
        'official_rules': official_rules,
        'official_regulations_url': official_regulations_url,
    }

    sidebets = Sidebet.objects.filter(tournament=tournament)
    players_data = get_player_progress_matrix(league, tournament)
    from tournament.utils.magic_link import build_magic_login_url
    for p in players_data:
        p['magic_link'] = build_magic_login_url(request, p['player'], league.id)

    enrolled_players = tournament.players.all().order_by('first_name', 'email')
    enrolled_user_ids = set(enrolled_players.values_list('id', flat=True))
    members = list(league.members.all().select_related('player').order_by('player__first_name', 'player__email'))
    for m in members:
        m.magic_link = build_magic_login_url(request, m.player, league.id)

    context = {
        'league': league,
        'tournament': tournament,
        'is_active_in_pool': is_active_in_pool,
        'point_system': point_system,
        'structure_data': structure_data,
        'tournament_knockout_stages': tournament_knockout_stages,
        'sidebets': sidebets,
        'players_data': players_data,
        'enrolled_user_ids': enrolled_user_ids,
        'enrolled_players': enrolled_players,
        'members': members,
    }
    return render(request, 'tournament/pool_admin_tournament_config.html', context)


@login_required
@require_POST
def pool_admin_bulk_toggle_players_view(request, league_id, tournament_id):
    """Enrolls or removes ALL pool members to/from a tournament."""
    from django.urls import reverse
    league = get_object_or_404(League, id=league_id)
    if league.admin != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("Åtkomst nekad.")

    tournament = get_object_or_404(Tournament, id=tournament_id)
    action = request.POST.get('action')

    # Ensure tournament is active in pool
    league.tournaments.add(tournament)

    members_users = [m.player for m in league.members.all().select_related('player')]

    if action == 'enroll_all':
        for u in members_users:
            tournament.players.add(u)
        messages.success(request, f"Alla {len(members_users)} poolmedlemmar har kopplats till {tournament.name}!")
    elif action == 'remove_all':
        for u in members_users:
            tournament.players.remove(u)
        messages.info(request, f"Alla deltagare har kopplats bort från {tournament.name}.")

    return redirect(f"{reverse('pool_admin_tournament_config', args=[league.id, tournament.id])}#sec-participants")


@login_required
@require_POST
def toggle_pool_tournament_view(request, league_id, tournament_id):
    """Activates or deactivates a tournament for this individual pool."""
    league = get_object_or_404(League, id=league_id)
    if league.admin != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("Åtkomst nekad.")

    tournament = get_object_or_404(Tournament, id=tournament_id)
    action = request.POST.get('action')
    return_to = request.POST.get('return_to', 'dashboard')

    if action == 'deactivate' or (not action and tournament in league.tournaments.all()):
        league.tournaments.remove(tournament)
        messages.info(request, f"Turneringen '{tournament.name}' har kopplats bort från {league.name}.")
    else:
        league.tournaments.add(tournament)
        messages.success(request, f"Turneringen '{tournament.name}' är nu aktiverad för {league.name}!")

    if return_to == 'config':
        return redirect('pool_admin_tournament_config', league_id=league.id, tournament_id=tournament.id)
    return redirect('pool_admin_dashboard', league_id=league.id)


@login_required
@require_POST
def toggle_tournament_player_view(request, league_id, tournament_id, user_id):
    """Enrolls or removes a pool player from a tournament with AJAX support."""
    league = get_object_or_404(League, id=league_id)
    if league.admin != request.user and not request.user.is_superuser:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Åtkomst nekad.'}, status=403)
        messages.error(request, "Åtkomst nekad.")
        return redirect('pool_admin_dashboard', league_id=league_id)

    tournament = get_object_or_404(Tournament, id=tournament_id)
    player = get_object_or_404(User, id=user_id)

    # Ensure tournament is active in this pool when connecting players
    league.tournaments.add(tournament)

    if player in tournament.players.all():
        tournament.players.remove(player)
        enrolled = False
        msg = f"{player.get_full_name() or player.email} har tagits bort från {tournament.name}."
    else:
        tournament.players.add(player)
        enrolled = True
        msg = f"{player.get_full_name() or player.email} har lagts till i {tournament.name}."

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'enrolled': enrolled,
            'enrolled_count': tournament.players.count(),
            'message': msg,
            'user_id': player.id,
            'user_name': player.get_full_name() or player.email,
            'user_email': player.email,
            'is_admin': player == league.admin
        })

    messages.success(request, msg)
    return redirect('pool_admin_tournament_config', league_id=league.id, tournament_id=tournament.id)


@login_required
@require_POST
def update_pool_branding_view(request, league_id):
    """Updates pool logo, name, description, and primary accent color."""
    league = get_object_or_404(League, id=league_id)
    if league.admin != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("Åtkomst nekad.")

    pool_name = request.POST.get('pool_name', '').strip()
    invite_code = request.POST.get('invite_code', '').strip().upper()
    description = request.POST.get('description', '').strip()
    primary_color = request.POST.get('primary_color', '#10b981').strip()

    if pool_name:
        league.name = pool_name
    if invite_code:
        # Check uniqueness if changed
        if League.objects.filter(invite_code=invite_code).exclude(id=league.id).exists():
            messages.error(request, f"Pool ID '{invite_code}' används redan av en annan pool. Välj en annan unik kod.")
            return redirect('pool_admin_dashboard', league_id=league.id)
        league.invite_code = invite_code
    
    league.description = description
    league.primary_color = primary_color

    if 'logo' in request.FILES:
        league.logo = request.FILES['logo']

    league.save()
    messages.success(request, "Poolens inställningar och logotyp har uppdaterats!")
    return redirect('pool_admin_dashboard', league_id=league.id)


@login_required
@require_POST
def pool_admin_add_player_view(request, league_id):
    """Creates a new player account directly and adds them to the pool (and optionally tournament)."""
    from django.contrib.auth.models import User as DjangoUser
    from django.urls import reverse
    league = get_object_or_404(League, id=league_id)
    if league.admin != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("Åtkomst nekad.")

    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    email = request.POST.get('email', '').strip().lower()
    tournament_id = request.POST.get('tournament_id')

    if not first_name or not email:
        messages.error(request, "Förnamn och e-post krävs.")
        if tournament_id:
            return redirect(f"{reverse('pool_admin_tournament_config', args=[league.id, tournament_id])}#sec-participants")
        return redirect('pool_admin_dashboard', league_id=league.id)

    # Check if user exists or create new without requiring manual password
    existing_user = User.objects.filter(email__iexact=email).first()
    if existing_user:
        player_user = existing_user
        if first_name and not player_user.first_name:
            player_user.first_name = first_name
        if last_name and not player_user.last_name:
            player_user.last_name = last_name
        player_user.save()
    else:
        username = email.lower()
        player_user = User(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name
        )
        player_user.set_unusable_password()
        player_user.save()
        profile, _ = UserProfile.objects.get_or_create(user=player_user)
        profile.must_set_password = True
        profile.save()

    if tournament_id:
        tournament = get_object_or_404(Tournament, id=tournament_id)
        league.tournaments.add(tournament)
        tournament.players.add(player_user)
        messages.success(request, f"Deltagaren {first_name} ({email}) har skapats och kopplats till {tournament.name}!")
        return redirect(f"{reverse('pool_admin_tournament_config', args=[league.id, tournament.id])}#sec-participants")

    # Add to LeagueMember (only when added at the pool level)
    member, created = LeagueMember.objects.get_or_create(
        league=league,
        player=player_user,
        defaults={'is_verified': True}
    )

    if created:
        messages.success(request, f"Spelaren {first_name} ({email}) har lagts till i poolen!")
    else:
        messages.info(request, f"Spelaren {first_name} ({email}) fanns redan och har säkerställts som deltagare i poolen.")

    return redirect('pool_admin_dashboard', league_id=league.id)


@login_required
@require_POST
def pool_admin_reset_player_password_view(request, league_id, player_id):
    """
    Forces a player to set a new password on their next login and generates a fresh one-click magic link.
    """
    league = get_object_or_404(League, id=league_id)
    if league.admin != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("Åtkomst nekad.")

    player = get_object_or_404(User, id=player_id)
    profile, _ = UserProfile.objects.get_or_create(user=player)
    profile.must_set_password = True
    profile.save()

    from tournament.utils.magic_link import build_magic_login_url
    magic_link = build_magic_login_url(request, player, league.id)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('accept', ''):
        return JsonResponse({
            'success': True,
            'message': f"Inloggningslänk för {player.get_full_name() or player.email} har genererats.",
            'magic_link': magic_link,
            'player_email': player.email,
            'player_name': player.get_full_name() or player.email,
        })

    messages.success(request, f"Inloggningslänk aktiverad för {player.get_full_name() or player.email}.")
    tournament_id = request.POST.get('tournament_id')
    if tournament_id:
        return redirect(f"{reverse('pool_admin_tournament_config', args=[league.id, tournament_id])}#sec-participants")
    return redirect('pool_admin_dashboard', league_id=league.id)


@login_required
@require_POST
def pool_admin_remove_player_view(request, league_id, member_id):
    """Removes a player from the pool."""
    league = get_object_or_404(League, id=league_id)
    if league.admin != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("Åtkomst nekad.")

    member = get_object_or_404(LeagueMember, id=member_id, league=league)
    if member.player == league.admin:
        messages.error(request, "Pool-Admin kan inte tas bort från poolen.")
        return redirect('pool_admin_dashboard', league_id=league.id)

    player_name = member.player.get_full_name() or member.player.email
    member.delete()
    messages.success(request, f"{player_name} har tagits bort från poolen.")
    return redirect('pool_admin_dashboard', league_id=league.id)


@login_required
@require_POST
def pool_admin_add_self_view(request, league_id):
    """Enrolls pool admin as a participating player if needed."""
    league = get_object_or_404(League, id=league_id)
    if league.admin != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("Åtkomst nekad.")

    LeagueMember.objects.get_or_create(league=league, player=request.user, defaults={'is_verified': True})
    messages.success(request, "Du har lagts till som deltagande spelare i din pool!")
    return redirect('pool_admin_dashboard', league_id=league.id)


@login_required
@require_POST
def pool_admin_reset_password_view(request, league_id, member_id):
    """
    Activates mandatory password reset for the player and generates a fresh one-click magic link.
    """
    league = get_object_or_404(League, id=league_id)
    if league.admin != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("Åtkomst nekad.")

    member = get_object_or_404(LeagueMember, id=member_id, league=league)
    player = member.player

    profile, _ = UserProfile.objects.get_or_create(user=player)
    profile.must_set_password = True
    profile.save()

    from tournament.utils.magic_link import build_magic_login_url
    magic_link = build_magic_login_url(request, player, league.id)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('accept', ''):
        return JsonResponse({
            'success': True,
            'message': f"Inloggningslänk för {player.get_full_name() or player.email} har genererats.",
            'magic_link': magic_link,
            'player_email': player.email,
            'player_name': player.get_full_name() or player.email,
        })

    player_name = player.get_full_name() or player.email
    messages.success(request, f"Inloggningslänk för {player_name} är redo. Spelaren uppmanas att välja sitt nya lösenord vid inloggning.")
    return redirect('pool_admin_dashboard', league_id=league.id)


@login_required
@require_POST
def verify_member_view(request, member_id):
    """Toggles member verification status."""
    member = get_object_or_404(LeagueMember, id=member_id)
    if member.league.admin != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("Åtkomst nekad.")

    member.is_verified = not member.is_verified
    member.save()
    status_str = "verifierats" if member.is_verified else "av-verifierats"
    messages.success(request, f"Deltagare {member.player.get_full_name() or member.player.email} har {status_str}.")
    point_system, created = LeaguePointSystem.objects.get_or_create(league=member.league)
    if created and hasattr(member.league.tournaments.first(), 'point_system') and member.league.tournaments.first().point_system:
        t_ps = member.league.tournaments.first().point_system
        point_system.match_correct_1x2 = t_ps.match_correct_1x2
        point_system.match_correct_goals_per_team = t_ps.match_correct_goals_per_team
        point_system.match_correct_total_goals = t_ps.match_correct_total_goals
        point_system.group_correct_placement = t_ps.group_correct_placement
        point_system.group_correct_points = t_ps.group_correct_points
        point_system.group_correct_goals_scored = t_ps.group_correct_goals_scored
        point_system.group_correct_goals_conceded = t_ps.group_correct_goals_conceded
        point_system.group_correct_goal_diff = t_ps.group_correct_goal_diff
        point_system.group_team_qualified = t_ps.group_team_qualified
        point_system.qualifying_table_team_qualified = t_ps.qualifying_table_team_qualified
        point_system.qualifying_table_exact_rank = t_ps.qualifying_table_exact_rank
        point_system.qualifying_table_points = t_ps.qualifying_table_points
        point_system.qualifying_table_goals_scored = t_ps.qualifying_table_goals_scored
        point_system.qualifying_table_goals_conceded = t_ps.qualifying_table_goals_conceded
        point_system.qualifying_table_goal_diff = t_ps.qualifying_table_goal_diff
        point_system.knockout_round_of_32 = t_ps.knockout_round_of_32
        point_system.knockout_round_of_16 = t_ps.knockout_round_of_16
        point_system.knockout_quarterfinal = t_ps.knockout_quarterfinal
        point_system.knockout_semifinal = t_ps.knockout_semifinal
        point_system.knockout_bronze_match = t_ps.knockout_bronze_match
        point_system.knockout_final = t_ps.knockout_final
        point_system.save()
    return redirect('pool_admin_dashboard', league_id=member.league.id)


@login_required
@require_POST
def update_pool_points_view(request, league_id):
    """Updates LeaguePointSystem values for the pool."""
    league = get_object_or_404(League, id=league_id)
    if league.admin != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("Åtkomst nekad.")

    tournament_id = request.POST.get('tournament_id')
    if tournament_id:
        t_obj = Tournament.objects.filter(id=tournament_id).first()
        if t_obj:
            league.tournaments.add(t_obj)

    point_system, _ = LeaguePointSystem.objects.get_or_create(league=league)

    # Match scoring
    point_system.match_correct_1x2 = int(request.POST.get('match_correct_1x2', 4))
    point_system.match_correct_goals_per_team = int(request.POST.get('match_correct_goals_per_team', 2))
    point_system.match_correct_total_goals = int(request.POST.get('match_correct_total_goals', 2))

    # Group scoring
    point_system.group_correct_placement = int(request.POST.get('group_correct_placement', 3))
    point_system.group_correct_points = int(request.POST.get('group_correct_points', 2))
    point_system.group_correct_goals_scored = int(request.POST.get('group_correct_goals_scored', 1))
    point_system.group_correct_goals_conceded = int(request.POST.get('group_correct_goals_conceded', 1))
    point_system.group_correct_goal_diff = int(request.POST.get('group_correct_goal_diff', 1))
    point_system.group_team_qualified = int(request.POST.get('group_team_qualified', 0))

    # Qualifying table
    point_system.qualifying_table_team_qualified = int(request.POST.get('qualifying_table_team_qualified', 5))
    point_system.qualifying_table_exact_rank = int(request.POST.get('qualifying_table_exact_rank', 0))
    point_system.qualifying_table_points = int(request.POST.get('qualifying_table_points', 0))
    point_system.qualifying_table_goals_scored = int(request.POST.get('qualifying_table_goals_scored', 0))
    point_system.qualifying_table_goals_conceded = int(request.POST.get('qualifying_table_goals_conceded', 0))
    point_system.qualifying_table_goal_diff = int(request.POST.get('qualifying_table_goal_diff', 0))

    # Knockout
    point_system.knockout_round_of_32 = int(request.POST.get('knockout_round_of_32', 2))
    point_system.knockout_round_of_16 = int(request.POST.get('knockout_round_of_16', 4))
    point_system.knockout_quarterfinal = int(request.POST.get('knockout_quarterfinal', 6))
    point_system.knockout_semifinal = int(request.POST.get('knockout_semifinal', 8))
    point_system.knockout_bronze_match = int(request.POST.get('knockout_bronze_match', 10))
    point_system.knockout_final = int(request.POST.get('knockout_final', 10))

    point_system.save()
    messages.success(request, "Poängreglerna har sparats för din pool!")
    if tournament_id:
        return redirect('pool_admin_tournament_config', league_id=league.id, tournament_id=tournament_id)
    return redirect('pool_admin_dashboard', league_id=league.id)


@login_required
@require_POST
def add_pool_sidebet_view(request, league_id):
    """Creates a custom Sidebet question for a tournament in the pool."""
    from tournament.models import Sidebet
    league = get_object_or_404(League, id=league_id)
    if league.admin != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("Åtkomst nekad.")

    tournament_id = request.POST.get('tournament_id')
    question = request.POST.get('question', '').strip()
    points = int(request.POST.get('points', 25))
    question_type = request.POST.get('question_type', 'TEXT')

    if not tournament_id or not question:
        messages.error(request, "Vänligen välj en turnering och ange en bonusfråga.")
        return redirect('pool_admin_dashboard', league_id=league.id)

    tournament = get_object_or_404(Tournament, id=tournament_id)
    league.tournaments.add(tournament)
    Sidebet.objects.create(
        tournament=tournament,
        question=question,
        points=points,
        question_type=question_type
    )

    messages.success(request, f"Egen bonusfråga '{question}' ({points}p) har skapats för {tournament.name}!")
    return redirect('pool_admin_tournament_config', league_id=league.id, tournament_id=tournament.id)


@login_required
@require_POST
def toggle_tournament_submission_verification_view(request, league_id, tournament_id, user_id):
    """Allows Pool Admin to toggle verification and lock-in of a player's predictions for a tournament."""
    from django.urls import reverse
    from tournament.services.cache_service import invalidate_tournament_cache
    
    league = get_object_or_404(League, id=league_id)
    if league.admin != request.user and not request.user.is_superuser:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Åtkomst nekad.'}, status=403)
        return HttpResponseForbidden("Åtkomst nekad.")

    tournament = get_object_or_404(Tournament, id=tournament_id)
    player = get_object_or_404(User, id=user_id)

    submission, created = TournamentSubmission.objects.get_or_create(
        tournament=tournament,
        player=player,
        defaults={'is_saved': True, 'is_verified': True}
    )
    if not created:
        submission.is_verified = not submission.is_verified
        if submission.is_verified:
            submission.is_saved = True
        submission.save()

    invalidate_tournament_cache(tournament.id)
    
    player_name = player.get_full_name() or player.email
    status_str = "låsts och verifierats" if submission.is_verified else "låsts upp"
    msg = f"Tipsen för {player_name} har {status_str}."

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'is_verified': submission.is_verified,
            'message': msg,
            'user_id': player.id
        })

    messages.success(request, msg)
    return redirect(f"{reverse('pool_admin_tournament_config', args=[league.id, tournament.id])}#sec-progress-matrix")


@login_required
def invite_preview_view(request):
    """Interactive preview workbench for testing and refining the HTML and text invite structure."""
    return render(request, 'tournament/invite_preview.html')
