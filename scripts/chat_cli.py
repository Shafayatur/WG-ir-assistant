"""
Interactive terminal chat, to test the bot's tool use and grounding
before building the Streamlit UI around it.

Run from the project root:
    python -m scripts.chat_cli

Type 'exit' to quit.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.chatbot import start_chat


def main():
    print("WeGro IR Assistant (test CLI). Type 'exit' to quit.\n")
    chat = start_chat()

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("exit", "quit"):
            break
        if not user_input:
            continue

        response = chat.send_message(user_input)
        print(f"\nBot: {response.text}\n")


if __name__ == "__main__":
    main()