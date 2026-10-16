"""
db.py - the bridge between Python and the SQLite database.

Flask gives every web request its own "g" object (short for global, but it
only lives for one request). We open one database connection per request,
keep it on g, and close it automatically when the request ends.
"""
import sqlite3

from flask import current_app, g


def get_db():
    """Return this request's database connection, opening it if needed."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        # Rows behave like dictionaries: row["name"] instead of row[1].
        g.db.row_factory = sqlite3.Row
        # SQLite does NOT enforce foreign keys unless asked, per connection.
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(exception=None):
    """Called by Flask after every request (registered in app.py)."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query_one(sql, params=()):
    """Run a SELECT and return the first row (or None)."""
    return get_db().execute(sql, params).fetchone()


def query_all(sql, params=()):
    """Run a SELECT and return all rows as a list."""
    return get_db().execute(sql, params).fetchall()


def execute(sql, params=()):
    """
    Run one INSERT / UPDATE / DELETE and commit it.
    Returns the cursor so callers can read cursor.lastrowid or rowcount.

    Every value goes in `params` and is bound to a ? placeholder.
    We NEVER build SQL with f-strings or + on user input: that is what
    prevents SQL injection.
    """
    db = get_db()
    cur = db.execute(sql, params)
    db.commit()
    return cur


def init_app(app):
    app.teardown_appcontext(close_db)
