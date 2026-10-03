"""Category classification for transactions based on name and label."""
import re

STARTER = ["Household", "Car", "Food shopping", "Takeaways", "Subscriptions",
           "Shopping", "Cash", "Savings/Transfers", "Unsorted"]

KEYWORDS = [
    ("Household", ["RENT", "WATER", "COUNCIL", "CITY OF", "E.ON", "ENERGY", "ELECTRIC",
                   "GAS", "OCTOPUS", "SKY", "TV LICENCE", "LICENCE", "MOBILE",
                   "BROADBAND", "VIRGIN MEDIA", "BT", "LIFE", "INSURANCE", "BILLS"]),
    ("Car", ["CAR", "PETROL", "FUEL", "PUMP", "DVLA", "SHELL", "ESSO", "TEXACO", "PARKING"]),
    ("Subscriptions", ["NETFLIX", "SPOTIFY", "YOUTUBE", "AUDIBLE", "XBOX", "PLAYSTATION",
                       "DISNEY", "PRIME", "UDEMY", "GOOGLE PLAY", "GOOGLE", "APPLE"]),
    ("Takeaways", ["JUST EAT", "DELIVEROO", "UBER EATS", "DOMINOS", "PIZZA", "KFC",
                   "MCDONALDS", "TAKEAWAY"]),
    ("Food shopping", ["TESCO", "ASDA", "SAINSBURYS", "ALDI", "LIDL", "MORRISONS",
                       "FARMFOODS", "ICELAND", "CO-OP", "M&S FOOD", "FOOD"]),
    ("Shopping", ["AMAZON", "ARGOS", "CURRYS", "THE RANGE", "B&Q", "IKEA", "EBAY"]),
    ("Savings/Transfers", ["SAVINGS", "SAVER", "TRANSFER", "ISA"]),
]


def guess_category(name: str, label: str = "", group: str = "") -> str:
    """Guess a category from transaction name and label.

    If group == "CASH" return "Cash". Otherwise, combine label and name to uppercase,
    then search for keywords in KEYWORDS order (first match wins). Matches must be
    whole words (use regex word boundaries). No match returns "Unsorted".
    """
    if group == "CASH":
        return "Cash"

    # Combine label and name to uppercase
    text = (label + " " + name).upper()

    # Search for keywords in order (first match wins)
    for category, keywords in KEYWORDS:
        for keyword in keywords:
            # Use whole word matching: word boundary before and after
            pattern = r"(?<![A-Z0-9])" + re.escape(keyword) + r"(?![A-Z0-9])"
            if re.search(pattern, text):
                return category

    return "Unsorted"


def category_for(key: str, label: str, saved_category: str) -> str:
    """Get the category for an item, preferring saved category if it exists.

    If saved_category is a non-empty string, return it. Otherwise split key
    "GROUP|NAME|REF" and return guess_category(NAME, label, GROUP).
    """
    if saved_category:
        return saved_category

    # Split key and call guess_category
    parts = key.split("|")
    if len(parts) >= 3:
        group = parts[0]
        name = parts[1]
        return guess_category(name, label, group)

    return "Unsorted"
