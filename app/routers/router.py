from datetime import datetime as date
import uuid
import json
import requests
import os
import logging
from google.genai import types
from fastapi import HTTPException, APIRouter
from app.agent_gai import agent, generate_content_config
from app.functions import save_expense, get_expenses_by_category, get_expenses_by_date

# Initialize FastAPI router and load environment variables.
router = APIRouter()

PAGE_ID = os.getenv("PAGE_ID")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
FB_MESSAGE_URL = (
    f"https://graph.facebook.com/v22.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global states to manage unpaid warnings.
unpaid_warned = set()


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


def current_time() -> str:
    """Returns the current date and time in a specific format."""
    return date.now().strftime("%Y-%m-%d")


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
                    model="gemini-2.0-flash",
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
                date=current_time(),
            )

            # Send confirmation
            img_payload = (
                f"*{image_json.get('category', '').upper()}*\n"
                f"*Expense*: {image_json.get('price', 0)}\n"
                f"*Description*: {image_json.get('description', '')}\n"
                f"*Date*: {current_time()}"
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

            # Detect intent via LLM
            intent_prompt = (
                "Determine the intent of the following message. The possible intents are: "
                "save_expense, get_by_category, get_by_date. Reply with a single intent keyword. "
                f"Message: {user_query}"
            )

            intent_resp = agent.models.generate_content(
                model="gemini-2.0-flash",
                contents=intent_prompt,
            ).text.strip()

            intent = intent_resp.lower().strip()

            logger.info(f"Detected intent: {intent}")

            query = f"NOTE: Current date: {current_time}. use current date as reference for date parameter in user query: {user_query}"

            # Execute based on intent
            if intent == "save_expense":
                # Let the LLM extract expense fields
                extraction = (
                    agent.models.generate_content(
                        model="gemini-2.0-flash",
                        contents=query,
                        config=generate_content_config,
                    )
                    .text.strip("```json")
                    .strip("```")
                )

                try:
                    expense = json.loads(extraction)
                except json.JSONDecodeError:
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to parse the JSON expense from the model.",
                    )
                save_expense(
                    id=str(uuid.uuid4()),
                    user_id=sender_id,
                    category=expense.get("category", ""),
                    price=expense.get("price", ""),
                    description=expense.get("description", ""),
                    date=current_time(),
                )
                send_fb_message(sender_id, {"text": "Expense saved successfully."})

            elif intent == "get_by_category":
                # Expect user_query contains category info
                parts = user_query.split()
                category = parts[-1]  # simplistic parsing
                records = get_expenses_by_category(user_id=sender_id, category=category)
                send_fb_message(
                    sender_id, {"text": f"Expenses in {category}: {records}"}
                )

            elif intent == "get_by_date":
                # Expect date in YYYY-MM-DD format
                parts = user_query.split()
                query_date = parts[-1]
                records = get_expenses_by_date(user_id=sender_id, date=query_date)
                send_fb_message(
                    sender_id, {"text": f"Expenses on {query_date}: {records}"}
                )

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
