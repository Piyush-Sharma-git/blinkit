"""
catalog.py - small display helpers for products.

The dataset has no product photos, so each product gets an emoji icon by
name, with a fallback per category. (Using real brand photos or logos
would need permission.)
"""
PRODUCT_ICONS = {
    "Onions": "🧅", "Potatoes": "🥔", "Tomatoes": "🍅", "Bananas": "🍌", "Mangoes": "🥭",
    "Carrots": "🥕", "Spinach": "🥬", "Cheese": "🧀", "Curd": "🥣", "Butter": "🧈",
    "Eggs": "🥚", "Bread": "🍞", "Milk": "🥛", "Cereal": "🥣", "Biscuits": "🍪",
    "Nuts": "🥜", "Chips": "🍟", "Popcorn": "🍿", "Cookies": "🍪", "Chocolates": "🍫",
    "Orange Juice": "🍊", "Cola": "🥤", "Iced Tea": "🧋", "Mango Drink": "🥭",
    "Lemonade": "🍋", "Frozen Pizza": "🍕", "Instant Noodles": "🍜",
    "Frozen Vegetables": "🥦", "Ice Cream": "🍨", "Frozen Biryani": "🍛", "Rice": "🍚",
    "Pulses": "🫘", "Sugar": "🍬", "Salt": "🧂", "Wheat Flour": "🌾", "Dish Soap": "🧽",
    "Toilet Cleaner": "🚽", "Detergent": "🧺", "Shampoo": "🧴", "Toothpaste": "🪥",
    "Lotion": "🧴", "Soap": "🧼", "Baby Wipes": "🧻", "Baby Food": "🍼", "Diapers": "👶",
    "Cat Food": "🐱", "Pet Treats": "🦴", "Dog Food": "🐶", "Pain Reliever": "💊",
    "Cough Syrup": "🍯", "Vitamins": "💊",
}

CATEGORY_ICONS = {
    "Fruits & Vegetables": "🥕", "Dairy & Breakfast": "🥛", "Snacks & Munchies": "🍿",
    "Cold Drinks & Juices": "🥤", "Instant & Frozen Food": "🍜", "Grocery & Staples": "🌾",
    "Household Care": "🧽", "Personal Care": "🧴", "Baby Care": "🍼", "Pet Care": "🐾",
    "Pharmacy": "💊",
}


def product_icon(name, category=None):
    return PRODUCT_ICONS.get(name) or CATEGORY_ICONS.get(category, "🛒")


def discount_pct(price, mrp):
    """Percentage off MRP, e.g. price 75, mrp 100 -> 25."""
    if not mrp:
        return 0
    return round((mrp - price) / mrp * 100)
