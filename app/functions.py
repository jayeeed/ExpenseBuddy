import json
from app.db_utils import save_to_db, db_query
from google.genai import types


tools = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="save_expense",
                description="Persist an expense record to the database.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    required=["user_id", "price", "category"],
                    properties={
                        "id": types.Schema(
                            type=types.Type.STRING,
                        ),
                        "user_id": types.Schema(
                            type=types.Type.STRING,
                        ),
                        "date": types.Schema(
                            type=types.Type.STRING,
                        ),
                        "price": types.Schema(
                            type=types.Type.STRING,
                        ),
                        "category": types.Schema(
                            type=types.Type.STRING,
                        ),
                        "description": types.Schema(
                            type=types.Type.STRING,
                        ),
                    },
                ),
            ),
            types.FunctionDeclaration(
                name="get_expense_by_category",
                description="Fetch all expenses for a specific category.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    required=["user_id", "category"],
                    properties={
                        "user_id": types.Schema(
                            type=types.Type.STRING,
                        ),
                        "category": types.Schema(
                            type=types.Type.STRING,
                        ),
                    },
                ),
            ),
            types.FunctionDeclaration(
                name="get_expense_by_date",
                description="Fetch all expenses within a date range.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    required=["start_date", "end_date"],
                    properties={
                        "user_id": types.Schema(
                            type=types.Type.STRING,
                        ),
                        "start_date": types.Schema(
                            type=types.Type.STRING,
                        ),
                        "end_date": types.Schema(
                            type=types.Type.STRING,
                        ),
                    },
                ),
            ),
        ]
    )
]
tool_config = types.GenerateContentConfig(
    tools=tools,
    response_mime_type="text/plain",
)


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


def get_expenses_by_category(user_id: str, category: str) -> dict:
    """Get expenses by category."""
    query = f"""
        SELECT * FROM expenses
        WHERE user_id = '{user_id}' AND category = '{category.lower()}'
    """

    expenses = db_query(query)

    print(f"Fetching expenses for user: {user_id}, category: {category}")

    return {"status": "success", "expenses": expenses}


def get_expenses_by_date(user_id: str, date: str) -> dict:
    """Get expenses by date range."""
    query = f"""
        SELECT * FROM expenses
        WHERE user_id = '{user_id}' AND date = '{date}'
    """

    expenses = db_query(query)

    print(f"Fetching expenses for user: {user_id}, date: {date}")
    return {"status": "success", "expenses": expenses}
