import json
from app.db_utils import save_to_db, db_query
from google.genai import types
from enum import Enum


# Food, Transport, Entertainment, Travel, Health, Shopping, Utilities, Education, Miscellaneous, Groceries, Dining, Subscriptions, Gifts
class Category(Enum):
    FOOD = "food"
    TRANSPORT = "transport"
    ENTERTAINMENT = "entertainment"
    UTILITIES = "utilities"
    GROCERY = "grocery"
    SHOPPING = "shopping"
    ELECTRONICS = "electronics"
    HEALTH = "health"
    MISCELLANEOUS = "miscellaneous"
    AUTOMOBILE = "automobile"
    CLOTHING = "clothing"
    EDUCATION = "education"
    SUBCRIPTIONS = "subscriptions"
    GIFTS = "gifts"
    OTHER = "other"
    NONE = "none"


# This is the actual function that would be called based on the model's suggestion
def save_expense(
    id: str,
    user_id: int,
    category: str,
    price: float,
    description: str,
    date: str,
) -> dict:
    """Save expense to db."""
    try:
        category_enum = Category[category.upper()]
    except KeyError:
        raise ValueError(f"Invalid category: {category}")

    expense_data = {
        "id": id,
        "user_id": user_id,
        "category": category_enum.value,
        "price": price,
        "description": description,
        "date": date,
    }

    save_to_db(expense_data)

    return {"status": "success", "message": "Expense saved!"}


def get_all_expenses(user_id: str) -> dict:
    """Get all expenses."""
    query = f"""SELECT * FROM expenses
                WHERE user_id = '{user_id}'"""

    return db_query(query)


def get_expenses_by_category(user_id: str, category: str) -> dict:
    """Get expenses by category."""
    query = f"""
        SELECT * FROM expenses
        WHERE user_id = '{user_id}' AND category = '{category.lower()}'
    """

    return db_query(query)


def get_expenses_by_date(user_id: str, start_date: str, end_date: str) -> dict:
    """Get expenses by date range."""
    query = f"""
        SELECT * FROM expenses
        WHERE user_id = '{user_id}' AND date BETWEEN '{start_date}' AND '{end_date}'
    """

    return db_query(query)


def get_breakdown(user_id: str) -> dict:
    """Get expenses by date range."""
    query = f"""
        SELECT category, sum(price) FROM expenses
        WHERE user_id = '{user_id}'
        GROUP BY category
    """

    return db_query(query)


tools = [
    save_expense,
    get_all_expenses,
    get_expenses_by_category,
    get_expenses_by_date,
    get_breakdown,
]

# func_config = types.GenerateContentConfig(
#     tools=tools,
#     # response_mime_type="text/plain",
#     # tool_config=types.ToolConfig(
#     #     function_calling_config=types.FunctionCallingConfig(mode="ANY"),
#     # ),
#     system_instruction="You are a helpful assistant which will only execute functions regarding expense related queries. Must be in English or Bengali. Must select category from the following list: Food, Transport, Entertainment, Travel, Health, Shopping, Utilities, Education, Miscellaneous, Groceries, Dining, Subscriptions, Gifts. Get appropiate catagory according to user query. If can't decide category just use 'miscellaneous'.",
# )

func_config = {
    "tools": tools,
    "automatic_function_calling": {"disable": True},
    "tool_config": {"function_calling_config": {"mode": "any"}},
    "system_instruction": "You are a helpful assistant 'Expense Buddy' which will only execute functions regarding expense related queries. Must be in English or Bengali. Must select category from the following list: Food, Transport, Entertainment, Travel, Health, Shopping, Utilities, Education, Miscellaneous, Groceries, Dining, Subscriptions, Gifts. Get appropiate catagory according to user query. If can't decide category just use 'miscellaneous'. Add a query_lang parameter to the input with value 'english' or 'bengali' to indicate the language of the query.",
}
