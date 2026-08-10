from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from tournament.models import League, LeagueMember, Tournament, PoolAdminRequest, MasterEvent
from tournament.services.pool_admin_service import get_player_progress_matrix

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
            uname = request.POST.get('username', '').strip()
            pwd = request.POST.get('password', '').strip()
            user = authenticate(request, username=uname, password=pwd)
            if user is None:
                # Try by email
                user_obj = DjangoUser.objects.filter(email__iexact=uname).first()
                if user_obj:
                    user = authenticate(request, username=user_obj.username, password=pwd)

            if user is not None:
                login(request, user)
                # Check if user owns a league
                user_league = League.objects.filter(admin=user).first()
                if user_league:
                    messages.success(request, f"Välkommen tillbaka, {user.first_name or user.username}!")
                    return redirect('pool_admin_dashboard', league_id=user_league.id)
                else:
                    messages.info(request, "Välkommen! Din Pool-Admin ansökan behandlas eller har inte aktiverats än.")
                    return redirect('request_pool_admin')
            else:
                messages.error(request, "Felaktig e-post/användarnamn eller lösenord.")
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
                    base_username = email.split('@')[0]
                    username = base_username
                    counter = 1
                    while DjangoUser.objects.filter(username=username).exists():
                        username = f"{base_username}{counter}"
                        counter += 1

                    user = DjangoUser.objects.create_user(
                        username=username,
                        email=email,
                        password=password,
                        first_name=first_name,
                        last_name=last_name or ''
                    )
                login(request, user)

            master_event = None
            if master_event_id:
                master_event = MasterEvent.objects.filter(id=master_event_id).first()

            PoolAdminRequest.objects.create(
                user=user,
                pool_name=pool_name,
                description=description,
                master_event=master_event
            )
            messages.success(request, f"Tack {user.first_name}! Din ansökan om att starta '{pool_name}' har skickats in och behandlas nu av Engine-Admin.")
            return redirect('hub')

    master_events = MasterEvent.objects.filter(is_active=True)
    return render(request, 'tournament/request_pool_admin.html', {
        'master_events': master_events,
        'pending_request': pending_request
    })

@login_required
def pool_admin_dashboard_view(request, league_id):
    from tournament.models import LeaguePointSystem, Sidebet
    league = get_object_or_404(League, id=league_id)

    if league.admin != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("Du har inte behörighet att administrera denna liga.")

    active_tournaments = Tournament.objects.filter(is_active=True)

    # Selected tournament selection: Pool Admin MUST explicitly choose a Tournament first!
    selected_tournament_id = request.GET.get('tournament_id')
    selected_tournament = None
    if selected_tournament_id:
        selected_tournament = active_tournaments.filter(id=selected_tournament_id).first()

    point_system, _ = LeaguePointSystem.objects.get_or_create(league=league)

    if selected_tournament:
        sidebets = Sidebet.objects.filter(tournament=selected_tournament)
        players_data = get_player_progress_matrix(league, selected_tournament)
        enrolled_user_ids = set(selected_tournament.players.values_list('id', flat=True))
    else:
        sidebets = Sidebet.objects.none()
        players_data = []
        enrolled_user_ids = set()

    # Check if admin is enrolled as player
    is_admin_enrolled = league.members.filter(player=request.user).exists()

    context = {
        'league': league,
        'point_system': point_system,
        'active_tournaments': active_tournaments,
        'selected_tournament': selected_tournament,
        'master_events': MasterEvent.objects.filter(is_active=True),
        'sidebets': sidebets,
        'players_data': players_data,
        'is_admin_enrolled': is_admin_enrolled,
        'enrolled_user_ids': enrolled_user_ids,
        'members': league.members.all().select_related('player')
    }
    return render(request, 'tournament/pool_admin.html', context)


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

    if player in tournament.players.all():
        tournament.players.remove(player)
        enrolled = False
        msg = f"{player.get_full_name() or player.username} har tagits bort från {tournament.name}."
    else:
        tournament.players.add(player)
        enrolled = True
        msg = f"{player.get_full_name() or player.username} har lagts till i {tournament.name}."

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'enrolled': enrolled,
            'enrolled_count': tournament.players.count(),
            'message': msg,
            'user_id': player.id,
            'user_name': player.get_full_name() or player.username,
            'user_email': player.email,
            'is_admin': player == league.admin
        })

    messages.success(request, msg)
    return redirect(f"/pool-admin/{league.id}/?tournament_id={tournament.id}#sec-participants")


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
    """Creates a new player account directly and adds them to the pool."""
    from django.contrib.auth.models import User as DjangoUser
    league = get_object_or_404(League, id=league_id)
    if league.admin != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("Åtkomst nekad.")

    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    email = request.POST.get('email', '').strip().lower()
    password = request.POST.get('password', '').strip()

    if not first_name or not email or not password:
        messages.error(request, "Förnamn, e-post och lösenord krävs.")
        return redirect('pool_admin_dashboard', league_id=league.id)

    # Check if user exists or create new
    existing_user = DjangoUser.objects.filter(email__iexact=email).first()
    if existing_user:
        player_user = existing_user
    else:
        base_username = email.split('@')[0]
        username = base_username
        counter = 1
        while DjangoUser.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        player_user = DjangoUser.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name
        )

    # Add to LeagueMember
    member, created = LeagueMember.objects.get_or_create(
        league=league,
        player=player_user,
        defaults={'is_verified': True}
    )

    if created:
        messages.success(request, f"Spelaren {first_name} ({email}) har skapats och lagts till i poolen!")
    else:
        messages.info(request, f"Spelaren {first_name} ({email}) fanns redan och har säkerställts som deltagare i poolen.")

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

    player_name = member.player.get_full_name() or member.player.username
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
    """Resets a player's password and generates mailto link context."""
    league = get_object_or_404(League, id=league_id)
    if league.admin != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("Åtkomst nekad.")

    member = get_object_or_404(LeagueMember, id=member_id, league=league)
    new_pwd = request.POST.get('new_password', '').strip()

    if not new_pwd:
        messages.error(request, "Vänligen ange ett nytt lösenord.")
        return redirect('pool_admin_dashboard', league_id=league.id)

    member.player.set_password(new_pwd)
    member.player.save()

    player_name = member.player.get_full_name() or member.player.username
    messages.success(request, f"Lösenordet för {player_name} har återställts till '{new_pwd}'. Klicka på e-postikonen bredvid deltagaren för att skicka inloggningsuppgifterna!")
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
    messages.success(request, f"Deltagare {member.player.username} har {status_str}.")
    return redirect('pool_admin_dashboard', league_id=member.league.id)


@login_required
@require_POST
def update_pool_points_view(request, league_id):
    """Updates LeaguePointSystem values for the pool."""
    league = get_object_or_404(League, id=league_id)
    if league.admin != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("Åtkomst nekad.")

    point_system, _ = LeaguePointSystem.objects.get_or_create(league=league)

    # Match scoring
    point_system.match_correct_1x2 = int(request.POST.get('match_correct_1x2', 3))
    point_system.match_correct_goals_per_team = int(request.POST.get('match_correct_goals_per_team', 3))
    point_system.match_correct_total_goals = int(request.POST.get('match_correct_total_goals', 1))

    # Group scoring
    point_system.group_correct_placement = int(request.POST.get('group_correct_placement', 2))
    point_system.group_correct_points = int(request.POST.get('group_correct_points', 1))
    point_system.group_correct_goals_scored = int(request.POST.get('group_correct_goals_scored', 1))
    point_system.group_correct_goals_conceded = int(request.POST.get('group_correct_goals_conceded', 1))
    point_system.group_correct_goal_diff = int(request.POST.get('group_correct_goal_diff', 1))
    point_system.group_team_qualified = int(request.POST.get('group_team_qualified', 0))

    # Qualifying table
    point_system.qualifying_table_team_qualified = int(request.POST.get('qualifying_table_team_qualified', 5))

    # Knockout
    point_system.knockout_round_of_16 = int(request.POST.get('knockout_round_of_16', 3))
    point_system.knockout_quarterfinal = int(request.POST.get('knockout_quarterfinal', 4))
    point_system.knockout_semifinal = int(request.POST.get('knockout_semifinal', 5))
    point_system.knockout_final = int(request.POST.get('knockout_final', 8))

    point_system.save()
    messages.success(request, "Poängreglerna har sparats för din pool!")
    return redirect(f"/pool-admin/{league.id}/#sec-set-points")


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
    points = int(request.POST.get('points', 5))
    question_type = request.POST.get('question_type', 'TEXT')

    if not tournament_id or not question:
        messages.error(request, "Vänligen välj en turnering och ange en bonusfråga.")
        return redirect('pool_admin_dashboard', league_id=league.id)

    tournament = get_object_or_404(Tournament, id=tournament_id)
    Sidebet.objects.create(
        tournament=tournament,
        question=question,
        points=points,
        question_type=question_type
    )

    messages.success(request, f"Egen bonusfråga '{question}' ({points}p) har skapats för {tournament.name}!")
    return redirect(f"/pool-admin/{league.id}/?tournament_id={tournament.id}#sec-sidebets")
