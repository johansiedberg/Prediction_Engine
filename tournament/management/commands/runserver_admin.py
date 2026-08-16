from django.contrib.staticfiles.management.commands.runserver import Command as StaticfilesRunserverCommand

class Command(StaticfilesRunserverCommand):
    default_addr = "127.0.0.1"
    default_port = "8029"
    help = "Starts the lightweight web server for Engine Admin on port 8029 (behind Caddy proxy on 2029)."

