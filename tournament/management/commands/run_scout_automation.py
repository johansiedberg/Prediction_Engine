"""
Management command to run automated AI Tournament Scout scans:
- Monthly general scan (1st of every month): Webscan + Deepscan across AllSportDB, Wikipedia & Gemini.
- Weekly deepscan of tournaments set to 'Under Survey' (WATCHLIST) respecting each tournament's survey_start_date.
- Records all activity to logs/scout_scans.log in a clean tree structure.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from tournament.services.scout_automation_service import ScoutAutomationService


class Command(BaseCommand):
    help = "Runs automated AI Tournament Scout scans (monthly general scan and/or weekly survey deepscan)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            type=str,
            choices=['monthly', 'weekly', 'auto'],
            default='auto',
            help="Type of scan to run: 'monthly' (general discovery + deepscan), 'weekly' (under-survey deepscan), or 'auto' (checks date)."
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help="Force running the monthly scan even if today is not the 1st of the month."
        )
        parser.add_argument(
            '--query',
            type=str,
            default=None,
            help="Optional query or sport filter for the monthly scan."
        )

    def handle(self, *args, **options):
        scan_type = options['type']
        force = options['force']
        query = options['query']
        today = timezone.localdate()

        self.stdout.write(self.style.NOTICE(f"=== Scout Automation Engine [{today}] ==="))

        if scan_type == 'monthly' or (scan_type == 'auto' and (today.day == 1 or force)):
            self.stdout.write(self.style.NOTICE("Executing Monthly General Scan (Webscan + Deepscan)..."))
            res_monthly = ScoutAutomationService.run_monthly_general_scan(custom_query=query)
            self.stdout.write(self.style.SUCCESS(
                f"Monthly Scan Complete: {res_monthly['scanned_count']} scanned, {res_monthly['rejected_count']} rejected/filtered."
            ))
            self.stdout.write(res_monthly.get('log_text', ''))

        if scan_type in ['weekly', 'auto']:
            self.stdout.write(self.style.NOTICE("Executing Weekly Survey Deepscan (Under Survey)..."))
            res_weekly = ScoutAutomationService.run_weekly_survey_scan()
            self.stdout.write(self.style.SUCCESS(
                f"Weekly Survey Scan Complete: {res_weekly['scanned_count']} scanned, {res_weekly['pending_count']} pending start date."
            ))
            self.stdout.write(res_weekly.get('log_text', ''))

        self.stdout.write(self.style.SUCCESS("All scheduled scan tasks finished."))
