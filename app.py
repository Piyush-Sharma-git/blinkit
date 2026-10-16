"""
app.py - creates the Flask application and wires everything together.

Run:   flask --app app run --debug
  or:  python app.py
"""
import os
import sqlite3

from flask import Flask, render_template, session
from flask_wtf.csrf import CSRFError, CSRFProtect

import db
from auth import ROLE_LABEL, has_role, load_logged_in_user
from config import Config
from catalog import product_icon
from services import PAYMENT_METHODS

csrf = CSRFProtect()


def inr(value):
    """Format a number as Indian rupees with Indian digit grouping: Rs 12,34,567.50"""
    if value is None:
        return "₹0.00"
    negative = value < 0
    whole, frac = f"{abs(float(value)):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups) + "," + tail
    return f"{'-' if negative else ''}₹{whole}.{frac}"


def order_code(order_id):
    """Display format of the transaction ID: 42 -> BLK-000042"""
    return f"BLK-{int(order_id):06d}"


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)            # close the DB connection after each request
    csrf.init_app(app)          # CSRF token required on every POST form

    # Blueprints = groups of routes. Two interfaces, one app, one database.
    from routes.public import public_bp
    from routes.admin import admin_bp
    app.register_blueprint(public_bp)                       # /, /products, ...
    app.register_blueprint(admin_bp, url_prefix="/admin")   # /admin/...

    app.before_request(load_logged_in_user)

    # Make these available inside every template.
    app.jinja_env.filters["inr"] = inr
    app.jinja_env.filters["order_code"] = order_code
    # Globals (unlike context-processor values) are also visible inside imported macros.
    app.jinja_env.globals["product_icon"] = product_icon

    @app.context_processor
    def template_globals():
        cart = session.get("cart", {})
        return {
            "has_role": has_role,
            "ROLE_LABEL": ROLE_LABEL,
            "PAYMENT_METHODS": PAYMENT_METHODS,
            "cart_count": sum(cart.values()),
        }

    # ---- Friendly error pages ------------------------------------------
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("error.html", code=403,
                               message="You do not have permission to open this page."), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404,
                               message="That page or record does not exist."), 404

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        return render_template("error.html", code=400,
                               message="The form expired or was tampered with. Go back, refresh and try again."), 400

    @app.errorhandler(sqlite3.OperationalError)
    def db_error(e):
        app.logger.exception("Database error")
        hint = ("The database has not been created yet. Stop the server, run "
                "'python seed.py', then start it again.") if "no such table" in str(e) \
            else "A database error occurred. Check the terminal for details."
        return render_template("error.html", code=500, message=hint), 500

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
