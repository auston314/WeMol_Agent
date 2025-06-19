import streamlit as st
import asyncio
import random, string, os, smtplib, json
from openai import OpenAI  # Updated import for new API interface
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from mcp_host import MCPHost
import streamlit.components.v1 as components
import atexit
from streamlit_molstar import st_molstar  # Import the Mol* viewer package

# Set the page configuration to wide layout.
st.set_page_config(page_title="ChatMol Copilot", layout="wide")

# Custom CSS for the sticky right panel and compact UI
st.markdown("""
<style>
    /* Global compact styling with increased top padding for header visibility */
    div.block-container {
        padding-top: 1rem !important;
        padding-bottom: 0.5rem !important;
    }
    
    /* Further reduce spacing in all containers */
    .stForm [data-testid="stFormSubmitButton"] > button {
        margin-top: -15px !important;
        height: 20px !important;
    }
    
    /* Remove unnecessary padding in columns */
    [data-testid="column"] > div {
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }
    
    /* Make column height fill viewport */
    div[data-testid="column"]:nth-child(2) {
        position: relative; /* Make this the positioning context */
        height: 100vh; /* Full viewport height */
    }
    
    .sticky-viewer-container {
        position: fixed; /* Fixed positioning relative to viewport */
        top: 5rem; /* Increase top spacing to account for Streamlit header plus some buffer */
        right: 1rem;
        width: calc(50% - 2rem); /* Match the column width minus margins */
        height: calc(95vh - 5rem); /* Adjust height to leave space at top and bottom */
        overflow-y: auto;
        background: transparent; /* Changed from white to transparent */
        margin: 0 !important;
        padding: 1rem !important;
        z-index: 999; /* Higher z-index to ensure it's on top */
        box-shadow: none !important;
        border: none !important;
        border-radius: 0 !important;
    }
    
    /* Make sure the molecules display correctly */
    .sticky-viewer-container div {
        max-width: 100%;
    }
    
    /* Ensure chat area gets equal width */
    div[data-testid="column"]:nth-child(1) {
        width: 50%;
    }
    
    /* Make sure the molstar viewer is visible with no white background */
    .molstar-container {
        z-index: 1000 !important; 
        position: relative !important;
        visibility: visible !important;
        opacity: 1 !important;
        background: transparent !important;
        box-shadow: none !important;
        border: none !important;
        border-radius: 0 !important;
    }
    
    /* Remove any background from mol viewer components */
    .molstar-container > div, 
    .molstar-container > div > div {
        background: transparent !important;
        box-shadow: none !important;
        border: none !important;
    }
    
    /* Ensure all elements within viewer container remain visible */
    .sticky-viewer-container * {
        visibility: visible !important;
        opacity: 1 !important;
    }
    
    /* Fix for the white overlay problem */
    iframe, canvas, svg {
        visibility: visible !important;
        z-index: 1000 !important; 
        position: relative !important;
        background: transparent !important;
        box-shadow: none !important;
        border: none !important;
    }
    
    /* Additional fix for any remaining white backgrounds */
    .sticky-viewer-container .element-container {
        background: transparent !important;
    }
</style>
""", unsafe_allow_html=True)

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
    st.session_state.chat_display_index = 0
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
if "chat_display_index" not in st.session_state:
    st.session_state.chat_display_index = 0  # Index for chat history navigation
if "selected_model" not in st.session_state:
    st.session_state.selected_model = "gpt-4o"
if "log_message" not in st.session_state:
    st.session_state.log_message = ""
if "event_loop" not in st.session_state:
    st.session_state.event_loop = asyncio.new_event_loop()

if "mcp_host" not in st.session_state:
    config_file = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            config_json = f.read()
        config = json.loads(config_json)
        servers = config.get("mcpServers", {})
        if len(servers) > 0:
            llm_config = {"timeout": 300}
            # Use OpenAI model
            mcp_host = MCPHost("openai", llm_config=llm_config)
            # Use Anthropic
            #mcp_host = MCPHost("anthropic", llm_config=llm_config)
            shared_loop = st.session_state.event_loop
            asyncio.set_event_loop(shared_loop)
            shared_loop.run_until_complete(mcp_host.connect_mcp_servers(servers))
            print("MCP host connected")

            # Define a cleanup function to close the connection
            def cleanup():
                if 'mcp_host' in st.session_state and st.session_state.mcp_host is not None and 'event_loop' in st.session_state:
                    shared_loop = st.session_state.event_loop
                    mcp_host = st.session_state.mcp_host
                    if hasattr(mcp_host, 'close') and callable(mcp_host.close):
                        try:
                            asyncio.get_event_loop()
                        except RuntimeError:
                            # If no event loop is running, create a new one
                            asyncio.set_event_loop(shared_loop)
                            shared_loop.run_until_complete(mcp_host.close())
                            print("MCP host connection closed")

                        if shared_loop.is_running():
                            # If the loop is running, close the connection in a new thread
                            print("MCP shared loop is running, try to close it")
                            shared_loop.run_until_complete(mcp_host.close())
                        else:
                            # If the loop is not running, close the connection directly
                            print("MCP shared loop is not running, try to close it")
                            asyncio.set_event_loop(shared_loop)
                            shared_loop.run_until_complete(mcp_host.close())
                            print("MCP host connection closed")
                        asyncio.set_event_loop(shared_loop)
                        shared_loop.run_until_complete(mcp_host.cleanup())
                        print("MCP host connection closed")
            # Register the cleanup function to be called on exit            
            atexit.register(cleanup)
            st.session_state.mcp_host = mcp_host
        else:
            st.session_state.mcp_host = None

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

# Main content area: Divided into Chat and Molecular Viewer
if st.session_state.logged_in:
    # Create two columns: one for chat, one for the molecular viewer with equal width
    col_chat, col_viewer = st.columns([1, 1], gap="small")  # Equal width columns

    with col_chat:
        # Increase top margin significantly to ensure title is fully visible below Streamlit banner
        st.markdown("<h4 style='margin-top: 30px; margin-bottom: 5px;'>Chat Area</h4>", unsafe_allow_html=True)
        
        # Helper functions for navigation
        def navigate_previous():
            if st.session_state.chat_display_index > 0:
                st.session_state.chat_display_index -= 6
                if st.session_state.chat_display_index < 0:
                    st.session_state.chat_display_index = 0
        
        def navigate_next():
            max_index = max(0, len(st.session_state.chat_messages) - 6)
            if st.session_state.chat_display_index < max_index:
                st.session_state.chat_display_index += 6
                if st.session_state.chat_display_index > max_index:
                    st.session_state.chat_display_index = max_index

        # --- Render only two messages from chat history based on display index ---
        chat_container = st.empty()
        with chat_container.container():
            # Always show the most recent messages by default
            if len(st.session_state.chat_messages) == 0:
                st.info("No messages yet. Start a conversation!")
            else:
                # Get six messages to display based on the current index
                start_idx = st.session_state.chat_display_index
                end_idx = min(start_idx + 6, len(st.session_state.chat_messages))
                display_messages = st.session_state.chat_messages[start_idx:end_idx]
                
                for msg in display_messages:
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

        # --- Display the multi-line message input form with compact styling ---
        with st.form(key="chat_form", clear_on_submit=True):
            # Further reduce height of text area
            user_message = st.text_area("", height=70, placeholder="Type your message here...", label_visibility="collapsed")
            
            # Custom styling for a more compact form with reduced spacing
            st.markdown("""
                <style>
                    /* Reduce padding in the text area */
                    .stTextArea textarea {
                        padding: 4px !important;
                        min-height: 60px !important;
                    }
                    
                    /* Make buttons significantly more compact */
                    .stButton button {
                        padding-top: 0px !important;
                        padding-bottom: 0px !important;
                        line-height: 0.9 !important;
                        min-height: 20px !important;
                        height: 22px !important;
                        font-size: 0.8em !important;
                    }
                    
                    /* More aggressive button height reduction specifically for the form submit button */
                    [data-testid="stFormSubmitButton"] button {
                        height: 20px !important;
                        min-height: 20px !important;
                        margin-top: -10px !important;
                        margin-bottom: 0px !important;
                    }
                    
                    /* Remove excess spacing around form elements */
                    .stForm {
                        padding-bottom: 0 !important;
                        margin-bottom: 0 !important;
                    }
                    
                    /* Reduce form padding */
                    .stForm > div:first-child {
                        padding-top: 0 !important;
                        padding-bottom: 0 !important;
                    }
                    
                    /* Reduce spacing between form elements */
                    .stForm > div > div {
                        margin-bottom: 0px !important; 
                    }
                    
                    /* Reduce space between text area and submit button */
                    .stTextArea {
                        margin-bottom: -15px !important;
                    }
                </style>
            """, unsafe_allow_html=True)
            
            # Changed button text to be more descriptive
            submit_button = st.form_submit_button("Send Your Message")
            
        # Chat navigation buttons - positioned after the input form with compact styling
        col_nav_prev, col_nav_info, col_nav_next = st.columns([1, 2, 1])
        
        with col_nav_prev:
            # More compact button with less height
            if st.button("← Previous", key="prev_msgs", use_container_width=True):
                navigate_previous()
        
        with col_nav_info:
            # Calculate total groups of 6 messages and current position
            total_groups = max(1, (len(st.session_state.chat_messages) + 5) // 6)
            current_group = (st.session_state.chat_display_index // 6) + 1
            if len(st.session_state.chat_messages) > 0:
                st.markdown(f"<div style='text-align: center; margin-top: 0; padding-top: 0; font-size: 0.8em;'>Page {current_group}/{total_groups}</div>", unsafe_allow_html=True)
        
        with col_nav_next:
            # More compact button with less height
            if st.button("Next →", key="next_msgs", use_container_width=True):
                navigate_next()
        
        if submit_button and user_message.strip():
            st.session_state.chat_messages.append({"role": "user", "content": user_message})
            option = 2
            if (option == 1):
                ai_response = generate_ai_response()
            else:
                if st.session_state.mcp_host is not None:
                    try:
                        loop = st.session_state.event_loop
                        asyncio.set_event_loop(loop)
                        async def get_ai_response():
                            try:
                                return await st.session_state.mcp_host.process_query(user_message.strip())
                            except Exception as e:
                                return f"Error generating AI response: {e}"
                        
                        mcp_coroutine = get_ai_response()
                        mcp_response = loop.run_until_complete(asyncio.wait_for(mcp_coroutine, timeout=300))
                        ai_response = mcp_response if mcp_response else "What can I assist you today?"

                    except asyncio.TimeoutError:
                        ai_response = "Error: Request timed out. Please try again."
                    except Exception as e:
                        ai_response = f"Error generating AI response: {e}"
                else:
                    ai_response = "Error: No server connection. Please check your configuration."
            
            # Add response to chat history
            st.session_state.chat_messages.append({"role": "assistant", "content": ai_response})
            
            # Update display index to show the latest messages
            st.session_state.chat_display_index = max(0, len(st.session_state.chat_messages) - 6)
            
            st.rerun()  # Forces re-run to update the chat history display

    with col_viewer:
        st.markdown("<div class='sticky-viewer-container'>", unsafe_allow_html=True)
        
        # Add Mol* viewer with sample files
        mol_data_dir = os.path.join(os.path.dirname(__file__), "mol_data")
        # Include both PDB and SDF format molecules
        molecule_files = [f for f in os.listdir(mol_data_dir) if f.endswith(('.pdb', '.sdf', '.sd'))]
        
        if len(molecule_files) > 0:
            # First display the molecule viewer without selector
            # Get the first molecule file as default or use session state to store selection
            if "selected_molecule" not in st.session_state:
                st.session_state.selected_molecule = molecule_files[0]
                
            molecule_file_path = os.path.join(mol_data_dir, st.session_state.selected_molecule)
            
            # Display the selected molecule with Mol* - ensure it's visible with correct height and no white background
            with st.container():
                # Apply inline styling to remove background
                st.markdown("""
                    <style>
                        div[data-testid="stVerticalBlock"] > div:has(div[data-testid="element-container"]) {
                            background: transparent !important;
                            box-shadow: none !important;
                            border: none !important;
                        }
                    </style>
                """, unsafe_allow_html=True)
                st_molstar(molecule_file_path, height=500, key="mol_viewer")
                
                # Add molecule selector below the viewer
                def change_molecule():
                    st.session_state.selected_molecule = st.session_state.mol_selector
                
                st.selectbox("", molecule_files, key="mol_selector", 
                              label_visibility="collapsed", 
                              index=molecule_files.index(st.session_state.selected_molecule),
                              on_change=change_molecule)
        else:
            st.markdown("""
                <div style="height: 100%; min-height: 500px; border: 1px solid #ccc; 
                        background-color: #f0f0f0; display: flex; 
                        align-items: center; justify-content: center;">
                    <p>No PDB files found in mol_data directory</p>
                </div>
            """, unsafe_allow_html=True)
            
        st.markdown("</div>", unsafe_allow_html=True) # Close the sticky-viewer-container div
else:
    # Add custom styling to ensure login message has adequate top margin
    st.markdown("""
        <style>
            /* Add extra top margin to the login message */
            .element-container:has(.stAlert) {
                margin-top: 50px !important;
            }
        </style>
    """, unsafe_allow_html=True)
    st.info("Please log in to start chatting.")
    # The main header "Chat Area" is removed from here as it's now part of the logged-in view.
    # You can add a general message or layout for the non-logged-in state if desired.

