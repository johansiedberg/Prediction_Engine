from django.core.management.base import BaseCommand
from tournament.services.scout_service import fetch_and_ingest_allsportdb_tournaments
from tournament.models import Sport, TournamentEvent, ScannedTournament

class Command(BaseCommand):
    help = 'Fetches upcoming H2H team sports championship tournaments from AllSportDB API (v3) up to 1 year ahead.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--months',
            type=int,
            default=12,
            help='Number of months ahead to fetch upcoming tournaments (default: 12)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run filtering and evaluation without saving records to database'
        )
        parser.add_argument(
            '--no-scout-sync',
            action='store_true',
            help='Do not sync events into ScannedTournament prospects for Engine Admin'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete existing un-converted ScannedTournament prospects before scanning'
        )

    def handle(self, *args, **options):
        months = options['months']
        dry_run = options['dry_run']
        sync_scout = not options['no_scout_sync']
        clear_old = options['clear']

        if clear_old and not dry_run:
            deleted_cnt = ScannedTournament.objects.filter(status='NEW').delete()[0]
            self.stdout.write(self.style.WARNING(
                f"Cleared {deleted_cnt} un-converted scanned tournament prospects."
            ))

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"=== AllSportDB Tournament Pipeline (Fetching {months} months ahead | Dry-Run: {dry_run}) ==="
        ))


        try:
            created_cnt, updated_cnt, prospects = fetch_and_ingest_allsportdb_tournaments(
                months_ahead=months,
                dry_run=dry_run,
                sync_scout=sync_scout
            )

            if dry_run:
                self.stdout.write(self.style.SUCCESS(
                    f"\n[DRY RUN COMPLETE] Simulated scanning for {months} months ahead."
                ))
                self.stdout.write(f"Evaluated {len(prospects)} valid H2H championship/cup prospects:")
                for p in prospects[:15]:
                    self.stdout.write(f" - [{p['grade']}] {p['title']} ({p['sport']}) -> {p['grade_reason']}")
                if len(prospects) > 15:
                    self.stdout.write(f" ... and {len(prospects) - 15} more.")
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"\n[INGESTION COMPLETE] Successfully synced AllSportDB tournament events!"
                ))
                self.stdout.write(f"  • Created events: {created_cnt}")
                self.stdout.write(f"  • Updated events: {updated_cnt}")
                self.stdout.write(f"  • Synced Scout Prospects: {len(prospects)}")
                self.stdout.write(f"  • Total Sports in DB: {Sport.objects.count()}")
                self.stdout.write(f"  • Total TournamentEvents in DB: {TournamentEvent.objects.count()}")
                self.stdout.write(f"  • Total ScannedTournaments in DB: {ScannedTournament.objects.count()}")

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Pipeline error: {str(e)}"))
