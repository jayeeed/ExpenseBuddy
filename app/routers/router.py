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
    get_all_expenses,
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
    """
    Download an image attachment and run it through the vision model
    to extract expense JSON.
    """
    kind = attachment.get("type")
    if kind != "image":
        raise HTTPException(
            status_code=400,
            detail="fetch_and_parse_attachment only supports image attachments.",
        )

    url = attachment.get("payload", {}).get("url")
    if not url:
        raise HTTPException(status_code=400, detail="Attachment URL missing.")

    resp = requests.get(url)
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to fetch attachment.")

    part = types.Part.from_bytes(data=resp.content, mime_type="image/jpeg")
    prompt = (
        "Detect expense from the image and return a JSON object with keys: "
        "category, price, description, date."
    )

    llm_resp = agent.models.generate_content(
        model=VISION_MODEL,
        contents=[part, prompt],
        config=generate_content_config,
    )

    text = llm_resp.text.strip("```json").strip("```").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON from LLM: {text}")
        raise HTTPException(status_code=500, detail="Invalid JSON from LLM.")


def transcribe_audio_attachment(sender_id: str, attachment: dict) -> str:
    """
    Download an audio attachment and run it through the text model
    to get a transcription.
    """
    url = attachment.get("payload", {}).get("url")
    if not url:
        raise HTTPException(status_code=400, detail="Attachment URL missing.")

    resp = requests.get(url)
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to fetch attachment.")

    part = types.Part.from_bytes(data=resp.content, mime_type="audio/mpeg")
    prompt = "Transcribe the audio message and return plain text. Response:"

    llm_resp = agent.models.generate_content(
        model=TEXT_MODEL,
        contents=[part, prompt],
    )
    send_fb_message(sender_id, {"text": llm_resp.text})

    # strip any markdown/code fences
    return llm_resp.text.strip("```").strip()


def handle_attachment_event(sender_id: str, attachments: list) -> None:
    """Process the first image attachment as an expense and confirm to user."""
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
    """
    current_date = datetime.now().strftime("%Y-%m-%d")
    user_prompt = (
        "\n# Instructions: (Don't use these in response only for reference)"
        f"\n# Note: 'today': {current_date}"
        "\n- Use Current Date as date reference."
        f"\n- Example: 'yesterday' will be day before {current_date}."
        "\n- Week start from Sunday, Weekend is Friday and Saturday."
        "\n- For 'save_expense' function price must be numeric."
        "\n- Don't use 'save_expense' if no numeric price in query."
        "\n- Decline function call if price is 0 or not numeric."
        "\n- Disregard irrelevant terms."
        "\n- Don't ask for user id, it's given below."
        f"\nuser_id: '{sender_id}', user_query: '{user_query}'"
    )

    resp = agent.models.generate_content(
        model=TEXT_MODEL, contents=user_prompt, config=func_config
    )

    fc = resp.function_calls[0]
    raw_args = fc.args
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        logger.info(
            f"\n*************************************\n"
            f"Function call: {fc.name}, args: {args}\n"
            "*************************************\n"
        )
    except json.JSONDecodeError:
        logger.error(f"Could not parse function args JSON: {raw_args}")
        args = {}

    return fc.name, args


def query_summary(records, query_lang):
    prompt = (
        f"NOTE: language list: ['english','bengali'].\n"
        f"User query language: {query_lang}.\n"
        "Given these expenses, format a concise (<200 chars) human response "
        "using '৳' for currency.\n"
        f"{records}\nResponse:"
    )

    summary = agent.models.generate_content(model=TEXT_MODEL, contents=prompt).text

    return summary


def handle_text_event(sender_id: str, text: str) -> None:
    """Dispatch on the LLM‑determined intent."""
    intent, args = call_intent_llm(sender_id, text)
    expense_date = args.get("date") or datetime.now().strftime("%Y-%m-%d")

    if intent == "save_expense":
        try:
            save_expense(
                id=str(uuid.uuid4()),
                user_id=sender_id,
                category=args.get("category", ""),
                price=args.get("price", 0),
                description=args.get("description", ""),
                date=args.get("date", expense_date),
            )
            reply = (
                f"*{args.get('category','').upper()}* saved!\n\n"
                f"• Amount: {args.get('price',0)}\n"
                f"• Description: {args.get('description','')}\n"
                f"• Date: {args.get('date', expense_date)}"
            )
            send_fb_message(sender_id, {"text": reply})

        except Exception as e:
            logger.error(f"Error in save_expense branch: {e}")
            send_fb_message(sender_id, {"text": "Sorry, I couldn't save your expense."})

    elif intent == "get_expenses_by_category":
        try:
            category = args.get("category", "")
            query_lang = args.get("language", "bengali")
            records = get_expenses_by_category(user_id=sender_id, category=category)
            if not records:
                send_fb_message(
                    sender_id, {"text": "No expenses found in that category."}
                )
                return
            summary = query_summary(records, query_lang)
            send_fb_message(sender_id, {"text": summary})

        except Exception as e:
            logger.error(f"Error fetching by category: {e}")
            send_fb_message(sender_id, {"text": "Couldn't retrieve your expenses."})

    elif intent == "get_expenses_by_date":
        try:
            start_date = args.get("start_date", "")
            end_date = args.get("end_date", "")
            query_lang = args.get("language", "bengali")
            records = get_expenses_by_date(
                user_id=sender_id,
                start_date=start_date,
                end_date=end_date,
            )
            if not records:
                send_fb_message(sender_id, {"text": "No expenses found on that date."})
                return
            summary = query_summary(records, query_lang)
            send_fb_message(sender_id, {"text": summary})

        except Exception as e:
            logger.error(f"Error fetching by date: {e}")
            send_fb_message(sender_id, {"text": "Couldn't retrieve your expenses."})

    elif intent == "get_all_expenses":
        try:
            records = get_all_expenses(user_id=sender_id)
            if not records:
                send_fb_message(sender_id, {"text": "No expenses found."})
                return
            summary = query_summary(records, "bengali")
            send_fb_message(sender_id, {"text": summary})

        except Exception as e:
            logger.error(f"Error fetching all expenses: {e}")
            send_fb_message(sender_id, {"text": "Couldn't retrieve your expenses."})

    elif intent == "greetings":
        send_fb_message(sender_id, {"text": "Hello! How can I help you today?"})

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

    message = event.get("message", {})

    # Handle attachments
    attachments = message.get("attachments", [])
    if attachments:
        kind = attachments[0].get("type")
        if kind == "audio":
            # Transcribe and treat as text
            text = transcribe_audio_attachment(sender_id, attachments[0])
            handle_text_event(sender_id, text)
        else:
            # Image expense
            handle_attachment_event(sender_id, attachments)
    elif "text" in message:
        handle_text_event(sender_id, message["text"])

    return {"status": "processed"}
