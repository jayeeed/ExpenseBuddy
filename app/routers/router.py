from datetime import datetime
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

router = APIRouter()

# Environment
PAGE_ID = os.getenv("PAGE_ID")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
FB_MSG_API_BASE = os.getenv("FB_MSG_API_BASE")
FB_MESSAGE_URL = (
    f"https://graph.facebook.com/v22.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
)

VISION_MODEL = os.getenv("VISION_MODEL")
TEXT_MODEL = os.getenv("TEXT_MODEL")

# Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# In‑memory set to track unpaid users we’ve warned already
unpaid_warned = set()


def send_fb_message(recipient_id: str, message: dict) -> None:
    """POST a message to the Messenger Graph API and log the result."""
    try:
        resp = requests.post(
            FB_MESSAGE_URL,
            json={"recipient": {"id": recipient_id}, "message": message},
        )
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to send message to {recipient_id}: {e}")


def is_paid_user(sender_id: str) -> bool:
    """Simple whitelist check; replace with your real billing lookup."""
    paid_ids = {"9317213844980928", "9502672683131798", "7573277649370618"}
    return sender_id in paid_ids


def fetch_and_parse_attachment(attachment: dict) -> dict:
    """Download an attachment and run it through the vision/text model to extract expense JSON."""
    kind = attachment.get("type")
    url = attachment.get("payload", {}).get("url")
    if not url:
        raise HTTPException(status_code=400, detail="Attachment URL missing.")

    resp = requests.get(url)
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to fetch attachment.")

    part = types.Part.from_bytes(
        data=resp.content, mime_type="image/jpeg" if kind == "image" else "audio/mpeg"
    )
    prompt = "Detect expense from the attachment and return a JSON object with keys: category, price, description, date."
    llm_resp = agent.models.generate_content(
        model=VISION_MODEL if kind == "image" else TEXT_MODEL,
        contents=[part, prompt],
        config=generate_content_config,
    )
    text = llm_resp.text.strip("```json").strip("```").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON from LLM: {text}")
        raise HTTPException(status_code=500, detail="Invalid JSON from LLM.")


def handle_attachment_event(sender_id: str, attachments: list) -> None:
    """Process the first attachment as an expense and confirm to user."""
    data = fetch_and_parse_attachment(attachments[0])
    expense_date = data.get("date") or datetime.now().strftime("%Y-%m-%d")

    try:
        save_expense(
            id=str(uuid.uuid4()),
            user_id=sender_id,
            category=data.get("category", ""),
            price=data.get("price", 0),
            description=data.get("description", ""),
            date=expense_date,
        )
        reply = (
            f"*{data.get('category','').upper()}* saved!\n\n"
            f"• Amount: {data.get('price',0)}\n"
            f"• Description: {data.get('description','')}\n"
            f"• Date: {expense_date}"
        )
        send_fb_message(sender_id, {"text": reply})

    except Exception as e:
        logger.error(f"Error saving attachment expense: {e}")
        send_fb_message(sender_id, {"text": "Sorry, I couldn't save your expense."})


def call_intent_llm(sender_id: str, user_query: str) -> tuple[str, dict]:
    """
    Ask the LLM to choose one of our functions and return (function_name, args).
    Assumes func_config has been set up with google.genai types.FunctionDeclaration.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    system_prompt = f"Date: {today}. Route the user's query to one of our functions."
    user_prompt = f"user_id: '{sender_id}', user_query: '{user_query}'"

    resp = agent.models.generate_content(
        model=TEXT_MODEL, contents=[system_prompt, user_prompt], config=func_config
    )

    fc = resp.function_calls[0]
    raw_args = fc.args
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
    except json.JSONDecodeError:
        logger.error(f"Could not parse function args JSON: {raw_args}")
        args = {}

    return fc.name, args


def handle_text_event(sender_id: str, text: str) -> None:
    """Dispatch on the LLM‑determined intent."""
    intent, args = call_intent_llm(sender_id, text)
    expense_date = args.get("date") or datetime.now().strftime("%Y-%m-%d")

    if intent == "save_expense":
        # Wrap just the save so we don't catch unrelated bugs
        try:
            save_expense(
                id=str(uuid.uuid4()),
                user_id=sender_id,
                category=args.get("category", ""),
                price=args.get("price", 0),
                description=args.get("description", ""),
                date=args.get("date", expense_date),
            )
            logger.info(f"Saved expense: {args}")

            reply = (
                f"*{args.get('category','').upper()}* saved!\n\n"
                f"• Amount: {args.get('price',0)}\n"
                f"• Description: {args.get('description','')}\n"
                f"• Date: {args.get('date', expense_date)}"
            )
            logger.info(f"Reply: {reply}")

            send_fb_message(sender_id, {"text": reply})

        except Exception as e:
            logger.error(f"Error in save_expense branch: {e}")
            send_fb_message(sender_id, {"text": "Sorry, I couldn't save your expense."})

    elif intent == "get_expenses_by_category":
        try:
            records = get_expenses_by_category(user_id=sender_id, **args)
            if not records:
                send_fb_message(
                    sender_id, {"text": "No expenses found in that category."}
                )
                return

            # Let the LLM format nicely
            prompt = f"Format these records concisely: {records}"
            summary = agent.models.generate_content(
                model=TEXT_MODEL, contents=prompt
            ).text
            send_fb_message(sender_id, {"text": summary})
        except Exception as e:
            logger.error(f"Error fetching by category: {e}")
            send_fb_message(sender_id, {"text": "Couldn't retrieve your expenses."})

    elif intent == "get_expenses_by_date":
        try:
            records = get_expenses_by_date(user_id=sender_id, **args)
            if not records:
                send_fb_message(sender_id, {"text": "No expenses found on that date."})
                return

            prompt = f"Format these records concisely: {records}"
            summary = agent.models.generate_content(
                model=TEXT_MODEL, contents=prompt
            ).text
            send_fb_message(sender_id, {"text": summary})
        except Exception as e:
            logger.error(f"Error fetching by date: {e}")
            send_fb_message(sender_id, {"text": "Couldn't retrieve your expenses."})

    else:
        send_fb_message(sender_id, {"text": "Sorry, I didn't understand that."})


@router.post("/webhook")
async def receive_message(data: dict):
    entry = data.get("entry", [])
    if not entry:
        return {"status": "no_events"}

    messaging = entry[0].get("messaging", [])
    if not messaging:
        return {"status": "no_events"}

    event = messaging[0]
    sender_id = str(event.get("sender", {}).get("id", ""))
    if not sender_id or sender_id == PAGE_ID:
        return {"status": "ignored"}

    # Check payment
    if not is_paid_user(sender_id):
        if sender_id not in unpaid_warned:
            send_fb_message(
                sender_id, {"text": "Please subscribe to use this service."}
            )
            unpaid_warned.add(sender_id)
        return {"status": "not_paid"}

    # Dispatch by text vs attachment
    message = event.get("message", {})
    if "attachments" in message:
        handle_attachment_event(sender_id, message["attachments"])
    elif "text" in message:
        handle_text_event(sender_id, message["text"])

    return {"status": "processed"}
