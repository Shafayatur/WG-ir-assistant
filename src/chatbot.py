"""
Wraps the Gemini API with our tool layer (src/llm_tools.py) and a system
instruction that enforces grounding: the model must only state numbers
that came back from a tool call, and must say so explicitly when data
isn't available rather than guessing.

Uses the google-genai SDK's automatic function calling: we pass our
plain Python functions as tools, and the SDK handles calling them and
feeding results back to the model before it writes a final answer.
"""
from google import genai
from google.genai import types
from google.genai import errors as genai_errors
import time

from src.config import Config
from src.llm_tools import ALL_TOOLS

MODEL_NAME = "gemini-flash-latest"

# After this many user turns in one session, start a fresh chat instead of
# letting history grow unbounded. Every message resends the full history
# to Gemini, including any large tool results (e.g. filter_orders rows) -
# without a cap, a long session gets progressively more expensive per
# question even if the questions themselves are simple.
MAX_TURNS_BEFORE_RESET = 8
RATE_LIMIT_WAIT_SECONDS = 65

SYSTEM_INSTRUCTION = """
You are an internal data assistant for the WeGro IR (Investor Relations) team.

You have tools that query two live data sources:
- Orders: individual investment orders (status/stage, amounts, projects, dates)
- CF Tracker: daily rollup metrics (registrations, bookings, investments, investor counts)

Hard rules, no exceptions:
1. NEVER state a number, count, date, or fact about the data unless it came
   from a tool call you just made in this conversation. Do not use general
   knowledge or guess at company-specific figures.
2. If a tool returns an empty result or no matching data, say plainly that
   you could not find that information - do not estimate or fill the gap.
3. Distinguish clearly between: (a) a number directly from the data, (b) a
   number you calculated from tool results (e.g. a percentage or average -
   say you calculated it), and (c) something you cannot determine from
   available data.
4. When a user's wording is ambiguous (e.g. a project name that doesn't
   exactly match), use list_projects to find the closest real match before
   answering, and tell the user which project you matched it to.
5. "Active" investments means stage='active' (currently invested or
   disbursing). If the user says "active" or "ongoing" or "current
   investors", use stage='active' unless they clearly mean something else.
6. For "latest" or "today" on CF Tracker data, always call get_latest_cf_day
   first - do not assume today's calendar date, since the underlying sheet
   has empty placeholder rows for future dates that haven't happened yet.
7. Investor name, phone, and email ARE available via tools now (bank
   account numbers and routing numbers are NOT - never stored). You may
   state a name when it's the direct answer to what was asked (e.g. "who
   is our most recent investor"). Don't proactively volunteer phone
   numbers or emails unless the user specifically asks for contact
   details - IR staff should use those deliberately for outreach, not
   have them appear as a side effect of unrelated questions.
8. Investor Tier (Low/Mid/High/VIP), favorite product category, preferred
   tenure, and activity status (Active/Cooling/Inactive - Reach Out) are
   precomputed business classifications - use list_investor_segments or
   get_investor_segment for these rather than trying to calculate them
   yourself from raw orders. Full definitions are in those tools'
   descriptions.
9. Keep answers concise and appropriate for a non-technical audience. State
   the specific numbers, not just a vague summary.
""".strip()


_client: genai.Client | None = None


def get_client() -> genai.Client:
    """Reuses a single Client instance for the whole process. Creating a
    new Client per call and letting it go out of scope can cause its
    underlying httpx connection to be garbage-collected and closed before
    a request completes - keeping one persistent instance avoids that."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=Config.GEMINI_API_KEY)
    return _client


def start_chat():
    """Returns a new chat session with tools and system instructions wired
    up. Call .send_message(text) on the result for each user turn."""
    client = get_client()
    return client.chats.create(
        model=MODEL_NAME,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=ALL_TOOLS,
        ),
    )


def friendly_error(e: Exception) -> str:
    """Turns raw API/network errors into a message a non-technical user
    could actually read - stack traces should never be user-facing.
    Handles both ClientError (4xx - problem with the request/quota) and
    ServerError (5xx - problem on Google's end, usually transient)."""
    code = getattr(e, "code", None)
    if isinstance(e, (genai_errors.ClientError, genai_errors.ServerError)):
        if code == 429:
            return ("The assistant is getting a lot of requests right now "
                    "(rate limit reached). Please wait about a minute and "
                    "try again.")
        if code and 500 <= code < 600:
            return ("Google's Gemini service is temporarily overloaded on "
                    "their end (not a problem with our data or your "
                    "question). Please try again in a few seconds.")
        return f"The assistant hit an error talking to Gemini ({code}). Please try again."
    return f"Something went wrong answering that: {e}"


def send_with_retry(chat, user_input: str):
    """Tries once, and retries automatically for known-transient errors:
    - 429 (rate limit): wait out the window, then retry once.
    - 5xx (Google's servers temporarily overloaded): short backoff retry,
      up to 2 extra attempts, since these are usually momentary."""
    last_exception = None
    for attempt in range(3):
        try:
            return chat.send_message(user_input)
        except (genai_errors.ClientError, genai_errors.ServerError) as e:
            last_exception = e
            code = getattr(e, "code", None)
            if code == 429:
                time.sleep(RATE_LIMIT_WAIT_SECONDS)
            elif code and 500 <= code < 600 and attempt < 2:
                time.sleep(3 * (attempt + 1))  # 3s, then 6s
            else:
                raise
    raise last_exception