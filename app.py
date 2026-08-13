"""
WeGro IR Assistant - Streamlit app.

Two tabs, one login gate:
- Dashboard: fixed views calling src/queries.py directly - zero LLM cost,
  works even if Gemini is down or the API key is missing/invalid.
- Ask a Question: the Gemini chatbot from src/chatbot.py, wired to the
  exact same query layer via src/llm_tools.py.

Run: streamlit run app.py
"""
import streamlit as st
import pandas as pd

from src.config import Config
from src import queries
from src.chatbot import start_chat, send_with_retry, friendly_error, MAX_TURNS_BEFORE_RESET

st.set_page_config(page_title="WeGro IR Assistant", layout="wide")


# ---------------------------------------------------------------------------
# Passkey gate
# ---------------------------------------------------------------------------

def check_passkey() -> bool:
    if st.session_state.get("authenticated"):
        return True

    st.title("WeGro IR Assistant")
    st.caption("Internal tool - Investor Relations team only")
    passkey = st.text_input("Enter passkey", type="password")
    if st.button("Enter"):
        if passkey == Config.APP_PASSKEY:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect passkey.")
    return False


if not check_passkey():
    st.stop()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.subheader("WeGro IR Assistant")
    try:
        latest_day = queries.get_latest_cf_day()
        st.caption(f"Latest CF Tracker data: {latest_day}")
    except Exception:
        st.caption("Could not load latest data date.")

    if st.button("New conversation"):
        st.session_state.pop("chat_session", None)
        st.session_state.pop("messages", None)
        st.session_state.pop("turn_count", None)
        st.rerun()

    if st.button("Log out"):
        st.session_state.clear()
        st.rerun()


tab_dashboard, tab_chat = st.tabs(["📊 Dashboard", "💬 Ask a Question"])


# ---------------------------------------------------------------------------
# Dashboard tab - no LLM involved, pure query layer
# ---------------------------------------------------------------------------

with tab_dashboard:
    st.subheader("Overview")

    try:
        cf_summary = queries.get_cf_summary()
        order_summary = queries.get_order_summary()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Investment Value (CF Tracker)", f"{cf_summary['total_investment_value']:,.0f}")
        c2.metric("Total Orders", f"{order_summary['order_count']:,.0f}")
        c3.metric("Unique Investors", f"{order_summary['unique_investor_count']:,.0f}")
        c4.metric("Total Returned", f"{order_summary['total_returned']:,.0f}")
    except Exception as e:
        st.error(f"Could not load summary metrics: {e}")

    st.divider()

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("**Monthly investment trend (CF Tracker)**")
        try:
            trend = queries.compare_cf_periods(period="month", n_periods=6)
            trend_display = trend.copy()
            trend_display["period_start"] = pd.to_datetime(trend_display["period_start"]).dt.strftime("%b %Y")
            st.bar_chart(trend_display.set_index("period_start")["investment_value"])
        except Exception as e:
            st.error(f"Could not load trend: {e}")

    with col_right:
        st.markdown("**Orders by stage**")
        try:
            rows = []
            for s in ["pending", "active", "closed", "canceled"]:
                summary = queries.get_order_summary(stage=s)
                rows.append({"stage": s, "order_count": summary["order_count"]})
            stage_df = pd.DataFrame(rows).set_index("stage")
            st.bar_chart(stage_df["order_count"])
        except Exception as e:
            st.error(f"Could not load stage breakdown: {e}")

    st.divider()
    st.markdown("**Top investors**")
    try:
        n = st.slider("Show top N", min_value=5, max_value=30, value=10, key="top_n")
        top_df = queries.top_investors(n=n)
        st.dataframe(top_df, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Could not load top investors: {e}")

    st.divider()
    st.markdown("**Filter orders**")
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        stage_filter = st.selectbox("Stage", ["(any)", "pending", "active", "closed", "canceled"])
    with fc2:
        project_filter = st.text_input("Project name contains")
    with fc3:
        limit_filter = st.number_input("Max rows", min_value=5, max_value=200, value=20)

    try:
        filtered = queries.filter_orders(
            stage=None if stage_filter == "(any)" else stage_filter,
            project_name=project_filter or None,
            limit=int(limit_filter),
        )
        st.dataframe(filtered, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Could not load filtered orders: {e}")


# ---------------------------------------------------------------------------
# Chat tab
# ---------------------------------------------------------------------------

with tab_chat:
    if "messages" not in st.session_state:
        st.session_state.messages = []
        st.session_state.turn_count = 0
        st.session_state.chat_unavailable = None
        try:
            st.session_state.chat_session = start_chat()
        except Exception as e:
            st.session_state.chat_unavailable = str(e)

    if st.session_state.get("chat_unavailable"):
        st.warning(
            "The chat assistant is currently unavailable "
            f"({st.session_state.chat_unavailable}). "
            "The Dashboard tab is unaffected and still has full data access."
        )
    else:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        user_input = st.chat_input("Ask about investors, orders, or CF tracker data...")
        if user_input:
            st.session_state.messages.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.markdown(user_input)

            if st.session_state.turn_count >= MAX_TURNS_BEFORE_RESET:
                st.session_state.chat_session = start_chat()
                st.session_state.turn_count = 0
                st.info("Starting a fresh conversation to keep things efficient - "
                         "earlier context in this session is no longer available.")

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    try:
                        response = send_with_retry(st.session_state.chat_session, user_input)
                        answer = response.text
                    except Exception as e:
                        answer = friendly_error(e)
                st.markdown(answer)

            st.session_state.messages.append({"role": "assistant", "content": answer})
            st.session_state.turn_count += 1