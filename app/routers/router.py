from datetime import datetime as date
import uuid
import json
import requests
import os
import logging
from google.genai import types
from fastapi import HTTPException, APIRouter
from app.agent_gai import agent, generate_content_config
from app.functions import (
    save_expense,
    get_expenses_by_category,
    get_expenses_by_date,
    func_config,
)

# Initialize FastAPI router and load environment variables.
router = APIRouter()

PAGE_ID = os.getenv("PAGE_ID")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
FB_MESSAGE_URL = (
    f"https://graph.facebook.com/v22.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
)
VISION_MODEL = "gemini-2.0-flash"
TEXT_MODEL = "gemini-1.5-flash"

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global states to manage unpaid warnings.
unpaid_warned = set()

current_date = date.now().strftime("%Y-%m-%d")


def send_fb_message(recipient_id: str, message: dict) -> None:
    """Helper function to send a Facebook message."""
    try:
        response = requests.post(
            FB_MESSAGE_URL,
            json={"recipient": {"id": recipient_id}, "message": message},
        )
        logger.info(
            f"Sent message to {recipient_id}. Response code: {response.status_code}, Response text: {response.text}"
        )
    except Exception as e:
        logger.error(f"Error sending message to {recipient_id}: {e}")


def is_paid_user(sender_id: str) -> bool:
    """
    Checks if the sender has a 'Paid' status by comparing the sender_id
    against a predefined list of paid user IDs.
    """
    paid_ids = {"9317213844980928", "9502672683131798", "7573277649370618"}
    return str(sender_id) in paid_ids


@router.post("/webhook")
async def receive_message(data: dict):
    sender_id = None
    try:
        entry = data.get("entry", [])
        if not entry:
            logger.error("No entry found in payload.")
            return "200 OK HTTPS."

        messaging = entry[0].get("messaging", [])
        if not messaging:
            logger.error("No messaging events found in payload.")
            return "200 OK HTTPS."

        message_data = messaging[0]
        sender_id = message_data.get("sender", {}).get("id")

        # Ignore messages if they originate from the page itself.
        if str(sender_id) == str(PAGE_ID):
            return {"status": "ignored", "sender_id": sender_id}

        # Paid user check.
        if not is_paid_user(sender_id):
            if sender_id not in unpaid_warned:
                send_fb_message(
                    sender_id,
                    {
                        "text": "You are not a paid user. Please subscribe to our service."
                    },
                )
                unpaid_warned.add(sender_id)
            return {"status": "not_paid", "sender_id": sender_id}

        # Determine if message has attachments (URL)
        if "message" in message_data and "attachments" in message_data["message"]:
            # Always treat attachments as save_expense
            attachments = message_data["message"]["attachments"]
            if not attachments or not isinstance(attachments, list):
                raise HTTPException(
                    status_code=400, detail="No attachments found in the message."
                )
            receipt_url = attachments[0].get("payload", {}).get("url")
            if not receipt_url:
                raise HTTPException(
                    status_code=400,
                    detail="No valid image URL provided in the message.",
                )

            # Fetch image bytes
            response = requests.get(receipt_url)
            if response.status_code != 200:
                raise HTTPException(
                    status_code=400,
                    detail="Failed to fetch the image from the provided URL.",
                )
            img_bytes = response.content

            # Use LLM to detect expense from image
            image_response = (
                agent.models.generate_content(
                    model=VISION_MODEL,
                    contents=[
                        types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                        "Detect expense from the image.",
                    ],
                    config=generate_content_config,
                )
                .text.strip("```json")
                .strip("```")
            )
            try:
                image_json = json.loads(image_response)
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to parse the JSON response from the model.",
                )

            # Save expense
            save_expense(
                id=str(uuid.uuid4()),
                user_id=sender_id,
                category=image_json.get("category", ""),
                price=image_json.get("price", ""),
                description=image_json.get("description", ""),
                date=current_date,
            )

            # Send confirmation
            img_payload = (
                f"*{image_json.get('category', '').upper()}*\n"
                f"*Expense*: {image_json.get('price', 0)}\n"
                f"*Description*: {image_json.get('description', '')}\n"
                f"*Date*: {current_date}"
            )
            send_fb_message(sender_id, {"text": img_payload})
            return {"status": "saved_image", "sender_id": sender_id}

        # Process text messages
        if "message" in message_data and "text" in message_data["message"]:
            user_query = message_data["message"]["text"]
            if not user_query:
                raise HTTPException(
                    status_code=400, detail="No text provided in the message."
                )
            logger.info(f"Received user query: ********{user_query}********")

            current_date = date.now().strftime("%Y-%m-%d")

            intent_prompt = (
                "\n# Instructions: (Don't use these in response only for reference)"
                f"\n# Note: 'today': {current_date}"
                "\n- Use Current Date as date reference."
                f"\n- Example: 'yesterday' (gotokal/গতকাল) will be day before {current_date} and 'tomorrow' (agamikal/আগামীকাল) will be day after {current_date}."
                "\n- Week start from Sunday"
                "\n- Weekend is Friday and Saturday"
                "\n- For 'save_expense' function price must be given in number format in user query."
                "\n- Don't use 'save_expense' function if user query doesn't contain price in numeric format."
                "\n- Disregard insignificant/irrelevant terms related to expenses."
                "\n- Don't ask for user id, it's given below."
                f"user_id: '{sender_id}', \nuser_query: '{user_query}'"
            )

            intent_response = agent.models.generate_content(
                model=TEXT_MODEL,
                contents=intent_prompt,
                config=func_config,
            )
            # logger.info(f"Intent response: {intent_response}")

            intent_args = intent_response.function_calls[0].args
            logger.info(f"Function params: {intent_args}")

            intent = intent_response.function_calls[0].name
            logger.info(f"Intent: {intent}")

            # Execute based on intent
            if intent == "save_expense":
                exp_category = intent_args.get("category", "")
                exp_price = intent_args.get("price", "")
                exp_description = intent_args.get("description", "")

                save_expense(
                    id=str(uuid.uuid4()),
                    user_id=sender_id,
                    category=exp_category,
                    price=exp_price,
                    description=exp_description,
                    date=current_date,
                )
                send_fb_message(sender_id, {"text": "Expense saved successfully."})

            elif intent == "get_expense_by_category":
                category = intent_args.get("category", "")

                query_lang = intent_args.get("language", "")
                logger.info(f"Language: {query_lang}")

                if not category:
                    raise HTTPException(
                        status_code=400,
                        detail="Category not provided in the intent response.",
                    )

                records = get_expenses_by_category(user_id=sender_id, category=category)

                normalizer_prompt = f"NOTE: language list: ['english', 'bengali']. Special case: Also reply in bengali if user query is in benglish (Bengali written using English characters). User query language: {query_lang}.\nSo response output must be in {query_lang} language. You have been given a list of expenses:\n\n{records}.\n\n Make sure to format the response in a concised (under 200 characters) human readable format. Just plain human like response. DO NOT include 'Expenses on 2025-04-18 for user 7573277649370618:' this kind of text on the response. Use currency symbol as Taka '৳'. Response:"

                normalized_text = agent.models.generate_content(
                    model=TEXT_MODEL,
                    contents=normalizer_prompt,
                ).text
                logger.info(f"Normalizer response: {normalized_text}")

                send_fb_message(sender_id, {"text": normalized_text})

            elif intent == "get_expense_by_date":
                start_date = intent_args.get("start_date", "")
                end_date = intent_args.get("end_date", "")

                query_lang = intent_args.get("language", "")
                logger.info(f"Language: {query_lang}")

                if not start_date or not end_date:
                    raise HTTPException(
                        status_code=400,
                        detail="Date range not provided in the intent response.",
                    )

                records = get_expenses_by_date(
                    user_id=sender_id, start_date=start_date, end_date=end_date
                )

                normalizer_prompt = f"NOTE: language list: ['english', 'bengali']. Special case: Also reply in bengali if user query is in benglish (Bengali written using English characters). User query language: {query_lang}.\nSo response output must be in {query_lang} language. You have been given a list of expenses:\n\n{records}.\n\n Make sure to format the response in a concised (under 200 characters) human readable format. Just plain human like response. DO NOT include 'Expenses on 2025-04-18 for user 7573277649370618:' this kind of text on the response. Use currency symbol as Taka '৳'. Response:"

                normalizer = agent.models.generate_content(
                    model=TEXT_MODEL,
                    contents=normalizer_prompt,
                ).text

                send_fb_message(sender_id, {"text": normalizer})

            else:
                send_fb_message(sender_id, {"text": "Sorry, I didn't understand that."})

            return {"status": intent, "sender_id": sender_id}

        # No matching handler
        return {"status": "no_action", "sender_id": sender_id}

    except HTTPException as he:
        logger.error(f"HTTPException in webhook endpoint: {he.detail}")
        raise he
    except Exception as e:
        logger.error(f"Error in webhook endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))
