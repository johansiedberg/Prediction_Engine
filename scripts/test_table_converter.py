from bs4 import BeautifulSoup

html = """
<table class="wikitable sports-series" data-nowrap="n" id="mwAsE"><tbody><tr><th scope="col" style="width:250px">Team 1</th><th scope="col" style="width:80px">Agg.</th><th scope="col" style="width:250px">Team 2</th><th scope="col" style="width:80px">1st leg</th><th scope="col" style="width:80px">2nd leg</th></tr><tr><td>Group runner-up</td><td>1</td><td>Group winner</td><td>25–27 Mar</td><td>28–30 Mar</td></tr></tbody></table>
"""

soup = BeautifulSoup(html, 'html.parser')
for table in soup.find_all('table'):
    markdown = []
    for i, row in enumerate(table.find_all('tr')):
        cols = row.find_all(['td', 'th'])
        row_text = " | ".join(col.get_text(strip=True) for col in cols)
        markdown.append("| " + row_text + " |")
        if i == 0:
            markdown.append("|" + "|".join(["---"] * len(cols)) + "|")
    table.replace_with("\n" + "\n".join(markdown) + "\n")

print(soup.get_text())
