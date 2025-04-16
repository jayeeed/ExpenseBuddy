from datetime import datetime as date
import uuid
import requests
import os
import logging
from google.genai.types import *
from fastapi import HTTPException, APIRouter
from google.genai import types
from app.agent_gai import agent, generate_content_config
from app.functions import save_expense

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
            FB_MESSAGE_URL, json={"recipient": {"id": recipient_id}, "message": message}
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


def get_chat_history(user_id: str) -> str:
    """Fetches the latest 5 incoming messages from the Facebook Conversations API for a specific user."""
    fb_api_url = (
        f"https://graph.facebook.com/v22.0/me/conversations?"
        f"fields=messages{{message,from,created_time}}&access_token={PAGE_ACCESS_TOKEN}"
    )
    response = requests.get(fb_api_url)
    history_text = ""
    if response.status_code == 200:
        fb_json = response.json()
        messages_list = [
            msg
            for conv in fb_json.get("data", [])
            for msg in conv.get("messages", {}).get("data", [])
            if str(msg.get("from", {}).get("id")) == str(user_id)
        ]
        messages_list.sort(key=lambda m: m.get("created_time", ""), reverse=True)
        latest_five = messages_list[:5]
        history_text = "\n".join(
            [f"User: {msg.get('message', '')}" for msg in latest_five]
        )
    else:
        logger.error(f"Failed to fetch latest messages: {response.text}")
    return history_text


def current_time() -> str:
    """Returns the current date and time in a specific format."""
    return date.now().strftime("%Y-%m-%d %H:%M:%S")


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

        # Process text messages.
        if "message" in message_data and "text" in message_data["message"]:
            user_query = message_data["message"]["text"]
            if not user_query:
                raise HTTPException(
                    status_code=400, detail="No text provided in the message."
                )

            text_response = (
                agent.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=user_query,
                    config=generate_content_config,
                )
                .text.strip("```json")
                .strip("```")
            )

            logger.info(f"Text response: {text_response}")

            # Parse the JSON response.
            try:
                text_response = json.loads(text_response)
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to parse the JSON response from the model.",
                )

            text_payload = (
                f"*{text_response.get('category', '').strip().upper()}*\n\n"
                f"*Expense*: ${text_response.get('price', 0)}\n\n"
                f"*Description*: {text_response.get('description', '').strip()}\n\n"
                f"*Date*: {current_time()}\n\n"
            )

            send_fb_message(sender_id, {"text": text_payload})

            save_expense(
                id=str(uuid.uuid4()),
                user_id=sender_id,
                category=text_response.get("category", ""),
                price=text_response.get("price", ""),
                description=text_response.get("description", ""),
                date=current_time(),
            )

        elif "message" in message_data and "attachments" in message_data["message"]:
            attachments = message_data["message"]["attachments"]

            if attachments and isinstance(attachments, list):
                reciept_img = attachments[0].get("payload", {}).get("url")
                if not reciept_img:
                    raise HTTPException(
                        status_code=400,
                        detail="No valid image URL provided in the message.",
                    )
            else:
                raise HTTPException(
                    status_code=400, detail="No attachments found in the message."
                )

            response = requests.get(reciept_img)
            if response.status_code == 200:
                img_bytes = response.content
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Failed to fetch the image from the provided URL.",
                )

            image_response = (
                agent.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[
                        types.Part.from_bytes(
                            data=img_bytes,
                            mime_type="image/jpeg",
                        ),
                        "Detect expense from the image.",
                    ],
                    config=generate_content_config,
                )
                .text.strip("```json")
                .strip("```")
            )

            # Parse the JSON response.
            try:
                image_response = json.loads(image_response)
                logger.info(f"Image response: {image_response}")
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to parse the JSON response from the model.",
                )

            img_payload = (
                f"*{image_response.get('category', '').strip().upper()}*\n\n"
                f"*Expense*: {image_response.get('price', 0)}\n\n"
                f"*Description*: {image_response.get('description', '').strip()}\n\n"
                f"*Date*: {current_time()}\n\n"
            )

            send_fb_message(sender_id, {"text": img_payload})

            save_expense(
                id=str(uuid.uuid4()),
                user_id=sender_id,
                category=image_response.get("category", ""),
                price=image_response.get("price", ""),
                description=image_response.get("description", ""),
                date=current_time(),
            )

    except Exception as e:
        logger.error(f"Error in webhook endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))
