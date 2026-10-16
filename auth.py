"""
auth.py - who is logged in, and what are they allowed to do?

Authentication = proving who you are (email + password).
Authorization  = deciding what you may access (customer vs staff role).

After a successful login we store only three small facts in the signed
session cookie: user_type ('customer' or 'employee'), user_id and role.
On every request we re-load the user from the database, so an employee who
is deactivated loses access immediately.
"""
from functools import wraps

from flask import abort, flash, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import query_one

# Higher number = more power. A manager can do everything a sales_exec can.
ROLE_LEVEL = {"sales_exec": 1, "manager": 2, "admin": 3}
ROLE_LABEL = {"sales_exec": "Sales Executive", "manager": "Sales Manager", "admin": "Administrator"}


def hash_password(plain):
    # pbkdf2/scrypt with a random salt; the plain password is never stored.
    return generate_password_hash(plain)


def verify_password(stored_hash, plain):
    return bool(stored_hash) and check_password_hash(stored_hash, plain)


def load_logged_in_user():
    """Runs before every request (registered in app.py). Sets g.customer / g.employee."""
    g.customer = None
    g.employee = None
    user_type = session.get("user_type")
    user_id = session.get("user_id")
    if user_type == "customer":
        g.customer = query_one(
            "SELECT customer_id, full_name, email FROM customers WHERE customer_id = ?",
            (user_id,))
    elif user_type == "employee":
        g.employee = query_one(
            "SELECT employee_id, full_name, email, role FROM employees "
            "WHERE employee_id = ? AND is_active = 1", (user_id,))
    # Stale or tampered session -> log out quietly.
    if user_type and g.customer is None and g.employee is None:
        session.clear()


def login_customer(customer):
    session.clear()                      # new session on login (no fixation)
    session["user_type"] = "customer"
    session["user_id"] = customer["customer_id"]


def login_employee(employee):
    session.clear()
    session["user_type"] = "employee"
    session["user_id"] = employee["employee_id"]
    session["role"] = employee["role"]


def safe_next(default):
    """Only follow ?next= if it is a path on OUR site (blocks open redirects)."""
    target = request.args.get("next") or request.form.get("next")
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return default


def customer_required(view):
    """Decorator: page needs a logged-in customer."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.customer is None:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("public.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def staff_required(min_role="sales_exec"):
    """
    Decorator factory: page needs a logged-in employee with at least min_role.
        @staff_required()            -> any employee
        @staff_required("manager")   -> manager or admin
        @staff_required("admin")     -> admin only
    """
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.employee is None:
                # Customers and visitors are sent to the STAFF login page.
                flash("Staff login required.", "warning")
                return redirect(url_for("admin.login", next=request.path))
            if ROLE_LEVEL[g.employee["role"]] < ROLE_LEVEL[min_role]:
                abort(403)               # logged in, but not allowed
            return view(*args, **kwargs)
        return wrapped
    return decorator


def has_role(min_role):
    """Used inside templates to show/hide buttons."""
    return g.get("employee") is not None and \
        ROLE_LEVEL[g.employee["role"]] >= ROLE_LEVEL[min_role]
