from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from tournament.models import UserProfile, BucketCategory, BucketItem

class Command(BaseCommand):
    help = "Seeds initial Herrklubben Bucket List categories, items, and sets Herrklubb status for users."

    def handle(self, *args, **options):
        self.stdout.write("Seeding Herrklubben Bucket List data...")

        # 1. Update user profiles (Set existing users as Herrklubb members by default)
        users = User.objects.all()
        for u in users:
            profile, created = UserProfile.objects.get_or_create(user=u)
            profile.is_herrklubb_member = True
            profile.save()
        self.stdout.write(self.style.SUCCESS(f"Updated {users.count()} users with Herrklubb membership."))

        # 2. Seed Categories
        categories_data = [
            {
                "name": "Sport & Stora Evenemang",
                "icon": "⚽",
                "order": 1,
                "items": [
                    ("Fotbollsresa: Serie A (Italien)", "T.ex. Milano-derby eller Rom-resa för klassisk italiensk läktarkultur."),
                    ("Fotbollsresa: Premier League (England)", "London eller Manchester – äkta brittisk fotbollspub och matchdag."),
                    ("Fotbollsresa: Bundesliga (Tyskland)", "Dortmund / Gelbe Wand eller München med episkt arrangemang."),
                    ("Fotbollsresa: Old Firm (Skottland)", "Celtic vs Rangers i Glasgow – ett av världens mäktigaste derbyn."),
                    ("Fotbollsresa: EM eller VM", "Landslagsturnering live från läktaren."),
                    ("Stockholmsderby", "AIK, Hammarby eller Djurgården i ett kokande allsvenskt derby."),
                    ("Formel 1-lopp", "Live Grand Prix med motorljud och VIP-stämning."),
                    ("NHL-match & Nordamerika", "Ishockeyresa till USA/Kanada för NHL i världsklass."),
                    ("Tennis Grand Slam & Event", "Franska Öppna (Paris), Australian Open eller Tennisveckan i Båstad."),
                    ("Övrig Elitsport", "Hockey-VM eller Handboll i Kiel."),
                ]
            },
            {
                "name": "Äventyr, Natur & Vinter",
                "icon": "🏔️",
                "order": 2,
                "items": [
                    ("Norgeresa till Coffe", "Vandring, fjäll & storslagna norska äventyr."),
                    ("Island", "Vulkaner, gejsrar, varma källor & naturupplevelser."),
                    ("Bestiga Kebnekaise", "Utmaning och toppbestigning på Sveriges högsta berg."),
                    ("Svensk Hajk & Friluftsliv", "Övernattning i vildmarken, fiske och lägereld."),
                    ("Skidresa", "Alperna eller klassiska fjällen för skidåkning & after-ski."),
                ]
            },
            {
                "name": "Temaresor: Mat, Dryck & Kultur",
                "icon": "🍺",
                "order": 3,
                "items": [
                    ("Oktoberfest i München", "Lederhosen, ölsejdlar och stämning i bayerska tält."),
                    ("Skottland: Whiskyresa", "Destilleriturer, provningar och skotsk kultur."),
                    ("Toscana: Vin- & Matresa", "Matlagningskurser, vingårdar och italiensk njutning."),
                ]
            },
            {
                "name": "Storstadsresor & Weekend",
                "icon": "🏙️",
                "order": 4,
                "items": [
                    ("Europa Storstad", "Weekend i Prag, Warszawa, Budapest, Bukarest eller Florens."),
                    ("Nordisk Weekend", "Oslo, Gotland eller Tylösand."),
                    ("Sydeuropa & Sol", "Barcelona, Sicilien eller 1 vecka sol & charter."),
                    ("Las Vegas & Kuba", "Långväga äventyr – casino i Vegas eller Kuba-resa."),
                ]
            },
            {
                "name": "Gemenskap & Snabba Event",
                "icon": "🎉",
                "order": 5,
                "items": [
                    ("Hyra Hus tillsammans", "Gemensam hussemester vid havet eller sjö."),
                    ("Konsert & Live-event", "Storkonsert eller festival tillsammans."),
                    ("Helg-Pokerkväll", "Klassisk pokerturnering med middag & god dryck."),
                ]
            }
        ]

        total_items_created = 0
        for cat_info in categories_data:
            cat, _ = BucketCategory.objects.get_or_create(
                name=cat_info["name"],
                defaults={"icon": cat_info["icon"], "order": cat_info["order"]}
            )
            cat.icon = cat_info["icon"]
            cat.order = cat_info["order"]
            cat.save()

            for item_title, item_desc in cat_info["items"]:
                item, created = BucketItem.objects.get_or_create(
                    title=item_title,
                    category=cat,
                    defaults={"description": item_desc}
                )
                if created:
                    total_items_created += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully seeded categories and created {total_items_created} bucket items."))
