"""
Interactive terminal chat, to test the bot's tool use and grounding
before building the Streamlit UI around it.

Run from the project root:
    python -m scripts.chat_cli

Type 'exit' to quit.
"""
import sys, os, time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from google.genai import errors as genai_errors
from src.chatbot import start_chat

RATE_LIMIT_WAIT_SECONDS = 65  # free tier resets ~60s; pad slightly


def _friendly_error(e: Exception) -> str:
    if isinstance(e, genai_errors.ClientError) and getattr(e, "code", None) == 429:
        return ("The assistant is getting a lot of requests right now "
                "(rate limit reached). Please wait about a minute and "
                "try again.")
    if isinstance(e, genai_errors.ClientError):
        return f"The assistant hit an error talking to Gemini ({e.code}). Please try again."
    return f"Something went wrong answering that: {e}"


def _send_with_retry(chat, user_input: str):
    """Tries once, and if it's specifically a rate limit (429), waits and
    retries automatically one time before giving up - each question can
    trigger multiple Gemini calls internally (tool selection + final
    answer), so hitting the free tier's per-minute cap mid-question is
    common, not exceptional."""
    try:
        return chat.send_message(user_input)
    except genai_errors.ClientError as e:
        if getattr(e, "code", None) == 429:
            print(f"\n(Rate limit hit - waiting {RATE_LIMIT_WAIT_SECONDS}s and retrying automatically...)")
            time.sleep(RATE_LIMIT_WAIT_SECONDS)
            return chat.send_message(user_input)  # let a second failure raise normally
        raise


def main():
    print("WeGro IR Assistant (test CLI). Type 'exit' to quit.\n")
    chat = start_chat()

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("exit", "quit"):
            break
        if not user_input:
            continue

        try:
            response = _send_with_retry(chat, user_input)
            print(f"\nBot: {response.text}\n")
        except Exception as e:
            print(f"\nBot: {_friendly_error(e)}\n")


if __name__ == "__main__":
    main()