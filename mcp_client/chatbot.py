import streamlit as st
import random, string, os, smtplib, json
from openai import OpenAI  # Updated import for new API interface
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import streamlit.components.v1 as components

# Set the page configuration to wide layout.
st.set_page_config(page_title="ChatMol Copilot", layout="wide")

# -------------------------------
# File for storing user credentials
# -------------------------------
USER_FILE = "users.json"

def load_users():
    if os.path.exists(USER_FILE):
        with open(USER_FILE, "r") as f:
            return json.load(f)
    else:
        return {}

def save_users(users):
    with open(USER_FILE, "w") as f:
        json.dump(users, f)

# -------------------------------
# LLM_CLIENT
# -------------------------------
def get_llm_client(provider):
    # OpenAI client
    if provider == "OpenAI":
        openai_api_key = os.environ['OPENAI_API_KEY']
        client = OpenAI(api_key=openai_api_key)
    # DeepSeek client
    elif provider == "DeepSeek":
        ds_api_key = os.environ["DS_API_KEY"]
        client = OpenAI(api_key=ds_api_key, base_url="https://api.deepseek.com")
    # Ollama client
    elif provider == "Ollama":
        client = OpenAI(
            base_url='https://www.chatmol.org/ollama/v1/',
            api_key='ollama',  # required but ignored
        )
    else:
        st.error("Unknown LLM provider")
        client = None
    return client

# Set default client (change provider as needed)
client = get_llm_client("Ollama")

# -------------------------------
# Avatars (example URLs)
# -------------------------------
USER_AVATAR = "https://www.pngitem.com/pimgs/m/146-1468479_my-profile-icon-blank-profile-picture-circle-hd.png"
AI_AVATAR = "https://cdn-icons-png.flaticon.com/512/4712/4712100.png"

# -------------------------------
# Email Sending Function
# -------------------------------
def send_mail_to_user(to_email, password):
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    smtp_user = "jinyuansun@chatmol.org"
    smtp_password = "ifws xlnh jpgw fkyr"

    msg = MIMEMultipart()
    msg['From'] = smtp_user
    msg['To'] = to_email
    msg['Subject'] = "Login information of ChatMol copilot"
    body = f"Dear user,\nWelcome to ChatMol copilot!\nYour login email is: {to_email}.\nYour password is: {password}."
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  # Enable TLS for security
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        return False

# -------------------------------
# Helper Functions for Authentication and Chat
# -------------------------------
def generate_password(length=8):
    """Generate a random alphanumeric password."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def handle_signup():
    email = st.session_state.get("email", "").strip()
    if not email:
        st.session_state.log_message = "Please enter an email address."
        return
    if email in st.session_state.users:
        st.session_state.log_message = "User already exists. Please log in instead."
    else:
        password = generate_password()
        st.session_state.users[email] = password
        save_users(st.session_state.users)
        if 'adp.com' in email:
            st.session_state.log_message = f"Signup successful! Here is your password; please keep it safe: {password}"
        else:
            if send_mail_to_user(email, password):
                st.session_state.log_message = "Signup successful! A password has been sent to your email."
            else:
                st.session_state.log_message = "Failed to send email. Please try again."

def handle_login():
    email = st.session_state.get("email", "").strip()
    password = st.session_state.get("password", "")
    if not email or not password:
        st.session_state.log_message = "Please enter both email and password."
        return
    if email in st.session_state.users and st.session_state.users[email] == password:
        st.session_state.logged_in = True
        st.session_state.log_message = "Login successful!"
    else:
        st.session_state.log_message = "Login failed. Incorrect email or password."

def handle_new_chat():
    st.session_state.chat_messages = []
    st.session_state.log_message = "New chat started."

def generate_ai_response():
    # Select the client based on the chosen model
    model_name = st.session_state.selected_model
    if model_name in ['gpt-4o', 'gpt-o3-mini', 'gpt-4o-mini']:
        client = get_llm_client('OpenAI')
    elif model_name == 'deepseek-chat':
        client = get_llm_client("DeepSeek")
    else:
        print("Ollama model ", model_name)
        client = get_llm_client("Ollama")
    try:
        responses = client.chat.completions.create(
            model=model_name,
            messages=[system_message] + st.session_state.chat_messages
        )
        ai_message = responses.choices[0].message.content
        print("ai message =", ai_message)
        return ai_message
    except Exception as e:
        return f"Error generating AI response: {e}"

# -------------------------------
# Initialize Session State Variables
# -------------------------------
if "users" not in st.session_state:
    st.session_state.users = load_users()  # Load users from file
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []  # Conversation messages
if "selected_model" not in st.session_state:
    st.session_state.selected_model = "gpt-4o"
if "log_message" not in st.session_state:
    st.session_state.log_message = ""

system_prompt = f"""
You are an assistant on various tasks, such as answer various user questions in a specific domain. Please provide answers based on the information provided.
"""
system_message = {"role": "user", "content": system_prompt}

# -------------------------------
# Layout: Sidebar for Control Panel and Main Area for Chat
# -------------------------------
with st.sidebar:
    st.header("Control Panel")
    # Email and Password Inputs
    st.text_input("Email Address", key="email")
    st.text_input("Password", type="password", key="password")
    # AI Model Selection
    st.selectbox(
        "Select AI Model",
        options=[
            "gpt-4o", "gpt-4o-mini", "gpt-o3-mini",
        ],
        key="selected_model"
    )
    # Login and Sign Up Buttons in two columns
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("Login"):
            handle_login()
    with col_btn2:
        if st.button("Sign Up"):
            handle_signup()
    # New Chat button clears conversation history
    if st.button("New Chat"):
        handle_new_chat()
    # Display the log message at the bottom.
    st.markdown("---")
    st.markdown(f"**Log:** {st.session_state.log_message}")

st.header("Chat Area")

if st.session_state.logged_in:

    # --- Render the entire chat history via a placeholder ---
    chat_container = st.empty()
    with chat_container.container():
        for msg in st.session_state.chat_messages:
            if msg["role"] == "user":
                user_html = (
                    f"""<div style="display: flex; align-items: flex-start; margin-bottom: 10px;">
  <img src="{USER_AVATAR}" width="30" style="margin-right: 10px;">
  <div style="background: #e0f7fa; color: #000; padding: 8px; border-radius: 5px; max-width:80%;">
    {msg['content']}
  </div>
</div>"""
                )
                st.markdown(user_html, unsafe_allow_html=True)
            elif msg["role"] == "assistant":
                if "```" in msg["content"]:
                    parts = msg["content"].split("```")
                    rendered_message = ""
                    for i, part in enumerate(parts):
                        if i % 2 == 0:
                            rendered_message += part
                        else:
                            rendered_message += f"\n```python\n{part}\n```\n"
                    ai_html = (
                        f"""<div style="display: flex; align-items: flex-start; margin-bottom: 10px;">
  <img src="{AI_AVATAR}" width="30" style="margin-right: 10px;">
  <div style="background: #e8f5e9; color: #000; padding: 8px; border-radius: 5px; max-width:80%;">
    {rendered_message}
  </div>
</div>"""
                    )
                    st.markdown(ai_html, unsafe_allow_html=True)
                else:
                    ai_html = (
                        f"""<div style="display: flex; align-items: flex-start; margin-bottom: 10px;">
  <img src="{AI_AVATAR}" width="30" style="margin-right: 10px;">
  <div style="background: #e8f5e9; color: #000; padding: 8px; border-radius: 5px; max-width:80%;">
    {msg['content']}
  </div>
</div>"""
                    )
                    st.markdown(ai_html, unsafe_allow_html=True)

    # --- Display the multi-line message input form ---
    with st.form(key="chat_form", clear_on_submit=True):
        user_message = st.text_area("Your Message", height=150)
        submit_button = st.form_submit_button("Send")
    if submit_button and user_message.strip():
        st.session_state.chat_messages.append({"role": "user", "content": user_message})
        ai_response = generate_ai_response()
        st.session_state.chat_messages.append({"role": "assistant", "content": ai_response})
        st.rerun()  # Forces re-run to update the chat history display
else:
    st.info("Please log in to start chatting.")

