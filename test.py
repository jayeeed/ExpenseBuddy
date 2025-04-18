import base64
import os
from google import genai
from google.genai import types


def generate():
    client = genai.Client(
        api_key=os.getenv("GEMENI_API_KEY"),
    )

    model = "gemini-2.0-flash"
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text="""food expense from 2025-01-01 to 2025-01-31 for user_id 12345""",
                ),
            ],
        ),
    ]
    tools = [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="save_expense",
                    description="Persist an expense record to the database.",
                    parameters=genai.types.Schema(
                        type=genai.types.Type.OBJECT,
                        required=["user_id", "price", "category"],
                        properties={
                            "id": genai.types.Schema(
                                type=genai.types.Type.STRING,
                            ),
                            "user_id": genai.types.Schema(
                                type=genai.types.Type.STRING,
                            ),
                            "date": genai.types.Schema(
                                type=genai.types.Type.STRING,
                            ),
                            "price": genai.types.Schema(
                                type=genai.types.Type.STRING,
                            ),
                            "category": genai.types.Schema(
                                type=genai.types.Type.STRING,
                            ),
                            "description": genai.types.Schema(
                                type=genai.types.Type.STRING,
                            ),
                        },
                    ),
                ),
                types.FunctionDeclaration(
                    name="get_expense_by_category",
                    description="Fetch all expenses for a specific category.",
                    parameters=genai.types.Schema(
                        type=genai.types.Type.OBJECT,
                        required=["user_id", "category"],
                        properties={
                            "user_id": genai.types.Schema(
                                type=genai.types.Type.STRING,
                            ),
                            "category": genai.types.Schema(
                                type=genai.types.Type.STRING,
                            ),
                        },
                    ),
                ),
                types.FunctionDeclaration(
                    name="get_expense_by_date",
                    description="Fetch all expenses within a date range.",
                    parameters=genai.types.Schema(
                        type=genai.types.Type.OBJECT,
                        required=["start_date", "end_date"],
                        properties={
                            "user_id": genai.types.Schema(
                                type=genai.types.Type.STRING,
                            ),
                            "start_date": genai.types.Schema(
                                type=genai.types.Type.STRING,
                            ),
                            "end_date": genai.types.Schema(
                                type=genai.types.Type.STRING,
                            ),
                        },
                    ),
                ),
            ]
        )
    ]
    generate_content_config = types.GenerateContentConfig(
        tools=tools,
        response_mime_type="text/plain",
    )

    for chunk in client.models.generate_content_stream(
        model=model,
        contents=contents,
        config=generate_content_config,
    ):
        print(chunk.text if chunk.function_calls is None else chunk.function_calls[0])


if __name__ == "__main__":
    generate()
