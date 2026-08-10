# League management views - join and switch leagues
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404

from tournament.models import League, LeagueMember


@login_required
def join_league_view(request):
    if request.method == 'POST':
        invite_code = request.POST.get('invite_code', '').strip().upper()
        if invite_code:
            league = League.objects.filter(invite_code__iexact=invite_code, is_active=True).first()
            if league:
                member, created = LeagueMember.objects.get_or_create(league=league, player=request.user)
                request.session['active_league_id'] = league.id
                messages.success(request, f"Du gick med i vängruppen {league.name}!")
            else:
                messages.error(request, f"Koden '{invite_code}' är ogiltig eller avslutad.")
        else:
            messages.error(request, "Vänligen fyll i en vängruppskod.")
    return redirect(request.META.get('HTTP_REFERER', '/dashboard/?tab=predictions'))


@login_required
def switch_league_view(request, league_id):
    league = get_object_or_404(League, id=league_id, is_active=True)
    if LeagueMember.objects.filter(league=league, player=request.user).exists() or request.user.is_superuser:
        request.session['active_league_id'] = league.id
        messages.info(request, f"Växlade till vängruppen {league.name}")
    else:
        messages.error(request, "Du är inte medlem i den vängruppen.")
    return redirect(request.META.get('HTTP_REFERER', '/dashboard/?tab=predictions'))
