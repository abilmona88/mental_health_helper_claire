from typing import List, Optional

import streamlit as st
from sqlalchemy.orm import Session

from auth import get_user_by_email, verify_password, create_user
from claire_ai import generate_claire_reply
from db import SessionLocal, init_db, User, Conversation, Message

st.set_page_config(
    page_title="Claire – Relaxation Companion",
    page_icon="💆‍♀️",
    layout="wide",
)

# ---------- DISCLAIMER TEXT (unchanged, keep whatever you already like) ----------

SIGNUP_DISCLAIMER = """
**IMPORTANT LEGAL NOTICE – TERMS OF USE, RISK ACKNOWLEDGEMENT, AND LIMITATION OF LIABILITY**

This app is for general informational and emotional support only. It does NOT provide
medical, mental-health, psychological, or emergency services. Do not use it for crises
or emergencies. If you are in crisis, contact your local emergency number or a crisis
hotline immediately.

By logging in and using this app, you accept that you are solely responsible for how you
use any information or responses provided, and you agree that the creators/operators of
this app are not liable for any loss, injury, or damage arising from your use or reliance
on the app, to the maximum extent permitted by applicable law.
"""

CHAT_REMINDER = (
    "⚠️ **Reminder:** Claire is an AI program for general information and emotional support only. "
    "She is **not** a doctor, therapist, or crisis service. Nothing in this chat is medical or "
    "mental-health advice, diagnosis, or treatment. Do **not** use this app for emergencies. If you "
    "are in crisis or think you might hurt yourself or someone else, contact your local emergency "
    "number or a crisis hotline immediately."
)


# ---------- DB helpers ----------

def get_db() -> Session:
    return SessionLocal()


def get_current_user(db: Session) -> Optional[User]:
    user_id = st.session_state.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


def get_or_create_active_conversation(db: Session, user: User) -> Conversation:
    conv_id = st.session_state.get("conversation_id")
    conv: Optional[Conversation] = None

    if conv_id:
        conv = (
            db.query(Conversation)
            .filter(Conversation.id == conv_id, Conversation.user_id == user.id)
            .first()
        )

    if conv is None:
        conv = (
            db.query(Conversation)
            .filter(Conversation.user_id == user.id, Conversation.is_active == True)
            .order_by(Conversation.created_at.desc())
            .first()
        )

    if conv is None:
        conv = Conversation(user_id=user.id, title="Claire session", is_active=True)
        db.add(conv)
        db.commit()
        db.refresh(conv)

    st.session_state["conversation_id"] = conv.id
    return conv


def start_new_conversation(db: Session, user: User) -> Conversation:
    db.query(Conversation).filter(Conversation.user_id == user.id).update(
        {Conversation.is_active: False}
    )
    db.commit()

    conv = Conversation(user_id=user.id, title="Claire session", is_active=True)
    db.add(conv)
    db.commit()
    db.refresh(conv)

    st.session_state["conversation_id"] = conv.id
    return conv


def get_conversation_history(
    db: Session, conversation: Conversation, limit: int = 50
) -> List[Message]:
    q = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
    )
    msgs = q.all()
    if len(msgs) > limit:
        msgs = msgs[-limit:]
    return msgs


# ---------- SEED THE TWO USERS ----------

def seed_two_users() -> None:
    """
    Ensure exactly two users exist in the DB for login:
      - username: rashad, password: admin1
      - username: alex,   password: admin2

    We use the User.email field as the 'username' for simplicity.
    """
    db = get_db()
    try:
        # Rashad
        rashad = get_user_by_email(db, "rashad")
        if rashad is None:
            rashad = create_user(
                db,
                email="rashad",
                full_name="Rashad",
                password="admin1",
                profile_notes="",
            )

        # Alex
        alex = get_user_by_email(db, "alex")
        if alex is None:
            alex = create_user(
                db,
                email="alex",
                full_name="Alex",
                password="admin2",
                profile_notes="",
            )
    finally:
        db.close()


# ---------- quick actions ----------

def handle_quick_action(
    db: Session, user: User, conversation: Conversation, seed_text: str
) -> None:
    user_msg = Message(
        conversation_id=conversation.id,
        sender_role="user",
        content=seed_text,
    )
    db.add(user_msg)
    db.commit()

    history = get_conversation_history(db, conversation)

    try:
        reply = generate_claire_reply(user, history)
    except Exception as e:
        reply = (
            "I hit an error while trying to respond. "
            "Check your OpenAI configuration.\n\n"
            f"Error: {e}"
        )

    assistant_msg = Message(
        conversation_id=conversation.id,
        sender_role="assistant",
        content=reply,
    )
    db.add(assistant_msg)
    db.commit()

    st.rerun()


# ---------- auth UI (LOGIN ONLY, NO SIGNUP) ----------

def show_auth_page() -> None:
    st.title("💆‍♀️ Claire – Relaxation Companion")

    st.markdown("### Legal Notice")
    with st.expander("Read this before logging in", expanded=False):
        st.markdown(SIGNUP_DISCLAIMER)

    st.write(
        "This app is restricted to authorized users only."
    )

    with st.form("login_form"):
        username = st.text_input("Username (rashad or alex)")
        password = st.text_input("Password", type="password")
        agree = st.checkbox(
            "I have read and agree to the legal notice above.",
            value=False,
        )
        submitted = st.form_submit_button("Log in")

    if submitted:
        if not username or not password:
            st.error("Username and password are required.")
            return
        if not agree:
            st.error("You must agree to the legal notice to log in.")
            return

        db = get_db()
        try:
            # We use email column as 'username'
            user = get_user_by_email(db, username)
            if not user or not verify_password(password, user.password_hash):
                st.error("Invalid username or password.")
            else:
                st.session_state["user_id"] = user.id
                st.session_state.pop("conversation_id", None)
                st.success("Logged in.")
                st.rerun()
        finally:
            db.close()


# ---------- main app (logged in) ----------

def show_main_app(user: User) -> None:
    db = get_db()
    try:
        conv = get_or_create_active_conversation(db, user)
        history = get_conversation_history(db, conv)

        # sidebar
        with st.sidebar:
            st.subheader("Account")
            st.write(f"**User:** {user.full_name} (username: {user.email})")

            # Profile notes still optional if you want internal personalized context
            profile_notes = st.text_area(
                "Profile notes (Claire uses this as context)",
                value=user.profile_notes or "",
                height=120,
            )
            if st.button("Save profile notes"):
                user.profile_notes = profile_notes.strip() or None
                db.add(user)
                db.commit()
                st.success("Profile updated.")

            if st.button("Start new session"):
                start_new_conversation(db, user)
                st.rerun()

            st.markdown("---")
            if st.button("Log out"):
                st.session_state.pop("user_id", None)
                st.session_state.pop("conversation_id", None)
                st.rerun()

        # main area
        st.title("💆‍♀️ Claire – Relaxation Companion")
        st.caption(
            "Claire is an AI coach inspired by the work of Dr. Claire Weekes. "
            "She is not a doctor or therapist and cannot provide crisis support."
        )

        # persistent chat disclaimer
        st.info(CHAT_REMINDER)

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("3-minute breathing", use_container_width=True):
                handle_quick_action(
                    db,
                    user,
                    conv,
                    "Guide me through a simple 3-minute breathing exercise in your usual style.",
                )
        with c2:
            if st.button("Racing thoughts", use_container_width=True):
                handle_quick_action(
                    db,
                    user,
                    conv,
                    "My thoughts are racing. Walk me through facing, accepting, floating, and letting time pass.",
                )
        with c3:
            if st.button("Body tension scan", use_container_width=True):
                handle_quick_action(
                    db,
                    user,
                    conv,
                    "Guide me through a slow body scan to release tension in your usual style.",
                )

        # history
        history = get_conversation_history(db, conv)
        for msg in history:
            role = "user" if msg.sender_role == "user" else "assistant"
            with st.chat_message(role):
                st.markdown(msg.content)

        # chat input
        user_input = st.chat_input("Tell Claire what's going on...")
        if user_input:
            user_msg = Message(
                conversation_id=conv.id,
                sender_role="user",
                content=user_input,
            )
            db.add(user_msg)
            db.commit()

            history = get_conversation_history(db, conv)

            try:
                reply = generate_claire_reply(user, history)
            except Exception as e:
                reply = (
                    "I hit an error while trying to respond. "
                    "Check your OpenAI configuration.\n\n"
                    f"Error: {e}"
                )

            assistant_msg = Message(
                conversation_id=conv.id,
                sender_role="assistant",
                content=reply,
            )
            db.add(assistant_msg)
            db.commit()

            with st.chat_message("assistant"):
                st.markdown(reply)

    finally:
        db.close()


# ---------- entrypoint ----------

def main() -> None:
    init_db()
    seed_two_users()  # <-- make sure Rashad and Alex exist

    db = get_db()
    try:
        user = get_current_user(db)
    finally:
        db.close()

    if user is None:
        show_auth_page()
    else:
        show_main_app(user)


if __name__ == "__main__":
    main()
