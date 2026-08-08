# Project Overview and Architecture: Prediction Engine v2.0 (Standalone Framework)

## 1. Background and Objectives

After successfully managing previous tournaments—most recently the 2026 Football World Cup—via advanced Excel macros to run leaderboards and point calculations, this project marks the next step in its evolution. The goal is to transition from manual, file-based administration to a modern, accessible web application built in Python and Django.

The main objective of the platform is to digitize and automate the entire workflow for the tipping club:

* **Automated Point Calculation:** The system automatically calculates tournament points and updates participant rankings based on match results.
* **Centralized Data Management:** A relational database (via Django's ORM) ensures data integrity and enables advanced statistics and form forecasting.
* **Improved User Experience:** Participants get a dedicated, constantly updated interface directly in their web browser.

## 2. System Structure and User Roles

The application relies on a clear division of responsibilities to separate system administration from the actual competition experience. The functionality is designed around two main interaction areas and roles:

### Admin (Administrator)

This role acts as the engine of the system. The interface (driven by Django's built-in admin panel) is used for system maintenance and quality control.

* **Manage Users:** Register, update, and administer the participants.
* **Manage Tournaments:** Set up new championships, define match rounds, and structure the underlying competition tree.
* **Verify Predictions:** Ensure submitted predictions are valid, complete, and submitted before the deadline.
* **Report Results:** Input actual match results after the final whistle, which in turn triggers the system's point calculation.

### Player (End User)

This is the public interface that participants interact with. The focus is on engagement, accessibility, and clear data visualization to enhance the competitive element.

* **Submit Predictions:** An interactive flow to easily register and submit match predictions for upcoming rounds.
* **View Results:** A personal view displaying history, individual accuracy, and earned points.
* **View Leaderboard:** The central ranking table showing current standings, total points, and position changes week by week.
* **Dashboard Comparisons:** Visual summaries and statistics where players can compare their form and picks against other participants.

## 3. Project Structure (Tree) and Key Files

To maintain order and separate responsibilities in the code, the project is set up according to Django's standard structure. The architecture separates database logic, routing, and user interface.

Here is the comprehensive overview of the project's directory tree:

```text
HERRKLUBBSTIPS/
│
├── core/
│   ├── __pycache__/
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
│
├── templates/
│   ├── admin/
│   │   └── tournament/
│   ├── index_backup.html
│   ├── login.html
│   └── tournament/
│       ├── base.html
│       ├── index.html
│       ├── login.html
│       └── predictions.html
│
├── tournament/
│   ├── __pycache__/
│   ├── migrations/
│   ├── static/
│   │   └── tournament/
│   │       ├── css/
│   │       │   └── style.css
│   │       ├── img/
│   │       ├── admin_columns.css
│   │       └── admin_enter.js
│   ├── templatetags/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── forms.py
│   ├── models.py
│   ├── tests.py
│   ├── urls.py
│   └── views.py
│
├── db.sqlite3
├── Kod.txt
├── manage.py
├── README.md
└── TemplateSyntaxError.txt
```

### Core Files Interaction

When a *Player* wants to view the current Leaderboard, a request is sent to a specific URL (`urls.py`). This points to a function in `views.py`. The function retrieves all necessary data and current standings from the database via `models.py`, processes the data, and finally sends the result to `leaderboard.html` in the `templates/` directory where it is dynamically rendered for the user.

---

## 4. Development & Workflow Conventions

* **Communication Language:** Discussion and planning are conducted in **English**.
* **Code & Comments:** All code, function signatures, and comments must be written in **English**.
* **App Output & UI Text:** Every user-facing text, label, and app output must be in **Swedish**.
* **UI & Design Approvals:** All proposed design or UI layout changes **MUST** be presented to the user for review and explicit approval **before** writing or editing template/CSS code files.
* **1X2 Prediction Frames:** Formatted in 4 distinct lines: (1) Outcome, (2) Team/Result, (3) % of predictions, (4) Player count (unmuted text).
* **AI Analysis Tone & Structure:** Edgy, banter-filled text for childhood friends. 3 paragraphs: (1) Entire field match analysis, (2) Player's individual tip (strictly **1 emoji**), (3) Outliers, wild tips & rivalry impacts.