import os
from google import genai
from google.genai import types

GEMENI_API_KEY = os.getenv("GEMENI_API_KEY")

agent = genai.Client(api_key=GEMENI_API_KEY)

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
                type=types.Type.INTEGER,
            ),
            "description": types.Schema(
                type=types.Type.STRING,
            ),
        },
    ),
)
