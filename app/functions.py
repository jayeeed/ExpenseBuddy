import json
from app.db_utils import save_to_db
from google.genai import types

# 1) Save a new expense record
save_expense_decl = {
    "name": "save_expense",
    "description": "Persist an expense record to the database.",
    "parameters": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "UUID of the expense"},
            "user_id": {"type": "string", "description": "ID of the user"},
            "date": {"type": "string", "description": "ISO date of the expense"},
            "price": {"type": "float", "description": "Amount spent in whole units"},
            "category": {"type": "string", "description": "Expense category"},
            "description": {"type": "string", "description": "Free‐form description"},
        },
        "required": ["id", "user_id", "date", "price", "category", "description"],
    },
}

# 2) Query by category
get_by_cat_decl = {
    "name": "get_expense_by_category",
    "description": "Fetch all expenses in a given category.",
    "parameters": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "User ID"},
            "category": {"type": "string", "description": "Expense category to filter"},
        },
        "required": ["user_id", "category"],
    },
}

# 3) Query by date range
get_by_date_decl = {
    "name": "get_expense_by_date",
    "description": "Fetch all expenses within a date range.",
    "parameters": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "User ID"},
            "start_date": {"type": "string", "description": "Start ISO date"},
            "end_date": {"type": "string", "description": "End ISO date"},
        },
        "required": ["user_id", "start_date", "end_date"],
    },
}

function_declarations = [save_expense_decl, get_by_cat_decl, get_by_date_decl]


# This is the actual function that would be called based on the model's suggestion
def save_expense(
    id: str,
    user_id: str,
    category: str,
    price: str,
    description: str = "",
    date: str = "",
) -> dict:
    """Save expense to db."""
    expense_data = {
        "id": id,
        "user_id": user_id,
        "category": category,
        "price": price,
        "description": description,
        "date": date,
    }

    # Save to database (assuming save_to_db is a function that handles DB operations)
    save_to_db(expense_data)

    print(f"Saving expense: {user_id}, {category}, {price}, {description}, {date}")
    return {"status": "success", "message": "Expense saved successfully."}
