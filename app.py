import streamlit as st
import google.oauth2.credentials
import googleapiclient.discovery
import requests
from urllib.parse import urlencode
import pandas as pd
import base64
import datetime
import time

# Google OAuth Configuration
CLIENT_ID = st.secrets["google"]["client_id"]
CLIENT_SECRET = st.secrets["google"]["client_secret"]
REDIRECT_URI = "https://fasi96-foodpandaexpensetracker-app-j4oqdj.streamlit.app/"  # Make sure this matches your Google Cloud Console settings
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# Store user credentials in session
if "credentials" not in st.session_state:
    st.session_state["credentials"] = None

def get_authorization_url():
    """Generate Google OAuth authorization URL."""
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "access_type": "online",
        "prompt": "consent",
    }
    return f"{AUTHORIZATION_URL}?{urlencode(params)}"

def exchange_code_for_tokens(auth_code):
    """Exchange authorization code for access tokens."""
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": auth_code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    }

    response = requests.post(TOKEN_URL, data=data)
    if not response.ok:
        raise Exception(f"Failed to exchange code: {response.text}")
    
    token_data = response.json()
    if 'access_token' not in token_data:
        raise Exception(f"No access token in response: {token_data}")

    st.write("Query Params:", st.query_params)
    st.write("Auth Code:", auth_code)
    st.write("Tokens:", token_data)
    return token_data

def get_emails_from_sender(service, sender_email, days=365, max_results=1000):
    # indicate that it will only process 1000 emails
    st.write("This will only process latest 1000 emails")
    """Fetching Emails from Foodpanda"""
    # Create placeholder metrics for real-time updates
    progress_counter = st.empty()
    current_total = st.empty()
    emails_processed = st.empty()
    
    running_total = 0
    processed_count = 0
    
    # Rest of the existing setup code...
    now = datetime.datetime.now()
    days_ago = now - datetime.timedelta(days=days)
    after_timestamp = int(time.mktime(days_ago.timetuple()))
    query = f"from:{sender_email} after:{after_timestamp}"

    try:
        results = service.users().messages().list(
            userId="me",
            maxResults=max_results,
            q=query
        ).execute()
        
        messages = results.get("messages", [])

        if not messages:
            st.warning(f"No emails found from {sender_email} in the last {days} days.")
            return

        total_messages = len(messages)
        data_dict = {'date': [], 'price': []}

        for i, msg in enumerate(messages, 1):
            msg_details = service.users().messages().get(
                userId="me",
                id=msg["id"]
            ).execute()
            
            headers = msg_details["payload"]["headers"]
            date = next((h["value"] for h in headers if h["name"] == "Date"), "No Date")
            content = msg_details["payload"]["parts"][0]["body"]["data"]
            decoded_content = base64.urlsafe_b64decode(content).decode('utf-8')
            
            try:
                price = decoded_content.split('Total')[1].split('PKR')[1].split('\n')[0].strip()
            except:
                price = decoded_content.split('Received')[1].split('Rs.')[1].split('\n')[0].strip()

            price = float(price.replace(',', ''))
            data_dict['date'].append(date)
            data_dict['price'].append(price)
            
            # Update running totals and progress
            running_total += price
            processed_count += 1
            
            # Update progress indicators
            progress_counter.progress(i / total_messages, f"Processing email {i} of {total_messages}")
            current_total.metric("Running Total", f"PKR {running_total:,.2f}")
            emails_processed.metric("Emails Processed", f"{processed_count}/{total_messages}")
            time.sleep(0.05)  # Small delay for visual effect

        # Clear progress indicators
        progress_counter.empty()
        current_total.empty()
        emails_processed.empty()
        
        return data_dict

    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        return None

def get_gmail_messages(credentials):
    """Fetch and analyze Foodpanda expenses from Gmail."""
    service = googleapiclient.discovery.build("gmail", "v1", credentials=credentials)
    
    # Get expenses data
    data_dict = {'date': [], 'price': []}
    try:
        service_results = get_emails_from_sender(service, "no-reply@mail.foodpanda.pk", days=days_to_analyze)
        if service_results:
            data_dict = service_results
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        return
    
    if not data_dict['date']:
        st.warning("📭 No Foodpanda orders found in the specified period.")
        return
    
    # Rest of your existing code for DataFrame processing and visualization
    df = pd.DataFrame(data_dict)
    df['date'] = pd.to_datetime(df['date'])
    
    # Calculate date range for display
    latest_order = df['date'].max()
    earliest_order = df['date'].min()
    date_range = f"{earliest_order.strftime('%B %d, %Y')} - {latest_order.strftime('%B %d, %Y')}"
    
    st.markdown(f"### 📅 Analysis Period: {date_range}")
    
    # Create DataFrame and process dates
    df = pd.DataFrame(data_dict)
    df['date'] = pd.to_datetime(df['date'])
    df['month_year'] = df['date'].dt.strftime('%B %Y')
    
    # Calculate monthly totals and sort by most recent first
    monthly_expenses = df.groupby('month_year')['price'].agg(['sum', 'count']).reset_index()
    monthly_expenses.columns = ['Month', 'Total Spent (PKR)', 'Number of Orders']
    
    # Convert Month to datetime for proper sorting
    monthly_expenses['Month_dt'] = pd.to_datetime(monthly_expenses['Month'], format='%B %Y')
    monthly_expenses = monthly_expenses.sort_values('Month_dt', ascending=False)
    monthly_expenses = monthly_expenses.drop('Month_dt', axis=1)  # Remove helper column

    # Display total statistics
    total_spent = df['price'].sum()
    total_orders = len(df)
    avg_order = total_spent / total_orders if total_orders > 0 else 0
    
    # Create three columns for key metrics with adjusted widths
    col1, col2, col3 = st.columns([1.5, 0.8, 1])  # Increased width of first column
    with col1:
        st.metric("Total Spent", f"PKR {total_spent:,.2f}")
    with col2:
        st.metric("Total Orders", total_orders)
    with col3:
        st.metric("Average Order", f"PKR {avg_order:,.2f}")
    
    # Display monthly breakdown
    st.subheader("📊 Monthly Breakdown")
    st.dataframe(monthly_expenses, hide_index=True)
    
    # Create a bar chart for monthly expenses
    st.subheader("📈 Monthly Spending Trend")
    chart_data = monthly_expenses.set_index('Month')
    st.bar_chart(chart_data['Total Spent (PKR)'])
    
    # Show recent orders
    st.subheader("🛵 Recent Orders")
    recent_orders = df.sort_values('date', ascending=False).head()
    recent_orders['date'] = recent_orders['date'].dt.strftime('%Y-%m-%d %H:%M')
    st.dataframe(recent_orders[['date', 'price']], hide_index=True)

# Streamlit UI
st.set_page_config(
    page_title="FoodPanda Expense Tracker",
    page_icon="🐼"
)

st.title("🐼 FoodPanda Expense Tracker")
st.markdown("Track and analyze your FoodPanda ordering habits")

# Handle OAuth callback
if "code" in st.query_params:
    try:
        # Get the authorization code from query parameters
        auth_code = st.query_params["code"]
        if isinstance(auth_code, list):  # Handle potential list return
            auth_code = auth_code[0]
            
        # Exchange the authorization code for tokens
        token_response = exchange_code_for_tokens(auth_code)
        
        # Store the credentials in session state
        st.session_state["credentials"] = {
            "token": token_response["access_token"],
            "refresh_token": token_response.get("refresh_token"),
            "token_uri": TOKEN_URL,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scopes": SCOPES,
        }
        
        # Clear the URL parameters and rerun
        st.query_params.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Authentication failed: {str(e)}")
        st.write("Debug info:")
        st.write(f"Query params: {st.query_params}")

# Check if user is already logged in
if st.session_state["credentials"]:
    st.success("✅ Connected to Gmail")
    credentials = google.oauth2.credentials.Credentials(**st.session_state["credentials"])
    
    days_to_analyze = st.slider("Select days to analyze", 30, 365, 365)
    
    if st.button("📊 Analyze My Food Expenses", type="primary"):
        with st.spinner(f"Analyzing your FoodPanda orders from the last {days_to_analyze} days..."):
            get_gmail_messages(credentials)
    
    # Add a small info text about data source
    st.info("💡 Data is fetched from your Gmail inbox using FoodPanda order confirmation emails", icon="ℹ️")

    if st.button("🔓 Disconnect Gmail", type="secondary"):
        del st.session_state["credentials"]
        st.rerun()

else:
    st.markdown("""
    ### 🔑 Connect Your Gmail
    To analyze your FoodPanda expenses, connect your Gmail account where you receive FoodPanda order confirmations.
    """)
    
    # Create login button with redirect inside the same tab
    auth_url = get_authorization_url()
    st.markdown(f'<a href="{auth_url}" target="_self"><button style="background-color:#FF2B85;color:white;padding:8px 16px;border:none;border-radius:4px;cursor:pointer;">🔐 Connect Gmail Account</button></a>', 
               unsafe_allow_html=True)
    
    # Add privacy note
    st.markdown("""
    ---
    ##### 🔒 Privacy Note
    This app only reads your FoodPanda order confirmation emails. No data is stored or shared.
    """)