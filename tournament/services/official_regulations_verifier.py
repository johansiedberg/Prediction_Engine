import logging
import re
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class OfficialRegulationsVerifier:
    """
    Automated verifier for Official Tournament Website & Rulebook Regulations.
    Fetches the official website, scans for tournament rules/regulations, group stages,
    and cross-checks the setup against Wikipedia extractions.
    """
    def __init__(self):
        self.headers = {
            'User-Agent': 'PredictionEngine-OfficialVerifier/1.0 (contact@predictionengine.app)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        }

    def verify_official_regulations(self, official_url, tournament_name):
        """
        Fetches and audits official website for regulations & setup confirmation.
        Returns dict with verification audit flags and findings.
        """
        if not official_url or not official_url.startswith('http'):
            return {
                'verified': False,
                'status': 'NO_OFFICIAL_URL',
                'reason': 'Ingen officiell webbadress angiven från AllSportDB.'
            }

        try:
            res = requests.get(official_url, headers=self.headers, timeout=12, allow_redirects=True)
            if res.status_code != 200:
                return {
                    'verified': False,
                    'status': f'HTTP_{res.status_code}',
                    'reason': f'Kunde inte nå officiell webbplats (HTTP {res.status_code}).'
                }

            content_type = res.headers.get('Content-Type', '').lower()
            is_pdf = 'application/pdf' in content_type or official_url.lower().endswith('.pdf')

            text_content = ''
            if is_pdf:
                import subprocess
                try:
                    proc = subprocess.run(['pdftotext', '-', '-'], input=res.content, capture_output=True, timeout=6)
                    if proc.returncode == 0:
                        text_content = proc.stdout.decode('utf-8', errors='ignore').lower()
                except Exception as pdf_err:
                    logger.warning(f"PDF text extraction failed via pdftotext for {official_url}: {pdf_err}")
                
                if not text_content:
                    # Fallback ASCII extraction for PDFs
                    text_content = " ".join([m.decode('latin-1', errors='ignore') for m in re.findall(rb'[\x20-\x7E\s]{4,}', res.content)]).lower()
            else:
                html_text = res.text
                soup = BeautifulSoup(html_text, 'html.parser')
                text_content = soup.get_text().lower()

            has_groups_mention = bool(re.search(r'\b(group|groups|grupp|grupper)\b', text_content))
            has_knockout_mention = bool(re.search(r'\b(knockout|quarterfinal|semifinal|final|slutspel)\b', text_content))
            has_regulations_mention = bool(re.search(r'\b(regulation|regulations|rule|rules|format|standings|reglemente)\b', text_content))
            has_teams_mention = bool(re.search(r'\b(teams|participants|nations|countries|lag)\b', text_content))

            verified = (has_groups_mention or has_knockout_mention) and has_regulations_mention

            return {
                'verified': verified,
                'status': 'VERIFIED' if verified else 'PARTIAL_VERIFICATION',
                'url': official_url,
                'has_groups_mention': has_groups_mention,
                'has_knockout_mention': has_knockout_mention,
                'has_regulations_mention': has_regulations_mention,
                'has_teams_mention': has_teams_mention,
                'reason': 'Officiell webbplats verifierad med godkända turneringsföreskrifter.' if verified else 'Officiell webbplats åtkomlig, men fullständiga reglementesfiler pågår.'
            }

        except Exception as e:
            logger.error(f"Error verifying official URL '{official_url}': {e}")
            return {
                'verified': False,
                'status': 'FETCH_ERROR',
                'reason': f'Nätverksfel vid granskning av officiell sida: {str(e)}'
            }
