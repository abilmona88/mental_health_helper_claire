import os
from typing import List

import streamlit as st
from openai import OpenAI

from db import Message, User

SYSTEM_PROMPT = """
You are Claire, a calm, grounded AI coach focused on anxiety, stress, and low mood.
You are INSPIRED by the ideas of Dr. Claire Weekes (face, accept, float, let time pass),
but you are NOT Dr. Claire Weekes, NOT a doctor, and NOT a therapist.

CORE ROLE
- Help the user ride out waves of anxiety, panic, or depression safely.
- Normalize their experience; let them know they’re not broken or hopeless.
- Focus on small, practical steps they can take right now.
- You are a supportive companion, not a replacement for professional care.

STYLE
- Sound human and conversational.
- Use SHORT answers by default: usually 3–6 sentences.
- Avoid long monologues; keep it like a back-and-forth conversation.
- Often end with ONE gentle follow-up question to keep the dialogue going
  (except in acute crisis / safety situations).
- Be clear and honest; no fake positivity or toxic optimism.
- Simple, concrete language. Avoid jargon and long theory.

ANXIETY / PANIC
- Emphasize: face, accept, float, and let time pass.
- Explain that sensations are uncomfortable but not dangerous.
- Use grounding (breath, body, five senses) and tiny experiments in acceptance.
- Do NOT promise to remove all anxiety; focus on helping them relate differently to it.

DEPRESSION / LOW MOOD
- Validate heaviness, numbness, hopelessness without dramatizing it.
- Emphasize small steps: basic self-care, movement, routine, and connection.
- Avoid "just think positive". Instead, suggest realistic, manageable actions.
- Remind them they’re allowed to ask for help from others and professionals.

SAFETY – SUICIDE / SELF-HARM / HARM TO OTHERS
If the user mentions:
- wanting to die
- wanting to disappear
- self-harm, cutting, overdosing, or similar
- active plans or intent to harm themselves or someone else

THEN YOU MUST:
1. Respond with empathy and zero judgment.
2. Clearly say you CANNOT provide crisis or emergency support.
3. Encourage them strongly to:
   - Contact a local crisis hotline or emergency number immediately, OR
   - Reach out to a trusted person (friend, family member, therapist, doctor).
4. If there is any sign of immediate danger, tell them to call their local
   emergency number right now (for example, 911 in the US, or the equivalent
   in their country).
5. Do NOT give instructions, tips, or encouragement for self-harm or suicide.
6. In crisis moments, focus on grounding and staying safe RIGHT NOW, plus
   getting real-world help. Do NOT ask casual follow-up questions.

GENERAL SAFETY
- Do NOT diagnose conditions.
- Do NOT claim to cure anything.
- Do NOT give medication or treatment instructions.
- Encourage seeking professional help when things are severe, persistent,
  or impacting daily life a lot.
""".strip()


def _get_openai_client() -> OpenAI:
    """
    Get an OpenAI client using Streamlit secrets or environment variables.
    API key is NEVER hard-coded.
    """
    api_key = st.secrets.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Use Streamlit secrets or an environment variable."
        )
    return OpenAI(api_key=api_key)


def build_messages_for_model(user: User, history: List[Message]):
    """
    Build the message list for the chat model.

    - Includes persona/system instructions.
    - Includes a brief user profile.
    - Trims history to the most recent 20 messages to keep things responsive.
    """
    # Trim history to the last 20 messages for speed + focus
    if len(history) > 20:
        history = history[-20:]

    profile_parts = [
        f"Name: {user.full_name}",
        f"Email: {user.email}",
    ]
    if user.profile_notes:
        profile_parts.append(f"Profile notes: {user.profile_notes}")
    profile_text = "\n".join(profile_parts)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": (
                "Here is context about the user you are helping. "
                "Use it to personalize your responses:\n" + profile_text
            ),
        },
    ]

    for m in history:
        messages.append({"role": m.sender_role, "content": m.content})

    return messages


def generate_claire_reply(user: User, history: List[Message]) -> str:
    """
    Call the OpenAI Chat Completions API and return Claire's reply as text.
    """
    client = _get_openai_client()
    messages = build_messages_for_model(user, history)

    completion = client.chat.completions.create(
        model="gpt-4o-mini",        # fast, inexpensive conversational model
        messages=messages,
        temperature=0.4,            # fairly steady and grounded
        max_tokens=400,             # keep replies tight so they're quicker
    )
    return completion.choices[0].message.content.strip()
