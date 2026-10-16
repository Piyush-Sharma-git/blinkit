# Blinkit Sales Portal (academic project)

A database-driven website with two interfaces sharing one SQLite database:

- **Customer website**: browse 268 products, cart, simulated checkout, order history
- **Internal Sales dashboard**: record transactions, manage customers and stock, reports, role-based access

Built with Python, Flask, SQLite, Jinja2, HTML/CSS/JS.

## Quick start

**Windows: double-click `start_windows.bat`.** Mac: double-click `start_mac.command`. It installs everything on the first run, checks that the database schema exists (and creates it if needed), then opens the website. Don't double-click `.py` files.

Manual way:

```bash
python -m venv venv
venv\Scripts\activate            # Windows   (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env           # Windows   (macOS/Linux: cp .env.example .env)
python seed.py                   # builds instance/blinkit.db from the Excel file
python app.py                    # open http://127.0.0.1:5000
python -m pytest -q              # 48 tests
```

Staff login: http://127.0.0.1:5000/admin/login. Demo accounts are printed by `seed.py`.

**Read `PROJECT_GUIDE.md`** for the full explanation: database design, data flow, the Sales workflow, security, testing checklist, troubleshooting and viva questions.

Not affiliated with Blinkit or Eternal Ltd. Product data comes from a sample dataset; customers and orders are synthetic.
