# Project Rules for Prediction Engine

## Development Server
- **Prediction (Player Application)**: Default port **2028**
  - Start command: `./venv/bin/python manage.py runserver` (or `./venv/bin/python manage.py runserver 2028`)
  - Access at: http://127.0.0.1:2028
- **Engine Admin**: Default port **2029**
  - Start command: `./venv/bin/python manage.py runserver_admin` (or `./venv/bin/python manage.py runserver 2029`)
  - Access at: http://127.0.0.1:2029 (or https:// in HTTPS-enabled environments)

## HTTPS Security Standards
- Enforces HTTPS standards (`SECURE_PROXY_SSL_HEADER`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`, `SECURE_REFERRER_POLICY`) for secure encrypted transport.


