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
    Computes total status for Engine Admin tournament card pill banner
    adhering to Monochromatic Tonal Contrast Standards:
    1. BLOCKED (Red monochromatic): If Checklist has ALERTS! (Cannot activate)
    2. ACTIVE (Green monochromatic): If Published & Active. (Possible to Deactivate)
    3. PAUSED / DEACTIVATED (Blue monochromatic): If manually paused/deactivated. (Possible to Activate)
    4. DRAFT / CONFIGURATION (Amber monochromatic): If Draft / Pre-publication mode. (Possible to Activate)
    """
    if chk_status['status'] == 'ALERT':
        return {
            'code': 'BLOCKED',
            'label': 'EJ REDO FÖR PUBLICERING (ALERTS 🚨)',
            'style': 'background-color: #450A0A !important; color: #FEE2E2 !important; border: 1px solid #B91C1C !important; font-weight: 700;',
            'badge_text': 'EJ REDO',
            'can_activate': False,
        }
    elif tour.is_active:
        return {
            'code': 'ACTIVE',
            'label': 'PUBLICERAD / AKTIV',
            'style': 'background-color: #052E16 !important; color: #DCFCE7 !important; border: 1px solid #15803D !important; font-weight: 700;',
            'badge_text': 'PUBLICERAD / AKTIV',
            'can_activate': True,
        }
    elif getattr(tour, 'is_paused', False):
        return {
            'code': 'PAUSED',
            'label': 'PAUSAD / AVAKTIVERAD',
            'style': 'background-color: #172554 !important; color: #DBEAFE !important; border: 1px solid #1D4ED8 !important; font-weight: 700;',
            'badge_text': 'PAUSAD',
            'can_activate': True,
        }
    else:
        return {
            'code': 'DRAFT',
            'label': 'UTKAST / EJ PUBLICERAD',
            'style': 'background-color: #451A03 !important; color: #FEF3C7 !important; border: 1px solid #B45309 !important; font-weight: 700;',
            'badge_text': 'UTKAST',
            'can_activate': True,
        }
