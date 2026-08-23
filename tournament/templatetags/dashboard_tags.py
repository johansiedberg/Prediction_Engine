from django import template

register = template.Library()

@register.filter(name='get_item')
def get_item(dictionary, key):
    if dictionary:
        val = dictionary.get(key)
        if val is None and key is not None:
            val = dictionary.get(str(key))
            if val is None:
                try:
                    val = dictionary.get(int(key))
                except (ValueError, TypeError):
                    pass
        return val
    return None

@register.filter(name='split')
def split(value, key="||"):
    """Splits a string by key delimiter."""
    if value:
        return value.split(key)
    return []

@register.simple_tag
def get_dashboard_users():
    return "" # Dummy tag to prevent crashing

@register.simple_tag
def get_dashboard_tournaments():
    return "" # Add this new dummy tag!

@register.filter(name='format_locations')
def format_locations_filter(value):
    """Formats single or multiple tournament locations separated by /."""
    if not value:
        return ""
    from tournament.services.scout_service import normalize_locations
    return normalize_locations(value)

import json
from tournament.country_registry import GLOBAL_COUNTRY_FLAG_MAP

@register.simple_tag
def get_global_country_code_map_json():
    return json.dumps(GLOBAL_COUNTRY_FLAG_MAP)

@register.filter(name='team_badge_url')
def team_badge_url_filter(team_name, sport=""):
    if not team_name:
        return ""
    if hasattr(team_name, 'badge_url'):
        return team_name.badge_url
    from tournament.services.team_badge_service import TeamBadgeService
    res = TeamBadgeService.resolve_team_badge(str(team_name), sport=str(sport), use_gemini_fallback=False)
    return res.badge_url