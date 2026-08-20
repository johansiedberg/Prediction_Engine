import os, django
import json

os.environ['GEMINI_API_KEY'] = 'YOUR_API_KEY'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from tournament.models import OfficialDataSource
from tournament.services.scout_orchestrator import DualScoutOrchestrator

# Setup Master List
OfficialDataSource.objects.get_or_create(name="UEFA", domain="uefa.com", is_verified=True)
OfficialDataSource.objects.get_or_create(name="FIFA", domain="fifa.com", is_verified=True)

print("Starting Dual-Source Scan for '2026-27 UEFA Nations League'...")
orchestrator = DualScoutOrchestrator()
result = orchestrator.run_deep_scan("2026-27 UEFA Nations League")

print("\n--- RESULTS ---")
rules = result.get('official_rules', 'NO RULES EXTRACTED')
print(f"RULES EXTRACTED:\n{rules[:500]}...\n")

prov = result.get('provenance_metadata', {})
print(f"PROVENANCE: {json.dumps(prov, indent=2)}")

if result.get('fixtures'):
    print(f"EXTRACTED {len(result['fixtures'])} FIXTURES (via Wikipedia fallback).")
