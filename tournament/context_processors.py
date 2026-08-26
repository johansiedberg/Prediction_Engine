from tournament.models import League, LeagueMember


def league_context(request):
    """Context processor providing user's leagues and currently selected active_league."""
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {
            'user_leagues': [],
            'active_league': None,
            'has_multiple_leagues': False,
        }

    # Avoid DB hits for static/media assets
    if request.path.startswith('/static/') or request.path.startswith('/media/'):
        return {}

    user_memberships = list(
        LeagueMember.objects.filter(player=request.user, league__is_active=True).select_related('league')
    )
    user_leagues = [m.league for m in user_memberships]

    session_league_id = request.session.get('active_league_id')
    active_league = None
    if session_league_id:
        active_league = next((l for l in user_leagues if l.id == session_league_id), None)
    if not active_league and user_leagues:
        active_league = user_leagues[0]
    if not active_league:
        active_league = League.objects.filter(is_active=True).first()

    if request.user.is_superuser:
        managed_leagues = list(League.objects.filter(is_active=True).order_by('name'))
    else:
        managed_leagues = list(League.objects.filter(admin=request.user, is_active=True).order_by('name'))

    return {
        'user_leagues': user_leagues,
        'managed_leagues': managed_leagues,
        'active_league': active_league,
        'has_multiple_leagues': len(user_leagues) > 1,
        'has_managed_leagues': len(managed_leagues) > 0,
    }
