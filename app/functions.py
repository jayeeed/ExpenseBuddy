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
                            example="12345",
                            description="Unique identifier for the expense.",
                        ),
                        "user_id": types.Schema(
                            type=types.Type.INTEGER,
                            example="user_123",
                            description="Identifier for the user.",
                        ),
                        "date": types.Schema(
                            type=types.Type.STRING,
                            example="2025-01-01",
                            description="Date of the expense in YYYY-MM-DD format.",
                        ),
                        "price": types.Schema(
                            type=types.Type.NUMBER,
                            example="100.00",
                            description="Amount spent.",
                        ),
                        "category": types.Schema(
                            type=types.Type.STRING,
                            example="Food",
                            enum=[
                                "Food",
                                "Transport",
                                "Entertainment",
                                "Travel",
                                "Other",
                                "Health",
                                "Shopping",
                                "Utilities",
                                "Education",
                                "Miscellaneous",
                                "Groceries",
                                "Dining",
                                "Subscriptions",
                                "Gifts",
                            ],
                            description="Category of the expense.",
                        ),
                        "description": types.Schema(
                            type=types.Type.STRING,
                            example="Lunch at a restaurant",
                            description="Description of the expense.",
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
                            example="user_123",
                            description="Identifier for the user.",
                        ),
                        "category": types.Schema(
                            type=types.Type.STRING,
                            example="Food",
                            enum=[
                                "Food",
                                "Transport",
                                "Entertainment",
                                "Travel",
                                "Other",
                                "Health",
                                "Shopping",
                                "Utilities",
                                "Education",
                                "Miscellaneous",
                                "Groceries",
                                "Dining",
                                "Subscriptions",
                                "Gifts",
                            ],
                            description="Category of the expense.",
                        ),
                        "language": types.Schema(
                            type=types.Type.STRING,
                            example="en",
                            enum=["english", "bengali"],
                            description="Language of the query.",
                        ),
                    },
                ),
            ),
            types.FunctionDeclaration(
                name="get_expense_by_date",
                description="Fetch all expenses within a date range.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    required=["user_id", "start_date", "end_date"],
                    properties={
                        "user_id": types.Schema(
                            type=types.Type.STRING,
                            example="user_123",
                            description="Identifier for the user.",
                        ),
                        "start_date": types.Schema(
                            type=types.Type.STRING,
                            example="2025-01-01",
                            description="Start date of the range in YYYY-MM-DD format.",
                        ),
                        "end_date": types.Schema(
                            type=types.Type.STRING,
                            example="2025-01-31",
                            description="End date of the range in YYYY-MM-DD format.",
                        ),
                        "language": types.Schema(
                            type=types.Type.STRING,
                            example="en",
                            enum=["english", "bengali"],
                            description="Language of the query.",
                        ),
                    },
                ),
            ),
        ]
    )
]
func_config = types.GenerateContentConfig(
    tools=tools,
    response_mime_type="text/plain",
    tool_config=types.ToolConfig(
        function_calling_config=types.FunctionCallingConfig(mode="ANY"),
    ),
)


# This is the actual function that would be called based on the model's suggestion
def save_expense(
    id: str,
    user_id: int,
    category: str,
    price: float,
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
        SELECT * FROM expensex
        WHERE user_id = '{user_id}' AND category = '{category.lower()}'
    """

    expenses = db_query(query)

    return {"status": "success", "expenses": expenses}


def get_expenses_by_date(user_id: str, start_date: str, end_date: str) -> dict:
    """Get expenses by date range."""
    query = f"""
        SELECT * FROM expensex
        WHERE user_id = '{user_id}' AND date BETWEEN '{start_date}' AND '{end_date}'
    """

    expenses = db_query(query)

    return {"status": "success", "expenses": expenses}
