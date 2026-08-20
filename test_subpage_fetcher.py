import requests
from bs4 import BeautifulSoup
import re

headers = {'User-Agent': 'Mozilla/5.0'}
base_url = 'https://en.wikipedia.org/api/rest_v1/page/html/'
main_page = '2026%E2%80%9327_UEFA_Nations_League'

resp = requests.get(base_url + main_page, headers=headers)
soup = BeautifulSoup(resp.text, 'html.parser')

subpages = []
for div in soup.find_all('div', class_='hatnote'):
    text = div.get_text().lower()
    if 'main article' in text or 'details' in text:
        for a in div.find_all('a'):
            href = a.get('href', '')
            if href.startswith('./') and 'Nations_League' in href:
                subpages.append(href.replace('./', ''))

print("Found subpages:", subpages)
