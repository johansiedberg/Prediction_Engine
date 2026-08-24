# tournament/views package - backward-compatible re-exports
# All view functions are re-exported here to maintain 100% backward compatibility
# with urls.py and middleware.py imports.

from tournament.views.auth import CustomLoginView, superuser_or_staff_required, register_view, sso_login_view
from tournament.views.dashboard import dashboard_view, hub_view
from tournament.views.predictions import predictions_view, upload_avatar_view
from tournament.views.leagues import join_league_view, switch_league_view
from tournament.views.engine_admin import (
    engine_admin_root_view,
    engine_admin_login_view,
    engine_admin_logout_view,
    engine_admin_dashboard_view,
    engine_admin_validate_tournament,
    engine_admin_simulate_tournament,
    engine_admin_reset_simulation,
    engine_admin_toggle_publish,
    engine_admin_preview_tournament,
    engine_admin_pool_requests_view,
    engine_admin_approve_pool_request_view,
    engine_admin_reject_pool_request_view,
    engine_admin_update_tournament,
    scout_import_json_view,
    scout_convert_view,
    scout_update_status_view,
    scout_delete_view,
    scout_prospect_json_view,
    scout_scrape_web_view,
    scout_import_wikipedia_view,
    scout_search_specific_view,
    scout_clear_list_view,
    scout_refresh_all_view,
    scout_deep_scan_one_view,
    scout_update_official_url_view,
    scout_update_official_rules_view,
    save_gemini_api_key_view,

    tournament_points_sidebets_get_view,


    tournament_points_save_view,
    tournament_sidebet_save_view,
    tournament_sidebet_delete_view,
    engine_admin_delete_tournament_view,
    engine_admin_tournament_details_view,
    engine_admin_groups_teams_view,
    engine_admin_save_team_view,
    engine_admin_save_match_view,
)

from tournament.views.pool_admin import (
    pool_admin_hub_view,
    create_pool_direct_view,
    request_pool_admin_view,
    pool_admin_dashboard_view,
    pool_admin_tournament_config_view,
    verify_member_view,
    update_pool_branding_view,
    pool_admin_add_player_view,
    pool_admin_remove_player_view,
    update_pool_points_view,
    add_pool_sidebet_view,
    pool_admin_add_self_view,
    pool_admin_reset_password_view,
    toggle_tournament_player_view,
    toggle_pool_tournament_view,
    update_pool_admin_email_view,
)

__all__ = [
    # Auth
    'CustomLoginView',
    'superuser_or_staff_required',
    'register_view',
    # Dashboard
    'dashboard_view',
    'hub_view',
    # Predictions
    'predictions_view',
    'upload_avatar_view',
    # Leagues
    'join_league_view',
    'switch_league_view',
    # Engine Admin (Port 2029)
    'engine_admin_root_view',
    'engine_admin_login_view',
    'engine_admin_logout_view',
    'engine_admin_dashboard_view',
    'engine_admin_validate_tournament',
    'engine_admin_simulate_tournament',
    'engine_admin_reset_simulation',
    'engine_admin_toggle_publish',
    'engine_admin_preview_tournament',
    'engine_admin_pool_requests_view',
    'engine_admin_approve_pool_request_view',
    'engine_admin_reject_pool_request_view',
    'engine_admin_update_tournament',
    # Pool Admin (Port 2028)
    'request_pool_admin_view',
    'pool_admin_dashboard_view',
    'verify_member_view',
    'update_pool_branding_view',
]
