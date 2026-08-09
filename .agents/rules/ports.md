# Dedicated Server Port Rule

Whenever starting development servers:
* **Prediction Engine (Prediction)**: MUST ALWAYS run on port `2028` (e.g. `python manage.py runserver`).
* **Prediction Engine (Engine Admin)**: MUST ALWAYS run on port `2029` (e.g. `python manage.py runserver_admin` or `python manage.py runserver 2029`).
* **Toarps Herrklubb**: MUST ALWAYS run on port `1981` (e.g. `python manage.py runserver`).
* **Swimrun GPX**: MUST ALWAYS run on port `6510` (e.g. `python app.py`).


