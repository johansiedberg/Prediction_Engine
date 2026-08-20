import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()
from tournament.services.llm_wikipedia_scout import LLMWikipediaScout

tournaments = [
    "2026–27 UEFA Nations League",
    "UEFA Euro 2028 qualifying",
    "2026–27 CONCACAF Nations League",
    "2026 FIFA Women's U20 World Cup",
    "2026 European Women's Handball Championship"
]

scout = LLMWikipediaScout()

for t in tournaments:
    print(f"\n--- Testing {t} ---")
    try:
        text = scout._fetch_plaintext(t)
        if text:
            print(f"Success! Extracted {len(text)} characters.")
            if "| " in text and "---" in text:
                print("Markdown tables detected!")
            else:
                print("No markdown tables found.")
            # Check for subpages
            if "ARTICLE CONTENT:" in text:
                subpages = text.count("=== ARTICLE CONTENT:")
                print(f"Subpages found + main page: {subpages}")
        else:
            print("Failed to extract any text.")
    except Exception as e:
        print(f"Error: {e}")
