# Predictions views - predictions submission and avatar upload
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404

from tournament.models import (
    Match, MatchPrediction, TournamentSubmission, Sidebet, SidebetAnswer, UserProfile
)


@login_required(login_url='/')
def predictions_view(request):
    if request.method == 'POST':
        from tournament.views.dashboard import dashboard_view
        return dashboard_view(request)
    active_tab = request.GET.get('active_tab', '')
    if active_tab:
        return redirect(f'/dashboard/?tab=predictions&active_tab={active_tab}')
    return redirect('/dashboard/?tab=predictions')


@login_required(login_url='/')
def upload_avatar_view(request):
    if request.method == 'POST' and request.FILES.get('avatar'):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        profile.avatar = request.FILES['avatar']
        profile.save()
        messages.success(request, 'Din profilbild har uppdaterats!')
    return redirect(request.META.get('HTTP_REFERER', '/dashboard/'))
