import os
from google import genai
from google.genai import types

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

agent = genai.Client(api_key=GEMINI_API_KEY)

generate_content_config = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=types.Schema(
        type=types.Type.OBJECT,
        required=["category", "price"],
        properties={
            "category": types.Schema(
                type=types.Type.STRING,
            ),
            "price": types.Schema(
                type=types.Type.STRING,
            ),
            "description": types.Schema(
                type=types.Type.STRING,
            ),
            "date": types.Schema(
                type=types.Type.STRING,
            ),
        },
    ),
)
