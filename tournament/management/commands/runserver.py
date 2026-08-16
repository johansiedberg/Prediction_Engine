from django.contrib.staticfiles.management.commands.runserver import Command as StaticfilesRunserverCommand

class Command(StaticfilesRunserverCommand):
    default_addr = "127.0.0.1"
    default_port = "8028"

