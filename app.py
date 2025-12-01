import os
from typing import List, Optional

import streamlit as st
from sqlalchemy.orm import Session

from auth import get_user_by_email, verify_password, create_user, hash_password
from claire_ai import generate_claire_reply
from db import SessionLocal, init_db, User, Conversation, Message

st.set_page_config(
    page_title="Claire – Relaxation Companion",
    page_icon="💆‍♀️",
    layout="wide",
)

# ---------- DISCLAIMER TEXT (short version – keep or swap with your heavy one) ----------

SIGNUP_DISCLAIMER = """
**IMPORTANT LEGAL NOTICE – READ BEFORE LOGGING IN**

This app and the AI assistant “Claire” provide general informational and emotional support only.
They do **not** provide medical, mental-health, psychological, or emergency services and are
not a substitute for professional care.

Do **not** use this app for crises or emergencies. If you are in crisis, think you might hurt
yourself or someone else, or believe someone is in danger, contact your local emergency number
(e.g. 911) or a crisis hotline immediately.

By logging in and using this app, you accept that you are solely responsible for how you use any
information or responses provided, and you agree that the creators/operators of this app are not
liable for any loss, injury, or damage arising from your use or reliance on the app, to the
maximum extent permitted by applicable law.
"""

CHAT_REMINDER = (
    "⚠️ **Reminder:** Claire is an AI program for general information and emotional support only. "
    "She is **not** a doctor, therapist, or crisis service, and nothing in this chat is medical or "
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


# ---------- helpers for secrets / env ----------

def _get_secret(key: str) -> Optional[str]:
    """
    Try st.secrets first, then environment variables.
    Never crashes if secrets are missing.
    """
    value = None
    try:
        if key in st.secrets:
            value = st.secrets[key]
    except Exception:
        # st.secrets may not exist in some environments
        value = None

    if not value:
        value = os.environ.get(key)

    if value is not None:
        value = str(value).strip()

    return value or None


# ---------- SEED EXACTLY TWO USERS FROM SECRETS (NO HARD-CODED CREDS) ----------

def seed_two_users_from_secrets() -> None:
    """
    Ensure at most two users exist, defined by secrets/env:

      CLAIRE_USER1_USERNAME
      CLAIRE_USER1_PASSWORD
      CLAIRE_USER1_FULLNAME  (optional)

      CLAIRE_USER2_USERNAME
      CLAIRE_USER2_PASSWORD
      CLAIRE_USER2_FULLNAME  (optional)

    Usernames are stored in User.email; passwords are hashed by hash_password().
    If a user already exists, their full_name and password_hash are updated
    to match the current secrets.
    """
    db = get_db()
    try:
        for idx in (1, 2):
            u_key = f"CLAIRE_USER{idx}_USERNAME"
            p_key = f"CLAIRE_USER{idx}_PASSWORD"
            n_key = f"CLAIRE_USER{idx}_FULLNAME"

            username = _get_secret(u_key)
            password = _get_secret(p_key)
            fullname = _get_secret(n_key) or (username or f"User{idx}")

            # If username or password isn't set, skip this slot
            if not username or not password:
                continue

            existing = get_user_by_email(db, username)
            if existing is None:
                # create new user
                create_user(
                    db,
                    email=username,
                    full_name=fullname,
                    password=password,
                    profile_notes="",
                )
            else:
                updated = False
                if existing.full_name != fullname:
                    existing.full_name = fullname
                    updated = True

                # ALWAYS sync the password hash with current secrets
                new_hash = hash_password(password)
                if existing.password_hash != new_hash:
                    existing.password_hash = new_hash
                    updated = True

                if updated:
                    db.add(existing)
                    db.commit()
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

    st.write("This app is restricted to authorized users only.")

    with st.form("login_form"):
        username = st.text_input("Username")
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
            # We use the email column as 'username'
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
    seed_two_users_from_secrets()  # <-- creates/updates your two users from secrets/env

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
