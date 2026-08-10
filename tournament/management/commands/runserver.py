from django.contrib.staticfiles.management.commands.runserver import Command as StaticfilesRunserverCommand

class Command(StaticfilesRunserverCommand):
    default_addr = "0.0.0.0"
    default_port = "2028"
