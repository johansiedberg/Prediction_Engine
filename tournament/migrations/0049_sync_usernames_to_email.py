from django.db import migrations


def sync_usernames_to_email(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    # Update existing users where email is set
    for user in User.objects.all():
        if user.email and '@' in user.email:
            new_username = user.email.strip().lower()
            # If another user already has this username, keep it unique
            if not User.objects.filter(username=new_username).exclude(id=user.id).exists():
                user.username = new_username
                user.email = new_username
                user.save(update_fields=['username', 'email'])


def reverse_sync(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('tournament', '0048_scannedtournament_official_source_url'),
    ]

    operations = [
        migrations.RunPython(sync_usernames_to_email, reverse_sync),
    ]
