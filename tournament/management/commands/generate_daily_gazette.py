import datetime
from django.core.management.base import BaseCommand
from tournament.models import Tournament, DailyGazette
from tournament.editorial_engine.detectors import detect_daily_events
from tournament.editorial_engine.media import generate_daily_gazette_edition


class Command(BaseCommand):
    help = "Generates the Daily Gazette edition for a given matchday using Tier 1 event detectors and Tier 3 storyteller engine."

    def add_arguments(self, parser):
        parser.add_argument('--matchday', type=int, default=None, help='Matchday number to process')
        parser.add_argument('--date', type=str, default=None, help='Publish date in YYYY-MM-DD format')
        parser.add_argument('--force', action='store_true', help='Force regeneration if gazette exists')

    def handle(self, *args, **options):
        tournament = Tournament.objects.first()
        if not tournament:
            self.stderr.write("No Tournament found in database.")
            return

        matchday = options['matchday']
        force = options['force']

        if options['date']:
            try:
                publish_date = datetime.datetime.strptime(options['date'], "%Y-%m-%d").date()
            except ValueError:
                self.stderr.write("Invalid date format. Use YYYY-MM-DD.")
                return
        else:
            publish_date = datetime.date.today()

        self.stdout.write(f"Running Tier 1 Event Detectors for matchday {matchday or 'latest'}...")
        events = detect_daily_events(tournament, matchday_number=matchday)
        self.stdout.write(self.style.SUCCESS(f"Detected {len(events)} events."))

        self.stdout.write(f"Generating Daily Gazette edition for date {publish_date}...")
        gazette = generate_daily_gazette_edition(tournament, publish_date=publish_date, force=force)

        self.stdout.write(self.style.SUCCESS(
            f"Successfully generated Daily Gazette edition #{gazette.id}:\n"
            f"  Headline: {gazette.headline}\n"
            f"  Tagline: {gazette.tagline}\n"
            f"  Format: {gazette.content_format}\n"
            f"  Image: {gazette.image_url}"
        ))
