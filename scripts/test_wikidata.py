import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from tournament.services.wikidata_scout import WikidataScout

res = WikidataScout.fetch_wikidata_entity("UEFA Nations League")
print(res)
