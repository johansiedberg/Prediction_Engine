import logging
import re
import datetime
from typing import Optional, Dict, Any, List
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class OfficialRegulationsVerifier:
    """
    Automated Ingest & Verifier for Official Tournament Websites & Press Releases.
    Fetches official federation portals (CAF, CONCACAF, UEFA, FIFA, FIBA, etc.), scans for
    official draw dates, draw status, group assignments, qualification pathways, and rule regulations.
    """
    def __init__(self):
        self.headers = {
            'User-Agent': 'PredictionEngine-OfficialVerifier/1.0 (contact@predictionengine.app)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        }

    def ingest_official_page(self, official_url: str, tournament_name: str = "") -> Dict[str, Any]:
        """
        Fetches and performs deep structured ingestion of an official federation page or press release.
        Extracts draw date, draw completion status, group schemes, and advancement pathways.
        """
        if not official_url or not official_url.startswith('http'):
            return {
                'verified': False,
                'status': 'NO_OFFICIAL_URL',
                'reason': 'Ingen officiell webbadress angiven.',
                'draw_date': None,
                'draw_completed': False,
                'groups': [],
                'qualification_pathway': '',
                'official_rules_summary': '',
            }

        try:
            res = requests.get(official_url, headers=self.headers, timeout=12, allow_redirects=True)
            if res.status_code != 200:
                return {
                    'verified': False,
                    'status': f'HTTP_{res.status_code}',
                    'reason': f'Kunde inte nå officiell webbplats (HTTP {res.status_code}).',
                    'draw_date': None,
                    'draw_completed': False,
                    'groups': [],
                }

            content_type = res.headers.get('Content-Type', '').lower()
            is_pdf = 'application/pdf' in content_type or official_url.lower().endswith('.pdf')

            text_content = ''
            if is_pdf:
                import subprocess
                try:
                    proc = subprocess.run(['pdftotext', '-', '-'], input=res.content, capture_output=True, timeout=6)
                    if proc.returncode == 0:
                        text_content = proc.stdout.decode('utf-8', errors='ignore')
                except Exception as pdf_err:
                    logger.warning("PDF text extraction failed for %s: %s", official_url, pdf_err)
                
                if not text_content:
                    text_content = " ".join([m.decode('latin-1', errors='ignore') for m in re.findall(rb'[\x20-\x7E\s]{4,}', res.content)])
            else:
                soup = BeautifulSoup(res.text, 'html.parser')
                # Remove scripts and styles
                for script in soup(["script", "style", "nav", "footer"]):
                    script.extract()
                text_content = soup.get_text(separator='\n')

            clean_text = ' '.join(text_content.split())
            lower_text = clean_text.lower()

            # 1. Extract Draw Date & Status
            draw_date_extracted = None
            draw_completed_flag = False

            from tournament.services.llm_wikipedia_scout import LLMWikipediaScout

            # Patterns for completed draws: "draw took place on 12 February 2026", "draw concluded on 19 Feb", "draw held on..."
            draw_match = re.search(
                r'(?:draw\s+(?:took\s+place|concluded|was\s+held|conducted)\s+(?:on|in)?\s+([0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+(?:\s+[0-9]{4})?|[A-Za-z]+\s+[0-9]{1,2}(?:,\s*[0-9]{4})?))',
                clean_text,
                re.IGNORECASE
            )
            if draw_match:
                draw_date_extracted = LLMWikipediaScout._parse_date_string(draw_match.group(1))
                draw_completed_flag = True

            # Patterns for future/scheduled draws: "draw will take place on 15 December 2026", "draw scheduled for..."
            if not draw_date_extracted:
                sched_match = re.search(
                    r'(?:draw\s+(?:will\s+take\s+place|is\s+scheduled|will\s+be\s+held)\s+(?:on|in|for)?\s+([0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+(?:\s+[0-9]{4})?|[A-Za-z]+\s+[0-9]{1,2}(?:,\s*[0-9]{4})?))',
                    clean_text,
                    re.IGNORECASE
                )
                if sched_match:
                    draw_date_extracted = LLMWikipediaScout._parse_date_string(sched_match.group(1))
                    draw_completed_flag = False

            # Check general text signals
            if "draw concluded" in lower_text or "draw was completed" in lower_text or "following the draw" in lower_text:
                draw_completed_flag = True

            # 2. Extract Groups & Teams if explicitly listed in text/tables
            groups_extracted = []
            group_blocks = re.findall(r'Group\s+([A-P1-9])\s*:\s*(.*?)(?=(?:Group\s+[A-P1-9]\s*:|\n|\r|\.|$))', text_content, re.IGNORECASE)
            for grp_letter, teams_blob in group_blocks:
                # Split teams by comma, slash, or dashes
                teams = [t.strip() for t in re.split(r'[,/–\t]', teams_blob) if len(t.strip()) > 2]
                if teams:
                    groups_extracted.append({
                        'name': f"Group {grp_letter.upper()}",
                        'teams': [{'name': LLMWikipediaScout._clean_team_name(t)} for t in teams if LLMWikipediaScout._clean_team_name(t)]
                    })

            # 3. Extract Rules / Pathway summary
            pathway_summary = ""
            if "qualification" in lower_text or "pathway" in lower_text or "advance" in lower_text:
                pathway_matches = re.findall(r'([^.\n]*?(?:qualif\w+|advance\w+|pathway|promotion)[^.\n]*?\.)', clean_text, re.IGNORECASE)
                if pathway_matches:
                    pathway_summary = " ".join(pathway_matches[:3]).strip()

            is_doc_portal = 'documents.uefa.com' in official_url.lower() or 'regulations' in official_url.lower() or 'rulebook' in official_url.lower()
            has_groups = bool(groups_extracted or re.search(r'\b(group|groups|grupp|grupper)\b', lower_text)) or is_doc_portal
            has_knockout = bool(re.search(r'\b(knockout|quarterfinal|semifinal|final|slutspel)\b', lower_text))
            has_regs = bool(re.search(r'\b(regulation|regulations|rule|rules|format|standings|reglemente)\b', lower_text)) or is_doc_portal
            verified = (has_groups or has_knockout) and (has_regs or bool(draw_date_extracted))

            return {
                'verified': verified,
                'status': 'VERIFIED' if verified else 'PARTIAL_VERIFICATION',
                'url': official_url,
                'draw_date': draw_date_extracted,
                'draw_completed': draw_completed_flag,
                'groups': groups_extracted,
                'qualification_pathway': pathway_summary,
                'has_groups_mention': has_groups,
                'has_knockout_mention': has_knockout,
                'has_regulations_mention': has_regs,
                'reason': 'Officiell webbplats och pressmeddelande verifierat.' if verified else 'Officiell webbplats åtkomlig.'
            }

        except Exception as e:
            logger.error("Error ingesting official URL '%s': %s", official_url, e)
            return {
                'verified': False,
                'status': 'FETCH_ERROR',
                'reason': f'Nätverksfel vid granskning av officiell sida: {str(e)}',
                'draw_date': None,
                'draw_completed': False,
                'groups': [],
            }

    def verify_official_regulations(self, official_url: str, tournament_name: str = "") -> Dict[str, Any]:
        """
        Backwards-compatible wrapper that delegates to ingest_official_page.
        """
        return self.ingest_official_page(official_url, tournament_name)
