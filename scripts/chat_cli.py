"""
Interactive terminal chat, to test the bot's tool use and grounding
before building the Streamlit UI around it.

Run from the project root:
    python -m scripts.chat_cli

Type 'exit' to quit.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from google.genai import errors as genai_errors
from src.chatbot import start_chat


def _friendly_error(e: Exception) -> str:
    """Turns raw API/network errors into a message a non-technical user
    could actually read - this same handling belongs in the Streamlit app
    too, since a stack trace should never be user-facing there."""
    if isinstance(e, genai_errors.ClientError) and getattr(e, "code", None) == 429:
        return ("The assistant is getting a lot of requests right now "
                "(rate limit reached). Please wait about a minute and "
                "try again.")
    if isinstance(e, genai_errors.ClientError):
        return f"The assistant hit an error talking to Gemini ({e.code}). Please try again."
    return f"Something went wrong answering that: {e}"


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
            response = chat.send_message(user_input)
            print(f"\nBot: {response.text}\n")
        except Exception as e:
            print(f"\nBot: {_friendly_error(e)}\n")


if __name__ == "__main__":
    main()