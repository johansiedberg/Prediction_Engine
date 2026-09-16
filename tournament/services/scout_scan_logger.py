import datetime
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from django.conf import settings
from django.utils import timezone


class ScoutScanLogger:
    """
    Dedicated logging service for AI Tournament Scout automated & manual runs.
    Outputs a clean, tree-structured format to logs/scout_scans.log:
      - Highest tree structure level: Number of found tournaments
      - Sub-branch: Type of scan
      - Sub-branches: Accepted / Rejected / Pending items with status, grade, and audit reason
    """

    LOG_DIR = Path(settings.BASE_DIR) / "logs"
    LOG_FILE = LOG_DIR / "scout_scans.log"

    @classmethod
    def _ensure_log_file(cls) -> Path:
        cls.LOG_DIR.mkdir(parents=True, exist_ok=True)
        if not cls.LOG_FILE.exists():
            cls.LOG_FILE.touch(exist_ok=True)
        return cls.LOG_FILE

    @classmethod
    def format_tree_entry(
        cls,
        scan_type: str,
        total_found: int,
        accepted_items: Optional[List[Dict[str, Any]]] = None,
        rejected_items: Optional[List[Dict[str, Any]]] = None,
        pending_items: Optional[List[Dict[str, Any]]] = None,
        timestamp: Optional[datetime.datetime] = None,
    ) -> str:
        """
        Formats a scan run into the required tree structure.
        """
        ts = timestamp or timezone.localtime()
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")

        accepted_items = accepted_items or []
        rejected_items = rejected_items or []
        pending_items = pending_items or []

        lines = []
        lines.append("=" * 80)
        # Highest level: Total number of found tournaments
        lines.append(f"[{ts_str}] Hittade: {total_found} turneringar")
        
        # Level 2: Type of scan
        lines.append(f"└── Typ av scanning: {scan_type}")

        sections = []
        if accepted_items:
            sections.append(("Godkända / Accepterade", accepted_items))
        if rejected_items:
            sections.append(("Avvisade / Filtrerade", rejected_items))
        if pending_items:
            sections.append(("Inplanerade / Inväntar startdatum", pending_items))

        if not sections:
            lines.append("    └── Inga turneringar bearbetades i denna scanning.")
        else:
            for idx, (section_title, items) in enumerate(sections):
                is_last_section = (idx == len(sections) - 1)
                sec_prefix = "└──" if is_last_section else "├──"
                pipe_prefix = "   " if is_last_section else "│  "

                lines.append(f"    {sec_prefix} {section_title} ({len(items)})")
                for item_idx, it in enumerate(items):
                    is_last_item = (item_idx == len(items) - 1)
                    item_connector = "└──" if is_last_item else "├──"

                    tag = it.get('grade') or it.get('status') or 'INFO'
                    name = it.get('name', 'Okänd turnering')
                    sport = f" ({it['sport']})" if it.get('sport') else ""
                    details = f" - {it['details']}" if it.get('details') else ""
                    lines.append(f"    {pipe_prefix} {item_connector} [{tag}] {name}{sport}{details}")

        lines.append("=" * 80)
        return "\n".join(lines)

    @classmethod
    def log_scan(
        cls,
        scan_type: str,
        total_found: int,
        accepted_items: Optional[List[Dict[str, Any]]] = None,
        rejected_items: Optional[List[Dict[str, Any]]] = None,
        pending_items: Optional[List[Dict[str, Any]]] = None,
        timestamp: Optional[datetime.datetime] = None,
    ) -> str:
        """
        Formats and appends the scan tree entry to logs/scout_scans.log.
        Returns the formatted string.
        """
        entry_text = cls.format_tree_entry(
            scan_type=scan_type,
            total_found=total_found,
            accepted_items=accepted_items,
            rejected_items=rejected_items,
            pending_items=pending_items,
            timestamp=timestamp,
        )
        log_path = cls._ensure_log_file()
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry_text + "\n\n")
        return entry_text

    @classmethod
    def get_recent_logs(cls, max_lines: int = 200, max_bytes: int = 50000) -> str:
        """
        Returns recent log content for display in Engine Admin.
        """
        log_path = cls._ensure_log_file()
        if not log_path.exists() or log_path.stat().st_size == 0:
            return "Ingen skanningslogg hittades ännu. Kör en månatlig eller veckovis scanning för att generera loggposter."

        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                read_size = min(size, max_bytes)
                f.seek(size - read_size, os.SEEK_SET)
                content = f.read()

            lines = content.splitlines()
            if len(lines) > max_lines:
                lines = lines[-max_lines:]
            return "\n".join(lines)
        except Exception as e:
            return f"Fel vid inläsning av skanningslogg: {str(e)}"
