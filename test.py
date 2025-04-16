import os
import uuid
from google import genai
from google.genai import types

# In‑memory "database" for demo purposes
EXPENSE_DB = []

# --- Step 1: Define function declarations ---

save_expense_fn = {
    "name": "save_expense",
    "description": "Save an expense record with date, amount, category, and description.",
    "parameters": {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "Date of the expense in YYYY-MM-DD format.",
            },
            "amount": {"type": "number", "description": "Amount spent."},
            "category": {
                "type": "string",
                "enum": [
                    "food",
                    "travel",
                    "transport",
                    "entertainment",
                    "utilities",
                    "grocery",
                    "shopping",
                    "electronics",
                    "health",
                    "miscellaneous",
                    "automobile",
                    "other",
                    "none",
                ],
                "description": "Category of the expense.",
            },
            "description": {
                "type": "string",
                "description": "Description of what was purchased.",
            },
        },
        "required": ["date", "amount", "category", "description"],
    },
}

get_by_cat_fn = {
    "name": "get_expenses_by_category",
    "description": "Retrieve all expenses for a given category.",
    "parameters": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "Category to filter expenses by.",
            }
        },
        "required": ["category"],
    },
}

get_by_date_fn = {
    "name": "get_expenses_by_date",
    "description": "Retrieve all expenses for a specific date.",
    "parameters": {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "Date to filter expenses by (YYYY-MM-DD).",
            }
        },
        "required": ["date"],
    },
}

# --- Step 2: Configure the GenAI client with your function declarations ---
GEMENI_API_KEY = os.getenv("GEMENI_API_KEY")
client = genai.Client(api_key=GEMENI_API_KEY)
tools = types.Tool(
    function_declarations=[save_expense_fn, get_by_cat_fn, get_by_date_fn]
)
config = types.GenerateContentConfig(
    tools=[tools]
)  # attach our tools :contentReference[oaicite:1]{index=1}

# --- Step 3: Ask the model and check for a function call ---

user_input = (
    "Coffee at Starbucks on for $5.00 on 2025-10-01 description: latte category: food"
)
response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents=user_input,
    config=config,
)

candidate = response.candidates[0].content.parts[0]
if candidate.function_call:
    name = candidate.function_call.name
    args = candidate.function_call.args

    # --- Step 4: Execute the corresponding function in your app ---
    if name == "save_expense":
        # Generate a unique ID and store
        expense = {
            "id": uuid.uuid4().hex,
            "date": args["date"],
            "amount": args["amount"],
            "category": args["category"],
            "description": args["description"],
        }
        EXPENSE_DB.append(expense)
        function_result = {"status": "success", "expense": expense}

    elif name == "get_expenses_by_category":
        function_result = [
            exp for exp in EXPENSE_DB if exp["category"] == args["category"]
        ]

    elif name == "get_expenses_by_date":
        function_result = [exp for exp in EXPENSE_DB if exp["date"] == args["date"]]

    else:
        function_result = {"error": f"No handler for {name}"}

    # --- Step 5: Send the result back to the model for a final reply ---
    followup = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[
            {
                "role": "assistant",
                "parts": [{"function_call": candidate.function_call}],
            },
            {
                "role": "function",
                "name": name,
                "parts": [{"text": str(function_result)}],
            },
        ],
        config=types.GenerateContentConfig(),  # no tools needed here
    )
    print(followup.text)

else:
    # Model returned a direct text response
    print(candidate.text)
