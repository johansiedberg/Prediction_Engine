from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from tournament.models import UserProfile, League, LeagueMember

class Command(BaseCommand):
    help = "Seeds the 11 Toarps Herrklubb members, system admin, and default leagues into the database."

    def handle(self, *args, **options):
        self.stdout.write("Seeding Prediction Engine users...")

        members = [
            {"username": "johan.siedberg", "first_name": "Johan", "last_name": "Siedberg", "email": "johan@siedberg.se"},
            {"username": "mikael.dahl", "first_name": "Mikael", "last_name": "Dahl", "email": "mikael@dahl.se"},
            {"username": "andreas.larsson", "first_name": "Andreas", "last_name": "Larsson", "email": "andreas@larsson.se"},
            {"username": "johan.svensson", "first_name": "Johan", "last_name": "Svensson", "email": "johan@svensson.se"},
            {"username": "johan.meldo", "first_name": "Johan", "last_name": "Meldo", "email": "johan@meldo.se"},
            {"username": "erik.svensson", "first_name": "Erik", "last_name": "Svensson", "email": "erik@svensson.se"},
            {"username": "christoffer.ericsson", "first_name": "Christoffer", "last_name": "Ericsson", "email": "christoffer@ericsson.se"},
            {"username": "martin.gustafsson", "first_name": "Martin", "last_name": "Gustafsson", "email": "martin@gustafsson.se"},
            {"username": "tommy.lycen", "first_name": "Tommy", "last_name": "Lycen", "email": "tommy@lycen.se"},
            {"username": "tommy.kallberg", "first_name": "Tommy", "last_name": "Källberg", "email": "tommy@kallberg.se"},
            {"username": "martin.krantz", "first_name": "Martin", "last_name": "Krantz", "email": "martin@krantz.se"},
        ]

        # 1. Create or update the 11 core members
        created_count = 0
        updated_count = 0

        for m in members:
            last_clean = m['last_name'].lower().replace('ä', 'a').replace('å', 'a').replace('ö', 'o').replace(' ', '')
            password = f"{last_clean}2026"
            email = m['email'].lower()

            user = User.objects.filter(email__iexact=email).first() or User.objects.filter(username=m['username']).first()
            if not user:
                user = User.objects.create(
                    username=email,
                    first_name=m['first_name'],
                    last_name=m['last_name'],
                    email=email,
                    is_active=True,
                )
                created = True
            else:
                created = False
                user.username = email
                user.first_name = m['first_name']
                user.last_name = m['last_name']
                user.email = email
                user.is_active = True

            user.set_password(password)
            user.save()

            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.is_herrklubb_member = True
            profile.save()

            if created:
                created_count += 1
            else:
                updated_count += 1

        # 2. Ensure superuser johansiedberg exists
        admin_email = 'johan@siedberg.se'
        admin_user = User.objects.filter(email__iexact=admin_email).first()
        if not admin_user:
            admin_user = User.objects.create(
                username=admin_email,
                email=admin_email,
                first_name='Johan',
                last_name='Siedberg',
                is_staff=True,
                is_superuser=True,
                is_active=True,
            )
            admin_user.set_password('admin2026')
            admin_user.save()
            self.stdout.write(self.style.SUCCESS(f"Created superuser '{admin_email}' with password 'admin2026'."))
        else:
            admin_user.username = admin_email
            admin_user.is_staff = True
            admin_user.is_superuser = True
            admin_user.save()

        # 3. Create default league 'Toarps Herrklubb' and add members
        league, l_created = League.objects.get_or_create(
            name="Toarps Herrklubb",
            defaults={
                "admin": admin_user,
                "invite_code": "HERRKLUBB2028",
                "is_active": True,
            }
        )

        for u in User.objects.filter(userprofile__is_herrklubb_member=True):
            LeagueMember.objects.get_or_create(league=league, player=u)

        self.stdout.write(self.style.SUCCESS(
            f"Successfully seeded members ({created_count} created, {updated_count} updated) in League '{league.name}'."
        ))
