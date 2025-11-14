from typing import List, Optional

import streamlit as st
from sqlalchemy.orm import Session

from auth import get_user_by_email, verify_password, create_user
from claire_ai import generate_claire_reply
from db import SessionLocal, init_db, User, Conversation, Message


# ---------- STREAMLIT CONFIG ----------
st.set_page_config(
    page_title="Claire – Relaxation Companion",
    page_icon="💆‍♀️",
    layout="wide",
)


# ---------- DB HELPERS ----------

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
    # mark old ones inactive
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
    messages = q.all()
    if len(messages) > limit:
        messages = messages[-limit:]
    return messages


# ---------- QUICK ACTION HANDLER ----------

def handle_quick_action(
    db: Session, user: User, conversation: Conversation, seed_text: str
) -> None:
    """
    Create a seed user message, call Claire, save reply, then rerun the app.
    """
    # user message
    user_msg = Message(
        conversation_id=conversation.id,
        sender_role="user",
        content=seed_text,
    )
    db.add(user_msg)
    db.commit()

    # full history (including this seed message)
    history = get_conversation_history(db, conversation)

    # Claire reply
    try:
        reply_text = generate_claire_reply(user, history)
    except Exception as e:
        reply_text = (
            "I hit an issue while trying to respond. "
            "Check the server logs or your OpenAI configuration and try again.\n\n"
            f"Error: {e}"
        )

    assistant_msg = Message(
        conversation_id=conversation.id,
        sender_role="assistant",
        content=reply_text,
    )
    db.add(assistant_msg)
    db.commit()

    # let Streamlit rerun and redraw with updated history
    st.rerun()


# ---------- AUTH UI ----------

def show_auth_page() -> None:
    st.title("💆‍♀️ Claire – Relaxation Companion")
    st.write(
        "Log in or create an account so Claire can remember your sessions and your preferences."
    )

    tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

    # ----- LOGIN -----
    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in")

        if submitted:
            if not email or not password:
                st.error("Email and password are required.")
            else:
                db = get_db()
                try:
                    user = get_user_by_email(db, email)
                    if not user or not verify_password(password, user.password_hash):
                        st.error("Invalid email or password.")
                    else:
                        st.session_state["user_id"] = user.id
                        st.session_state.pop("conversation_id", None)
                        st.success("Logged in successfully.")
                        st.rerun()
                finally:
                    db.close()

    # ----- SIGNUP -----
    with tab_signup:
        with st.form("signup_form"):
            full_name = st.text_input("Full name")
            email = st.text_input("Email", key="signup_email")
            password = st.text_input("Password", type="password", key="signup_pw")
            password2 = st.text_input(
                "Confirm password", type="password", key="signup_pw2"
            )
            profile_notes = st.text_area(
                "Anything Claire should know about you?",
                placeholder=(
                    "What tends to make you anxious? What usually helps you relax? (Optional)"
                ),
            )
            submitted = st.form_submit_button("Create account")

        if submitted:
            if not full_name or not email or not password or not password2:
                st.error("All fields except profile notes are required.")
            elif len(password) < 8:
                st.error("Password must be at least 8 characters.")
            elif password != password2:
                st.error("Passwords do not match.")
            else:
                db = get_db()
                try:
                    if get_user_by_email(db, email) is not None:
                        st.error("An account with that email already exists.")
                    else:
                        user = create_user(
                            db,
                            email=email,
                            full_name=full_name,
                            password=password,
                            profile_notes=profile_notes,
                        )
                        st.session_state["user_id"] = user.id
                        st.session_state.pop("conversation_id", None)
                        st.success("Account created. You are now logged in.")
                        st.rerun()
                finally:
                    db.close()


# ---------- MAIN APP (LOGGED-IN) ----------

def show_main_app(user: User) -> None:
    db = get_db()
    try:
        conversation = get_or_create_active_conversation(db, user)
        history = get_conversation_history(db, conversation)

        # ----- SIDEBAR -----
        with st.sidebar:
            st.subheader("Your profile")
            st.write(f"**Name:** {user.full_name}")
            st.write(f"**Email:** {user.email}")

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

        # ----- MAIN CONTENT -----
        st.title("💆‍♀️ Claire – Relaxation Companion")

        st.caption(
            "Claire is an AI coach inspired by the work of Dr. Claire Weekes. "
            "She is not a doctor or therapist and cannot provide crisis support."
        )

        # Quick action buttons
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("3-minute breathing", use_container_width=True):
                handle_quick_action(
                    db,
                    user,
                    conversation,
                    "Guide me through a simple 3-minute breathing exercise in your usual style.",
                )
        with col2:
            if st.button("Racing thoughts", use_container_width=True):
                handle_quick_action(
                    db,
                    user,
                    conversation,
                    "My thoughts are racing. Walk me through facing, accepting, floating, and letting time pass.",
                )
        with col3:
            if st.button("Body tension scan", use_container_width=True):
                handle_quick_action(
                    db,
                    user,
                    conversation,
                    "Guide me through a slow body scan to release tension in your usual style.",
                )

        # Reload history (in case something changed while drawing buttons)
        history = get_conversation_history(db, conversation)

        # Render existing messages
        for msg in history:
            role = "user" if msg.sender_role == "user" else "assistant"
            with st.chat_message(role):
                st.markdown(msg.content)

        # Chat input
        user_input = st.chat_input("Tell Claire what's going on...")
        if user_input:
            # Save user message
            user_msg = Message(
                conversation_id=conversation.id,
                sender_role="user",
                content=user_input,
            )
            db.add(user_msg)
            db.commit()

            # History including the new message
            history = get_conversation_history(db, conversation)

            # Generate reply
            try:
                reply_text = generate_claire_reply(user, history)
            except Exception as e:
                reply_text = (
                    "I hit an issue while trying to respond. "
                    "Check the server logs or your OpenAI configuration and try again.\n\n"
                    f"Error: {e}"
                )

            assistant_msg = Message(
                conversation_id=conversation.id,
                sender_role="assistant",
                content=reply_text,
            )
            db.add(assistant_msg)
            db.commit()

            # Show the latest exchange immediately
            with st.chat_message("user"):
                st.markdown(user_input)
            with st.chat_message("assistant"):
                st.markdown(reply_text)

    finally:
        db.close()


# ---------- ENTRYPOINT ----------

def main() -> None:
    init_db()

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
