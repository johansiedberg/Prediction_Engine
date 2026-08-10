import re

def get_tournament_checklist_status(tour):
    teams = list(tour.teams.all())
    teams_cnt = len(teams)
    has_alerts = False
    has_warnings = False

    if teams_cnt == 0:
        has_alerts = True
    else:
        placeholder_teams = [t.name for t in teams if re.match(r'^([A-L][1-8]|Lag\s*\d+|Team\s*\d+)$', t.name.strip(), re.IGNORECASE)]
        if placeholder_teams:
            has_alerts = True

    if not hasattr(tour, 'point_system') or not tour.point_system:
        has_alerts = True

    matches = tour.matches.all()
    matches_cnt = matches.count()
    if matches_cnt == 0:
        has_alerts = True
    else:
        dates = [m.date_time for m in matches if m.date_time is not None]
        if len(dates) == 0 or len(set(dates)) == 1 or len(dates) < matches_cnt:
            has_warnings = True

    if has_alerts:
        return {'status': 'ALERT', 'emoji': '🚨', 'badge_class': 'bg-danger text-white border border-light', 'title': '🚨 ALERT: Innehåller placeholders eller saknar krav'}
    elif has_warnings:
        return {'status': 'WARNING', 'emoji': '⚠️', 'badge_class': 'bg-warning text-dark border border-dark', 'title': '⚠️ VARNING: Mindre datum/schemaanmärkningar'}
    else:
        return {'status': 'READY', 'emoji': '✅', 'badge_class': 'bg-success text-white border border-light', 'title': '✅ READY: Turneringen är 100% redo för publicering'}


def get_tournament_total_status(tour, chk_status):
    """
    Computes total status for Engine Admin tournament card pill banner:
    Normal faded translucent background with vibrant text and subtle border.
    1. BLOCKED (Faded Red, red text): If Checklist has ALERTS! (Cannot activate)
    2. ACTIVE (Faded Green, green text): If Published & Active. (Possible to Deactivate)
    3. PAUSED / DEACTIVATED (Faded Blue, blue text): If manually paused/deactivated. (Possible to Activate)
    4. DRAFT / TESTING (Faded Orange, orange text): If Draft / Testing mode. (Possible to Activate)
    """
    if chk_status['status'] == 'ALERT':
        return {
            'code': 'BLOCKED',
            'label': 'BLOCKERAD (ALERTS FINNS 🚨)',
            'style': 'background-color: rgba(220, 53, 69, 0.15) !important; color: #ff6b6b !important; border: 1px solid rgba(220, 53, 69, 0.3) !important; font-weight: 700;',
            'badge_text': 'BLOCKERAD',
            'can_activate': False,
        }
    elif tour.is_active:
        return {
            'code': 'ACTIVE',
            'label': 'PUBLISERAD / AKTIV',
            'style': 'background-color: rgba(25, 135, 84, 0.15) !important; color: #2eca8b !important; border: 1px solid rgba(25, 135, 84, 0.3) !important; font-weight: 700;',
            'badge_text': 'PUBLISERAD / AKTIV',
            'can_activate': True,
        }
    elif getattr(tour, 'is_paused', False):
        return {
            'code': 'PAUSED',
            'label': 'PAUSAD / AVAKTIVERAD',
            'style': 'background-color: rgba(13, 110, 253, 0.15) !important; color: #4dabf7 !important; border: 1px solid rgba(13, 110, 253, 0.3) !important; font-weight: 700;',
            'badge_text': 'PAUSAD / AVAKTIVERAD',
            'can_activate': True,
        }
    else:
        return {
            'code': 'DRAFT',
            'label': 'UTKAST / TESTLÄGE',
            'style': 'background-color: rgba(253, 126, 20, 0.15) !important; color: #ff922b !important; border: 1px solid rgba(253, 126, 20, 0.3) !important; font-weight: 700;',
            'badge_text': 'UTKAST / TESTLÄGE',
            'can_activate': True,
        }
