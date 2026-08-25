"""
Management command to run the Google Gemini AI Search Grounded Tournament Scout.
Discovers upcoming tournaments across 3 pillars:
1. Premier Continental Club Tournaments
2. Continental & Global Qualifiers
3. Major National Team Finals
"""

from django.core.management.base import BaseCommand
from tournament.services.scout_service import fetch_and_ingest_gemini_ai_tournaments


class Command(BaseCommand):
    help = "Discovers and ingests upcoming tournaments via Google Gemini AI with Google Search Grounding."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=15,
            help="Number of tournaments to discover (default: 15)",
        )
        parser.add_argument(
            "--query",
            type=str,
            default="",
            help="Optional custom search query or sport filter",
        )

    def handle(self, *args, **options):
        count = options["count"]
        query = options["query"] or None

        self.stdout.write(self.style.NOTICE(f"Starting Gemini AI Search Grounded Scout (Target: {count} tournaments)..."))
        created, updated, prospects = fetch_and_ingest_gemini_ai_tournaments(count=count, custom_query=query)

        self.stdout.write(
            self.style.SUCCESS(
                f"Scout Completed: {created} new prospects created, {updated} updated (Total: {len(prospects)})."
            )
        )
        for p in prospects:
            dates = f"{p.start_date or 'TBD'} to {p.end_date or 'TBD'}"
            self.stdout.write(f"  • [{p.sport}] {p.name} ({dates}) - Host: {p.host_country or 'Unknown'}")
