# Claire – Relaxation Companion (Streamlit + OpenAI)

This is a full Streamlit application that:

- Provides a calming chat experience with **Claire**, an AI relaxation companion inspired by the ideas of Dr. Claire Weekes (but not her).
- Uses **OpenAI's Chat Completion API** safely on the server side.
- Implements **user accounts** (sign up / log in) with hashed passwords.
- Stores **per-user chat history** and **user profile notes** in a local SQLite database.
- Is ready to run locally in PyCharm and to deploy on **Streamlit Cloud** without exposing your OpenAI API key in the repo.

---

## 1. Project structure

```text
claire_relaxation_app/
├── app.py
├── auth.py
├── claire_ai.py
├── db.py
├── README.md
├── requirements.txt
├── .gitignore
└── .streamlit/
    └── secrets.toml.example
```

At runtime, a SQLite database file named `claire_app.db` will be created in the project root.

---

## 2. Installation (local, e.g. in PyCharm)

1. **Clone or unzip** this project into a folder:

   ```bash
   cd claire_relaxation_app
   ```

2. (Recommended) Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # macOS / Linux
   # .venv\Scripts\activate  # Windows
   ```

3. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure your OpenAI API key** (never committed to Git):

   - Copy the example secrets file:

     ```bash
     mkdir -p .streamlit
     cp .streamlit/secrets.toml.example .streamlit/secrets.toml
     ```

   - Edit `.streamlit/secrets.toml` and put your real key:

     ```toml
     OPENAI_API_KEY = "sk-your-real-key-here"
     ```

   Alternatively, you can set an environment variable:

   ```bash
   export OPENAI_API_KEY="sk-your-real-key-here"
   ```

5. **Run the app using Streamlit**:

   From PyCharm's terminal (or any terminal in this folder):

   ```bash
   streamlit run app.py
   ```

   Your browser should open at something like:

   - http://localhost:8501

---

## 3. Running in Streamlit Cloud (public web app, key still hidden)

1. Push this project to a new **GitHub repo**, making sure:

   - `.streamlit/secrets.toml` is **NOT** in the repo (it’s ignored by `.gitignore`).
   - Only `.streamlit/secrets.toml.example` is committed (safe; no real key).

2. On **Streamlit Cloud**:

   - Click “New app”
   - Connect your GitHub repo and select `app.py` as the main file.

3. In the Streamlit Cloud app settings:

   - Go to **“Secrets”** (or “Advanced → Secrets”)
   - Paste:

     ```toml
     OPENAI_API_KEY = "sk-your-real-key-here"
     ```

4. Deploy.

Your app is now public, but your OpenAI API key lives only in the Streamlit secrets backend (or env vars on the server). Users, forks, and GitHub itself never see the key.

---

## 4. How user accounts & history work

- Users **sign up** with:
  - Email
  - Full name
  - Password
  - Optional profile notes (“what tends to help you relax”, triggers, etc.)

- Passwords are **hashed** with bcrypt via `passlib`. The raw password is never stored.

- On successful login:
  - `user_id` is stored in `st.session_state`.
  - The app fetches or creates an active conversation for that user.
  - All messages in that conversation are loaded from the database and displayed.

- When the user sends a new message:
  - It’s saved to the `messages` table in SQLite.
  - The model is called with:
    - A system persona prompt for Claire (relaxation-focused, safety-aware).
    - A second system message summarizing the user profile (based on DB).
    - The conversation history messages for that user.
  - The assistant’s reply is saved and displayed.

- Users can start a **new session** from the sidebar; the previous one remains stored.

---

## 5. Security and safety notes

- **OpenAI API key:**
  - Never hard-coded.
  - Loaded only from Streamlit secrets or environment variables on the server.
  - `.streamlit/secrets.toml` is in `.gitignore` so it’s never committed.

- **Passwords:**
  - Stored only as bcrypt hashes.
  - Use a strong password in production.

- **Mental health boundaries:**
  - Claire is **not** a doctor or therapist.
  - The system prompt instructs the model to:
    - Avoid diagnosis.
    - Avoid claims of cure.
    - Redirect users to professionals / emergency services if they mention self-harm or harm to others.

---

## 6. Notes for PyCharm

- Open the folder `claire_relaxation_app` in PyCharm.
- Configure the interpreter to use `.venv` if you created one.
- Use a **Run Configuration** like:
  - Script: `streamlit`
  - Parameters: `run app.py`
  - Or simply run `streamlit run app.py` from the integrated terminal.

You can then develop, debug, and tweak everything right in PyCharm while still using Streamlit as the runtime.

---
# mental_health_helper_claire
