from django.core.management.base import BaseCommand
from django.utils import timezone
from tournament.models import Tournament
from tournament.editorial_engine.static_generators import generate_static_insights
from tournament.editorial_engine.detectors import detect_daily_events, check_and_trigger_special_editions
from tournament.editorial_engine.media import generate_daily_gazette_edition


class Command(BaseCommand):
    help = "Generates Static Insights, Special Editions, and Daily Gazette editions for active tournaments."

    def add_arguments(self, parser):
        parser.add_argument('--date', type=str, help='Target publish date (YYYY-MM-DD)')
        parser.add_argument('--force', action='store_true', help='Force regeneration of gazette if it exists')

    def handle(self, *args, **options):
        date_str = options.get('date')
        force = options.get('force', False)

        active_tournaments = Tournament.objects.filter(is_active=True)
        if not active_tournaments.exists():
            active_tournaments = Tournament.objects.all()

        for t in active_tournaments:
            self.stdout.write(self.style.SUCCESS(f"--- Processing Editorial Engine for: {t.name} ---"))
            
            # 1. Generate Static Insights (Almanac & Pre-Tournament analysis)
            insights = generate_static_insights(t)
            self.stdout.write(f"Generated {len(insights)} Static Insight records.")

            # 2. Check and Trigger Milestone Special Editions (Round 1, Round 2, Halftime, etc.)
            sp_editions = check_and_trigger_special_editions(t)
            self.stdout.write(f"Processed {len(sp_editions)} Special Milestone Edition(s).")

            # 3. Detect Daily Events & Generate Daily Gazette
            detect_daily_events(t)
            gazette = generate_daily_gazette_edition(t, publish_date=date_str, force=force)
            if gazette:
                self.stdout.write(self.style.SUCCESS(f"Daily Gazette generated for {gazette.publish_date}: '{gazette.headline}'"))

