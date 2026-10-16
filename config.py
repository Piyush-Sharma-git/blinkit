"""
config.py - all settings in one place.

Secrets come from environment variables (or a .env file), never from code
that gets shared. If SECRET_KEY is missing we fall back to a development
value and print a warning, so the project still runs on a fresh laptop.
"""
import os
import warnings

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Reads key=value pairs from .env into os.environ (if the file exists).
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    if not SECRET_KEY:
        warnings.warn("SECRET_KEY not set - using an insecure development key. "
                      "Copy .env.example to .env and set one.")
        SECRET_KEY = "dev-only-change-me"

    # Path of the SQLite database file (inside instance/, which is not shared).
    DATABASE = os.environ.get("DATABASE_PATH",
                              os.path.join(BASE_DIR, "instance", "blinkit.db"))

    # Flask-WTF: CSRF protection is ON for every form.
    WTF_CSRF_ENABLED = True

    # Session cookie hardening.
    SESSION_COOKIE_HTTPONLY = True      # JavaScript cannot read the cookie
    SESSION_COOKIE_SAMESITE = "Lax"     # cookie not sent on cross-site POSTs

    ORDERS_PER_PAGE = 25


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False            # tests post forms directly
