import json
from app.db_utils import save_to_db, db_query
from google.genai import types
from enum import Enum


class Category(Enum):
    FOOD = "food"
    TRAVEL = "travel"
    TRANSPORT = "transport"
    REPAIR = "repair"
    ENTERTAINMENT = "entertainment"
    UTILITIES = "utilities"
    GROCERY = "grocery"
    SHOPPING = "shopping"
    ELECTRONICS = "electronics"
    HEALTH = "health"
    MISCELLANEOUS = "miscellaneous"
    AUTOMOBILE = "automobile"
    OTHER = "other"
    NONE = "none"


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
                        "user_id": types.Schema(
                            type=types.Type.INTEGER,
                            example="738126784619",
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
                            description="Amount spent in float.",
                        ),
                        "category": types.Schema(
                            type=types.Type.STRING,
                            example="Food",
                            description="Category of the expense.",
                        ),
                        "description": types.Schema(
                            type=types.Type.STRING,
                            example="Lunch at a restaurant",
                            description="Description of the expense.",
                        ),
                        "language": types.Schema(
                            type=types.Type.STRING,
                            example="english",
                            enum=["english", "bengali"],
                            description="Language of the query.",
                        ),
                    },
                ),
            ),
            types.FunctionDeclaration(
                name="get_expenses_by_category",
                description="Fetch all expenses for a specific category.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    required=["user_id", "category"],
                    properties={
                        "user_id": types.Schema(
                            type=types.Type.STRING,
                            example="738126784619",
                            description="Identifier for the user.",
                        ),
                        "category": types.Schema(
                            type=types.Type.STRING,
                            example="Food",
                            description="Category of the expense.",
                        ),
                        "language": types.Schema(
                            type=types.Type.STRING,
                            example="english",
                            enum=["english", "bengali"],
                            description="Language of the query.",
                        ),
                    },
                ),
            ),
            types.FunctionDeclaration(
                name="get_expenses_by_date",
                description="Fetch all expenses within a date range.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    required=["user_id", "start_date", "end_date"],
                    properties={
                        "user_id": types.Schema(
                            type=types.Type.STRING,
                            example="738126784619",
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
            types.FunctionDeclaration(
                name="greetings",
                description="Greet the user.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "user_id": types.Schema(
                            type=types.Type.STRING,
                            example="738126784619",
                            description="Identifier for the user.",
                        ),
                        "greeting": types.Schema(
                            type=types.Type.STRING,
                            example="Hi/Hello",
                            description="Greeting message.",
                        ),
                        "language": types.Schema(
                            type=types.Type.STRING,
                            example="english",
                            enum=["english", "bengali"],
                            description="Language of the query.",
                        ),
                    },
                ),
            ),
            types.FunctionDeclaration(
                name="irrelevant",
                description="Output for irrelevant queries.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "user_id": types.Schema(
                            type=types.Type.STRING,
                            example="738126784619",
                            description="Identifier for the user.",
                        ),
                        "language": types.Schema(
                            type=types.Type.STRING,
                            example="english",
                            enum=["english", "bengali"],
                            description="Language of the query.",
                        ),
                        "query": types.Schema(
                            type=types.Type.STRING,
                            example="Want to know latest news",
                            description="irrelevant query.",
                        ),
                    },
                ),
            ),
            types.FunctionDeclaration(
                name="get_all_expenses",
                description="Fetch all expenses.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "user_id": types.Schema(
                            type=types.Type.STRING,
                            example="738126784619",
                            description="Identifier for the user.",
                        ),
                        "language": types.Schema(
                            type=types.Type.STRING,
                            example="english",
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
    # tool_config=types.ToolConfig(
    #     function_calling_config=types.FunctionCallingConfig(mode="AUTO"),
    # ),
    system_instruction="You are a helpful assistant which will only execute functions regarding expense related queries. Must be in English or Bengali. Must select category from the following list: Food, Transport, Entertainment, Travel, Health, Shopping, Utilities, Education, Miscellaneous, Groceries, Dining, Subscriptions, Gifts. Get appropiate catagory according to user query. If can't decide category just use 'miscellaneous'.",
)

# func_config = {
#     "tools": tools,
#     "automatic_function_calling": {"disable": True},
#     "tool_config": {"function_calling_config": {"mode": "any"}},
# }


# This is the actual function that would be called based on the model's suggestion
def save_expense(
    id: str,
    user_id: int,
    category: Category,
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

    save_to_db(expense_data)

    return {"status": "success", "message": "Expense saved!"}


def get_all_expenses(user_id: str) -> dict:
    """Get all expenses."""
    query = f"""SELECT * FROM expenses
                WHERE user_id = '{user_id}'"""

    return db_query(query)


def get_expenses_by_category(user_id: str, category: Category) -> dict:
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
