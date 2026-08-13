"""
Interactive terminal chat, to test the bot's tool use and grounding
before building the Streamlit UI around it.

Run from the project root:
    python -m scripts.chat_cli

Type 'exit' to quit.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.chatbot import start_chat, send_with_retry, friendly_error, MAX_TURNS_BEFORE_RESET


def main():
    print("WeGro IR Assistant (test CLI). Type 'exit' to quit.\n")
    chat = start_chat()
    turn_count = 0

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("exit", "quit"):
            break
        if not user_input:
            continue

        if turn_count >= MAX_TURNS_BEFORE_RESET:
            chat = start_chat()
            turn_count = 0
            print("(Starting a fresh conversation to keep things efficient - "
                  "earlier context in this session is no longer available.)\n")

        try:
            response = send_with_retry(chat, user_input)
            print(f"\nBot: {response.text}\n")
            turn_count += 1
        except Exception as e:
            print(f"\nBot: {friendly_error(e)}\n")


if __name__ == "__main__":
    main()