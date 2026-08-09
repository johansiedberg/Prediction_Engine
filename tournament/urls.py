from django.urls import path
from django.contrib.auth.views import LogoutView
from .views import (
    CustomLoginView, dashboard_view, predictions_view, upload_avatar_view,
    hub_view, join_league_view, switch_league_view,
    engine_admin_dashboard_view, engine_admin_validate_tournament,
    engine_admin_simulate_tournament, engine_admin_reset_simulation,
    engine_admin_toggle_publish, engine_admin_preview_tournament
)

urlpatterns = [
    path('', CustomLoginView.as_view(), name='login'),
    path('hub/', hub_view, name='hub'),
    path('dashboard/', dashboard_view, name='dashboard'),
    path('predictions/', predictions_view, name='predictions'),
    path('profile/avatar/', upload_avatar_view, name='upload_avatar'),
    path('league/join/', join_league_view, name='join_league'),
    path('league/switch/<int:league_id>/', switch_league_view, name='switch_league'),
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),

    # Engine Admin Routes
    path('engine-admin/', engine_admin_dashboard_view, name='engine_admin'),
    path('engine-admin/validate/<int:tournament_id>/', engine_admin_validate_tournament, name='engine_admin_validate'),
    path('engine-admin/simulate/<int:tournament_id>/', engine_admin_simulate_tournament, name='engine_admin_simulate'),
    path('engine-admin/reset-simulation/<int:tournament_id>/', engine_admin_reset_simulation, name='engine_admin_reset_simulation'),
    path('engine-admin/toggle-publish/<int:tournament_id>/', engine_admin_toggle_publish, name='engine_admin_toggle_publish'),
    path('engine-admin/preview/<int:tournament_id>/', engine_admin_preview_tournament, name='engine_admin_preview'),
]

