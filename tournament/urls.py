from django.urls import path
from django.contrib.auth.views import LogoutView
from .views import (
    CustomLoginView, dashboard_view, predictions_view, upload_avatar_view,
    hub_view, join_league_view, switch_league_view,
    # Engine Admin (Port 2029)
    create_admin_user_view,
    engine_admin_dashboard_view, engine_admin_validate_tournament,
    engine_admin_simulate_tournament, engine_admin_reset_simulation,
    engine_admin_toggle_publish, engine_admin_preview_tournament,
    engine_admin_pool_requests_view, engine_admin_approve_pool_request_view,
    engine_admin_reject_pool_request_view,
    # Pool Admin (Port 2028)
    request_pool_admin_view, pool_admin_dashboard_view,
    verify_member_view, update_pool_branding_view,
    pool_admin_add_player_view, pool_admin_remove_player_view,
    update_pool_points_view, add_pool_sidebet_view,
    pool_admin_add_self_view, pool_admin_reset_password_view,
    toggle_tournament_player_view,
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

    # Pool Admin Portal (Port 2028)
    path('pool-admin/request/', request_pool_admin_view, name='request_pool_admin'),
    path('pool-admin/<int:league_id>/', pool_admin_dashboard_view, name='pool_admin_dashboard'),
    path('pool-admin/verify-member/<int:member_id>/', verify_member_view, name='verify_member'),
    path('pool-admin/branding/<int:league_id>/', update_pool_branding_view, name='update_pool_branding'),
    path('pool-admin/<int:league_id>/add-player/', pool_admin_add_player_view, name='pool_admin_add_player'),
    path('pool-admin/<int:league_id>/add-self/', pool_admin_add_self_view, name='pool_admin_add_self'),
    path('pool-admin/<int:league_id>/remove-player/<int:member_id>/', pool_admin_remove_player_view, name='pool_admin_remove_player'),
    path('pool-admin/<int:league_id>/reset-password/<int:member_id>/', pool_admin_reset_password_view, name='pool_admin_reset_password'),
    path('pool-admin/<int:league_id>/points/', update_pool_points_view, name='update_pool_points'),
    path('pool-admin/<int:league_id>/sidebet/', add_pool_sidebet_view, name='add_pool_sidebet'),
    path('pool-admin/<int:league_id>/toggle-player/<int:tournament_id>/<int:user_id>/', toggle_tournament_player_view, name='toggle_tournament_player'),

    # Engine Admin Routes (Port 2029)
    path('engine-admin/create-admin-user/', create_admin_user_view, name='create_admin_user'),
    path('engine-admin/', engine_admin_dashboard_view, name='engine_admin'),
    path('engine-admin/validate/<int:tournament_id>/', engine_admin_validate_tournament, name='engine_admin_validate'),
    path('engine-admin/simulate/<int:tournament_id>/', engine_admin_simulate_tournament, name='engine_admin_simulate'),
    path('engine-admin/reset-simulation/<int:tournament_id>/', engine_admin_reset_simulation, name='engine_admin_reset_simulation'),
    path('engine-admin/toggle-publish/<int:tournament_id>/', engine_admin_toggle_publish, name='engine_admin_toggle_publish'),
    path('engine-admin/preview/<int:tournament_id>/', engine_admin_preview_tournament, name='engine_admin_preview'),
    path('engine-admin/pool-requests/', engine_admin_pool_requests_view, name='engine_admin_pool_requests'),
    path('engine-admin/pool-requests/approve/<int:request_id>/', engine_admin_approve_pool_request_view, name='engine_admin_approve_pool_request'),
    path('engine-admin/pool-requests/reject/<int:request_id>/', engine_admin_reject_pool_request_view, name='engine_admin_reject_pool_request'),
]
