# tournament/views/engine_admin/__init__.py
# Backward-compatible re-exports from decomposed modules

from tournament.views.engine_admin.dashboard import (
    engine_admin_root_view,
    engine_admin_login_view,
    engine_admin_logout_view,
    engine_admin_dashboard_view,
)
from tournament.views.engine_admin.tournaments import (
    engine_admin_validate_tournament,
    engine_admin_simulate_tournament,
    engine_admin_reset_simulation,
    engine_admin_toggle_publish,
    engine_admin_preview_tournament,
    engine_admin_delete_tournament_view,
    engine_admin_tournament_details_view,
    engine_admin_update_tournament,
    engine_admin_groups_teams_view,
    engine_admin_save_team_view,
    engine_admin_save_match_view,
)
from tournament.views.engine_admin.scout import (
    scout_import_json_view,
    scout_search_specific_view,
    scout_import_wikipedia_view,
    scout_convert_view,
    scout_update_status_view,
    scout_delete_view,
    scout_prospect_json_view,
    scout_scrape_web_view,
    _run_deep_scan_on_prospect,
    scout_deep_scan_one_view,
    scout_update_official_url_view,
    scout_update_official_rules_view,
    scout_clear_list_view,
    scout_refresh_all_view,
)
from tournament.views.engine_admin.config import (
    engine_admin_pool_requests_view,
    engine_admin_approve_pool_request_view,
    engine_admin_reject_pool_request_view,
    tournament_points_sidebets_get_view,
    tournament_points_save_view,
    tournament_sidebet_save_view,
    tournament_sidebet_delete_view,
    save_gemini_api_key_view,
)
