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
    get_all_expenses,
    get_expenses_by_category,
    get_expenses_by_date,
    get_breakdown,
    func_config,
)

router = APIRouter()

# Environment
PAGE_ID = os.getenv("PAGE_ID")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
FB_MSG_API_BASE = os.getenv("FB_MSG_API_BASE")
FB_MESSAGE_URL = f"{FB_MSG_API_BASE}{PAGE_ACCESS_TOKEN}"

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
    ).text

    send_fb_message(sender_id, {"text": llm_resp})
    return llm_resp


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


def call_intent_llm(sender_id: str, user_query: str) -> list[tuple[str, dict]]:
    """
    Ask the LLM to choose one or more of our functions and return
    a list of (function_name, args) tuples.
    """
    query_lang = agent.models.generate_content(
        model=TEXT_MODEL,
        contents=f"just reply with the language name of the query language. query: {user_query}\n\n eg; ['english', 'bengali']",
    ).text

    logger.info(f"Query language: {query_lang}")

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
        f"\nuser_id: '{sender_id}', user_query: '{user_query}', must reply in language: '{query_lang}'. Response:"
    )

    resp = agent.models.generate_content(
        model=TEXT_MODEL, contents=user_prompt, config=func_config
    )

    logger.info(f"LLM response: {resp}")

    calls: list[tuple[str, dict]] = []
    for fc in resp.function_calls:
        raw = fc.args
        try:
            args = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            logger.error(f"Could not parse args for {fc.name}: {raw}")
            args = {}
        logger.info(f"Function call: {fc.name}, args: {args}")
        calls.append((fc.name, args))

    return calls


def query_summary(records, query_lang):
    logger.info(f"whqudhkjashjkdcdqiwd: {query_lang}")
    prompt = (
        f"NOTE: language list: ['english','bengali'].\n"
        f"User query language: {query_lang}.\n"
        "Given these expenses, format a concise (<200 chars) human response "
        "using '৳' for currency.\n"
        f"{records}\nResponse:"
    )

    summary = agent.models.generate_content(model=TEXT_MODEL, contents=prompt).text
    return summary


def merge_responses_with_llm(replies: list[str]) -> str:
    """
    Ask the LLM to combine multiple bullet points or short sentences
    into one cohesive, friendly reply.
    """
    merge_prompt = (
        "You are an assistant that merges multiple bullet points or short sentences "
        "into one cohesive, friendly reply. Combine the following items:\n\n"
        + "\n\n".join(f"- {r}" for r in replies)
        + "\n\nFinal Response:"
    )
    llm_resp = agent.models.generate_content(model=TEXT_MODEL, contents=[merge_prompt])
    return llm_resp.text.strip()


def handle_text_event(sender_id: str, text: str) -> None:
    """
    Dispatch on all LLM‑determined function calls, accumulate each result,
    then send one merged, natural response.
    """
    calls = call_intent_llm(sender_id, text)
    replies: list[str] = []

    for intent, args in calls:
        args.setdefault("date", datetime.now().strftime("%Y-%m-%d"))

        if intent == "save_expense":
            try:
                save_expense(
                    id=str(uuid.uuid4()),
                    user_id=sender_id,
                    category=args.get("category", ""),
                    price=args.get("price", 0),
                    description=args.get("description", ""),
                    date=args["date"],
                )
                replies.append(
                    f"*{args.get('category','').upper()}* saved! "
                    f"(৳{args.get('price',0)}, {args['date']})"
                )
            except Exception as e:
                logger.error(f"Error in save_expense: {e}")
                replies.append("⚠️ Sorry, I couldn't save one of your expenses.")

        elif intent == "get_expenses_by_category":
            try:
                category = args.get("category", "")
                query_lang = args.get("language", "")
                records = get_expenses_by_category(user_id=sender_id, category=category)
                if not records:
                    replies.append(f"No expenses found in category '{category}'.")
                else:
                    replies.append(query_summary(records, query_lang))
            except Exception as e:
                logger.error(f"Error fetching by category: {e}")
                replies.append("⚠️ Couldn't retrieve expenses by category.")

        elif intent == "get_expenses_by_date":
            try:
                start = args.get("start_date", "")
                end = args.get("end_date", "")
                query_lang = args.get("language", "")
                records = get_expenses_by_date(
                    user_id=sender_id, start_date=start, end_date=end
                )
                if not records:
                    replies.append(f"No expenses found between {start} and {end}.")
                else:
                    replies.append(query_summary(records, query_lang))
            except Exception as e:
                logger.error(f"Error fetching by date: {e}")
                replies.append("⚠️ Couldn't retrieve expenses by date.")

        elif intent == "get_all_expenses":
            try:
                query_lang = args.get("language", "")
                records = get_all_expenses(user_id=sender_id)
                if not records:
                    replies.append("No expenses found.")
                else:
                    replies.append(query_summary(records, query_lang))
            except Exception as e:
                logger.error(f"Error fetching all expenses: {e}")
                replies.append("⚠️ Couldn't retrieve all expenses.")

        elif intent == "get_breakdown":
            try:
                query_lang = args.get("language", "")
                records = get_breakdown(user_id=sender_id)
                if not records:
                    replies.append("No expenses to break down.")
                else:
                    replies.append(query_summary(records, query_lang))
            except Exception as e:
                logger.error(f"Error fetching breakdown: {e}")
                replies.append("⚠️ Couldn't retrieve expense breakdown.")

        elif intent == "greetings":
            replies.append("Hello! How can I help you today?")

        else:
            replies.append("Sorry, I didn't understand that request.")

    if not replies:
        send_fb_message(sender_id, {"text": "Sorry, I couldn't process your request."})
        return

    if len(replies) > 1:
        merged = merge_responses_with_llm(replies)
        send_fb_message(sender_id, {"text": merged})
    else:
        send_fb_message(sender_id, {"text": replies[0]})


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
            text = transcribe_audio_attachment(sender_id, attachments[0])
            handle_text_event(sender_id, text)
        else:
            handle_attachment_event(sender_id, attachments)

    elif "text" in message:
        handle_text_event(sender_id, message["text"])

    return {"status": "processed"}
