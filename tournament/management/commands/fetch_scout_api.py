"""
Management command to pull tournaments from an external REST API (e.g. Google AI Studio Agent or Local Proxy).
Validates each tournament using Pydantic TournamentSchema and ingests into Prediction Engine.
"""

from django.core.management.base import BaseCommand
from tournament.services.scout_service import fetch_and_ingest_from_api


class Command(BaseCommand):
    help = "Pulls and ingests tournaments from an external REST API endpoint via strict Pydantic validation."

    def add_arguments(self, parser):
        parser.add_argument(
            "--url",
            type=str,
            default="http://localhost:3000/api/tournaments",
            help="External API URL to query (default: http://localhost:3000/api/tournaments)",
        )
        parser.add_argument(
            "--min-runway",
            type=int,
            default=30,
            help="Minimum runway buffer in days (default: 30)",
        )
        parser.add_argument(
            "--sport",
            type=str,
            default="",
            help="Optional sport filter parameter (e.g. Football, Basketball, Ice Hockey)",
        )
        parser.add_argument(
            "--save-files",
            action="store_true",
            help="Save individual validated JSON files to disk",
        )
        parser.add_argument(
            "--output-dir",
            type=str,
            default="tournaments",
            help="Directory to save individual JSON files (default: tournaments)",
        )

    def handle(self, *args, **options):
        api_url = options["url"]
        min_runway = options["min_runway"]
        sport = options["sport"] or None
        save_files = options["save_files"]
        output_dir = options["output_dir"]

        self.stdout.write(
            self.style.NOTICE(
                f"Querying External Scout API: {api_url} (minRunway={min_runway}d, sport={sport or 'All'})..."
            )
        )

        try:
            created, updated, prospects = fetch_and_ingest_from_api(
                api_url=api_url,
                min_runway=min_runway,
                sport=sport,
                save_json_files=save_files,
                output_dir=output_dir,
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ REST API Ingestion Completed: {created} created, {updated} updated (Total: {len(prospects)})."
                )
            )
            for p in prospects:
                dates = f"{p.start_date or 'TBD'} to {p.end_date or 'TBD'}"
                self.stdout.write(f"  • [{p.sport}] {p.name} ({dates}) - Status: {p.status}")

        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"✗ Failed to pull from external API: {exc}"))
