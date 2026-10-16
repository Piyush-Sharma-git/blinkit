"""
forms.py - every form, with its validation rules (Flask-WTF / WTForms).

Each FlaskForm automatically includes a hidden CSRF token. form.validate_on_submit()
returns True only if the request is a POST, the CSRF token is valid, and every
validator below passes. If not, form.errors holds messages shown on the page.
"""
from datetime import date

from flask_wtf import FlaskForm
from wtforms import (BooleanField, DateField, DecimalField, IntegerField, PasswordField,
                     SelectField, StringField, TextAreaField)
from wtforms.validators import (DataRequired, EqualTo, InputRequired, Length, NumberRange,
                                Optional, Regexp, ValidationError)

from services import PAYMENT_METHODS

EMAIL = Regexp(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$", message="Enter a valid email address.")
PHONE = Regexp(r"^[6-9]\d{9}$", message="Enter a 10-digit Indian mobile number.")


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), EMAIL])
    password = PasswordField("Password", validators=[DataRequired()])


class CustomerDetailsForm(FlaskForm):
    """Fields shared by customer self-registration and staff 'new customer'."""
    full_name = StringField("Full name", validators=[DataRequired(), Length(2, 80)])
    email = StringField("Email", validators=[DataRequired(), EMAIL, Length(max=120)])
    phone = StringField("Mobile number", validators=[DataRequired(), PHONE])
    address = StringField("Address", validators=[DataRequired(), Length(5, 200)])
    city = StringField("City", validators=[DataRequired(), Length(2, 60)])


class RegisterForm(CustomerDetailsForm):
    password = PasswordField("Password", validators=[
        DataRequired(), Length(min=8, message="Use at least 8 characters.")])
    confirm = PasswordField("Confirm password", validators=[
        DataRequired(), EqualTo("password", message="Passwords do not match.")])


class ProductForm(FlaskForm):
    name = StringField("Product name", validators=[DataRequired(), Length(2, 80)])
    brand = StringField("Brand", validators=[DataRequired(), Length(2, 80)])
    category_id = SelectField("Category", coerce=int, validators=[DataRequired()])
    price = DecimalField("Selling price (Rs)", places=2,
                         validators=[DataRequired(), NumberRange(min=0.01)])
    mrp = DecimalField("MRP (Rs)", places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    # InputRequired (not DataRequired) because 0 is a valid stock number.
    stock_qty = IntegerField("Stock on hand", validators=[InputRequired(), NumberRange(min=0)])
    min_stock = IntegerField("Reorder level (min)", validators=[InputRequired(), NumberRange(min=0)])
    max_stock = IntegerField("Max stock", validators=[InputRequired(), NumberRange(min=1)])
    is_active = BooleanField("Available for sale", default=True)

    def validate_mrp(self, field):           # WTForms calls validate_<field> automatically
        if self.price.data is not None and field.data is not None and field.data < self.price.data:
            raise ValidationError("MRP cannot be lower than the selling price.")

    def validate_max_stock(self, field):
        if self.min_stock.data is not None and field.data is not None and field.data < self.min_stock.data:
            raise ValidationError("Max stock must be at least the reorder level.")


class EmployeeForm(FlaskForm):
    full_name = StringField("Full name", validators=[DataRequired(), Length(2, 80)])
    email = StringField("Work email", validators=[DataRequired(), EMAIL])
    role = SelectField("Role", choices=[("sales_exec", "Sales Executive"),
                                        ("manager", "Sales Manager"),
                                        ("admin", "Administrator")])
    password = PasswordField("Temporary password", validators=[DataRequired(), Length(min=8)])


class OrderForm(FlaskForm):
    """Header of the staff order form. The product rows are parsed separately
    (services.parse_items) because their number changes in the browser."""
    customer_id = SelectField("Customer", coerce=int,
                              validators=[DataRequired(message="Choose a customer.")])
    order_date = DateField("Transaction date", default=date.today, validators=[DataRequired()])
    payment_method = SelectField("Payment method", choices=list(PAYMENT_METHODS.items()))
    payment_status = SelectField("Payment status", choices=[
        ("paid", "Paid"), ("pending", "Pending"), ("failed", "Failed")])
    notes = TextAreaField("Notes (optional)", validators=[Optional(), Length(max=300)])

    def validate_order_date(self, field):
        if field.data and field.data > date.today():
            raise ValidationError("Transaction date cannot be in the future.")


class StatusForm(FlaskForm):
    status = SelectField("Order status", choices=[
        ("placed", "Placed"), ("delivered", "Delivered"), ("cancelled", "Cancelled")])


class PaymentStatusForm(FlaskForm):
    payment_status = SelectField("Payment status", choices=[
        ("pending", "Pending"), ("paid", "Paid"), ("failed", "Failed"), ("refunded", "Refunded")])


class CheckoutForm(FlaskForm):
    payment_method = SelectField("Payment method", choices=[
        ("upi", "UPI (simulated)"), ("card", "Card (simulated)"), ("cod", "Cash on delivery")])
    notes = TextAreaField("Delivery note (optional)", validators=[Optional(), Length(max=300)])
