from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from tournament.models import UserProfile, League, LeagueMember

class Command(BaseCommand):
    help = "Seeds the 11 Toarps Herrklubb members, system admin, and default leagues into the database."

    def handle(self, *args, **options):
        self.stdout.write("Seeding Prediction Engine users...")

        members = [
            {"username": "johan.siedberg", "first_name": "Johan", "last_name": "Siedberg", "email": "johan.siedberg@gmail.com"},
            {"username": "mikael.dahl", "first_name": "Mikael", "last_name": "Dahl", "email": "mikaeld81@gmail.com"},
            {"username": "andreas.larsson", "first_name": "Andreas", "last_name": "Larsson", "email": "anymaztic@hotmail.com"},
            {"username": "johan.svensson", "first_name": "Johan", "last_name": "Svensson", "email": "svenjohansvensson@gmail.com"},
            {"username": "johan.meldo", "first_name": "Johan", "last_name": "Meldo", "email": "jmeldo@gmail.com"},
            {"username": "erik.svensson", "first_name": "Erik", "last_name": "Svensson", "email": "erik.sve@hotmail.com"},
            {"username": "christoffer.ericsson", "first_name": "Christoffer", "last_name": "Ericsson", "email": "coff_erics@yahoo.se"},
            {"username": "martin.gustafsson", "first_name": "Martin", "last_name": "Gustafsson", "email": "martin.gustafson1@gmail.com"},
            {"username": "tommy.lycen", "first_name": "Tommy", "last_name": "Lycen", "email": "t.lycen@gmail.com"},
            {"username": "tommy.kallberg", "first_name": "Tommy", "last_name": "Källberg", "email": "senasa@gmail.com"},
            {"username": "martin.krantz", "first_name": "Martin", "last_name": "Krantz", "email": "martin@meritel.se"},
        ]

        # 1. Create or update the 11 core members
        created_count = 0
        updated_count = 0
        herrklubb_users = []

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

            UserProfile.objects.get_or_create(user=user)
            herrklubb_users.append(user)

            if created:
                created_count += 1
            else:
                updated_count += 1

        # 2. Ensure standalone, isolated Engine Admin 'johansiedberg' exists
        admin_user = User.objects.filter(username='johansiedberg').first()
        if not admin_user:
            admin_user = User.objects.create(
                username='johansiedberg',
                email='engineadmin@predictionengine.local',
                first_name='Engine',
                last_name='Admin',
                is_staff=True,
                is_superuser=True,
                is_active=True,
            )
        else:
            admin_user.username = 'johansiedberg'
            admin_user.email = 'engineadmin@predictionengine.local'
            admin_user.is_staff = True
            admin_user.is_superuser = True
            admin_user.is_active = True

        admin_user.set_password('saftochbullar')
        admin_user.save()

        # Remove superuser/staff status from all other users to ensure strictly ONE global Engine Admin
        User.objects.exclude(pk=admin_user.pk).update(is_staff=False, is_superuser=False)
        self.stdout.write(self.style.SUCCESS("Enforced isolated Engine Admin 'johansiedberg'."))

        # 3. Create default league 'Toarps Herrklubb' with player Johan Siedberg as Pool Admin
        pool_admin_user = User.objects.filter(email='johan.siedberg@gmail.com').first()
        league, l_created = League.objects.get_or_create(
            name="Toarps Herrklubb",
            defaults={
                "admin": pool_admin_user,
                "invite_code": "HERRKLUBB2028",
                "is_active": True,
            }
        )
        if not l_created and league.admin != pool_admin_user:
            league.admin = pool_admin_user
            league.save()

        for u in herrklubb_users:
            LeagueMember.objects.get_or_create(league=league, player=u)

        self.stdout.write(self.style.SUCCESS(
            f"Successfully seeded members ({created_count} created, {updated_count} updated) in League '{league.name}'."
        ))
