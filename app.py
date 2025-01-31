import streamlit as st
import google.oauth2.credentials
import googleapiclient.discovery
import requests
from urllib.parse import urlencode
import pandas as pd
import base64
import datetime
import time
import re
import plotly.express as px

# Google OAuth Configuration
CLIENT_ID = st.secrets["google"]["client_id"]
CLIENT_SECRET = st.secrets["google"]["client_secret"]
REDIRECT_URI = "https://fasi96-foodpandaexpensetracker-app-j4oqdj.streamlit.app/"  
# REDIRECT_URI = "http://localhost:8501"
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
        "access_type": "offline",
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
    return response.json()

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
        data_dict = {'date': [], 'price': [], 'restaurant': []}

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

            try:
                price = float(price.replace(',', ''))
            except:
                price = 0
                
            # Extract restaurant name
            try:
                restaurant = re.search(r'Partner:\s*Name:\s*(.+)', decoded_content)
                restaurant = restaurant.group(1).strip() if restaurant else "Unknown"
            except:
                restaurant = "Unknown"
            
            data_dict['date'].append(date)
            data_dict['price'].append(price)
            data_dict['restaurant'].append(restaurant)
            
            # Update running totals and progress
            running_total += price
            processed_count += 1
            
            # Update progress indicators
            progress_counter.progress(i / total_messages, f"Processing email {i} of {total_messages}")
            current_total.metric("Running Total", f"PKR {running_total:,.2f}")
            emails_processed.metric("Emails Processed", f"{processed_count}/{total_messages}")

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
    data_dict = {'date': [], 'price': [], 'restaurant': []}
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

    # Restaurant Analysis
    st.subheader("🏪 Restaurant Analysis")
    
    # Add Time of Day Analysis
    st.subheader("⏰ Order Timing Analysis")
    
    # Extract hour from datetime and create a copy of relevant columns
    timing_df = df.copy()
    timing_df['hour'] = timing_df['date'].dt.hour
    timing_df['day_of_week'] = timing_df['date'].dt.day_name()
    
    # Create scatter plot of orders by time of day
    st.markdown("#### When Do You Order?")
    st.markdown("Each point represents an order. Hover over points to see details.")
    
    # Create scatter plot using plotly
    fig = px.scatter(
        timing_df,
        x='hour',
        y='price',
        color='day_of_week',
        hover_data={
            'price': ':.0f',
            'restaurant': True,
            'date': '|%Y-%m-%d %H:%M',
            'hour': False,
            'day_of_week': True
        },
        title='Orders by Time of Day',
        labels={
            'hour': 'Hour of Day', 
            'price': 'Order Amount (PKR)',
            'day_of_week': 'Day of Week'
        }
    )
    
    # Map the hours to new values (12 PM = 0, 1 PM = 1, ..., 11 AM = 23)
    timing_df['adjusted_hour'] = timing_df['hour'].apply(
        lambda x: (x - 12) % 24
    )
    
    # Create scatter plot with adjusted hours
    fig = px.scatter(
        timing_df,
        x='adjusted_hour',
        y='price',
        color='day_of_week',
        hover_data={
            'price': ':.0f',
            'restaurant': True,
            'date': '|%Y-%m-%d %H:%M',
            'hour': False,
            'day_of_week': True
        },
        title='Orders by Time of Day',
        labels={
            'adjusted_hour': 'Hour of Day', 
            'price': 'Order Amount (PKR)',
            'day_of_week': 'Day of Week'
        }
    )
    
    # Rearrange hours to start from noon (12 PM)
    hour_labels = [
        '12 PM', '1 PM', '2 PM', '3 PM', '4 PM', '5 PM',
        '6 PM', '7 PM', '8 PM', '9 PM', '10 PM', '11 PM',
        '12 AM', '1 AM', '2 AM', '3 AM', '4 AM', '5 AM',
        '6 AM', '7 AM', '8 AM', '9 AM', '10 AM', '11 AM'
    ]
    
    # Enhanced layout customization
    fig.update_layout(
        xaxis=dict(
            tickmode='array',
            ticktext=hour_labels,
            tickvals=list(range(24)),  # Simple 0-23 range
            tickangle=45,
            gridcolor='rgba(128, 128, 128, 0.2)',
            title_font=dict(size=14),
            tickfont=dict(size=10),
            dtick=1,
            range=[-0.5, 23.5],  # Show full range
            showgrid=True,
            zeroline=False,
        ),
        yaxis=dict(
            title_font=dict(size=14),
            gridcolor='rgba(128, 128, 128, 0.2)',
            zeroline=True,
            zerolinecolor='rgba(128, 128, 128, 0.2)',
        ),
        showlegend=True,
        legend_title_text='Day of Week',
        height=500,
        plot_bgcolor='white',
        margin=dict(t=50, l=50, r=50, b=50),
    )
    
    # Update marker properties
    fig.update_traces(
        marker=dict(
            size=10,
            opacity=0.7,
            line=dict(width=1, color='white'),
            symbol='circle'
        )
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Add time-based insights with more detailed analysis
    col1, col2, col3 = st.columns(3)
    
    with col1:
        peak_hour = timing_df.groupby('hour')['price'].count().idxmax()
        peak_hour_formatted = f"{peak_hour:02d}:00" if peak_hour < 12 else f"{peak_hour-12:02d}:00 PM" if peak_hour > 12 else "12:00 PM"
        st.metric("Most Common Order Time", peak_hour_formatted)
        
    with col2:
        peak_day = timing_df['day_of_week'].mode().iloc[0]
        st.metric("Most Common Day", peak_day)
        
    with col3:
        avg_order_time = timing_df['hour'].mean()
        avg_time_formatted = f"{int(avg_order_time):02d}:{int((avg_order_time % 1) * 60):02d}"
        st.metric("Average Order Time", avg_time_formatted)
    
    # Add time period analysis
    st.markdown("#### 🕒 Time Period Analysis")
    
    def get_time_period(hour):
        if 5 <= hour < 12:
            return "Morning (5 AM - 11:59 AM)"
        elif 12 <= hour < 17:
            return "Afternoon (12 PM - 4:59 PM)"
        elif 17 <= hour < 22:
            return "Evening (5 PM - 9:59 PM)"
        else:
            return "Late Night (10 PM - 4:59 AM)"
    
    timing_df['time_period'] = timing_df['hour'].apply(get_time_period)
    period_stats = timing_df.groupby('time_period').agg({
        'price': ['count', 'mean', 'sum']
    }).round(2)
    
    period_stats.columns = ['Number of Orders', 'Average Order (PKR)', 'Total Spent (PKR)']
    period_stats = period_stats.reindex([
        "Morning (5 AM - 11:59 AM)",
        "Afternoon (12 PM - 4:59 PM)",
        "Evening (5 PM - 9:59 PM)",
        "Late Night (10 PM - 4:59 AM)"
    ])
    
    st.dataframe(period_stats)
    
    # Add explanation of the visualization
    st.markdown("""
    #### 💡 Understanding Your Order Patterns
    - Each point represents an individual order
    - Colors show different days of the week
    - The height of each point shows the order amount
    - Hover over points to see the restaurant and exact time
    
    This can help you identify:
    - Your peak ordering hours
    - Which days you tend to order more
    - Whether you spend more during certain times
    - Your late-night ordering habits
    """)
    
    # Overall top restaurants
    restaurant_summary = df.groupby('restaurant').agg({
        'price': ['sum', 'count', 'mean']
    }).round(2)
    restaurant_summary.columns = ['Total Spent', 'Number of Orders', 'Average Order']
    restaurant_summary = restaurant_summary.sort_values('Number of Orders', ascending=False)
    
    # Display top 10 most ordered from restaurants
    st.markdown("#### Top 10 Most Ordered From Restaurants")
    top_restaurants = restaurant_summary.head(10)
    st.dataframe(top_restaurants)
    
    # Monthly top 3 restaurants
    st.markdown("#### Monthly Top 3 Restaurants")
    df['month_year'] = pd.to_datetime(df['date']).dt.strftime('%B %Y')
    
    # Sort months in descending order
    months = sorted(df['month_year'].unique(), key=lambda x: pd.to_datetime(x, format='%B %Y'), reverse=True)
    
    monthly_summary = []
    for month in months:
        month_data = df[df['month_year'] == month]
        top_3 = month_data.groupby('restaurant').agg({
            'price': 'sum',
            'restaurant': 'count'
        }).round(2)
        top_3.columns = ['Total Spent', 'Orders']
        top_3 = top_3.sort_values('Total Spent', ascending=False).head(3)
        
        # Format the top 3 restaurants as strings
        formatted_top_3 = [
            f"{restaurant} ({orders} - PKR {spent:,.0f})"
            for restaurant, (spent, orders) in top_3.iterrows()
        ]
        
        # Pad with empty strings if less than 3 restaurants
        while len(formatted_top_3) < 3:
            formatted_top_3.append("")
            
        monthly_summary.append({
            'Month': month,
            '1st': formatted_top_3[0],
            '2nd': formatted_top_3[1],
            '3rd': formatted_top_3[2]
        })
    
    monthly_summary_df = pd.DataFrame(monthly_summary)
    st.dataframe(monthly_summary_df, hide_index=True)

# Streamlit UI
st.set_page_config(
    page_title="FoodPanda Expense Tracker",
    page_icon="🐼"
)

# Check query parameters for page navigation
if "page" in st.query_params:
    current_page = st.query_params["page"]
else:
    current_page = "Home"

# Add a navigation menu in the sidebar
page = st.sidebar.radio("Navigation", ["Home", "Privacy Policy"], index=0 if current_page == "Home" else 1)

# Update URL when page changes
if page == "Privacy Policy" and current_page != "Privacy Policy":
    st.query_params["page"] = "Privacy Policy"
elif page == "Home" and current_page != "Home":
    st.query_params.clear()

if page == "Privacy Policy":
    st.title("Privacy Policy")
    st.markdown("""
    **Last Updated:** 2025-01-31

    Thank you for using the **FoodPanda Expense Tracker** (the "App"). Your privacy is important to us. This Privacy Policy explains how we collect, use, and protect your information when you use the App.

    ### **1. Information We Collect**
    The App accesses your Gmail account to retrieve FoodPanda order confirmation emails. Specifically, we collect the following information:
    - **Email Metadata**: The date and sender of FoodPanda order confirmation emails.
    - **Email Content**: The total order amount (price) extracted from the email body.

    We do **not** collect or store:
    - Your Gmail login credentials (email address or password).
    - Any personal information beyond what is necessary to analyze your FoodPanda expenses.
    - Any emails or data unrelated to FoodPanda order confirmations.

    ### **2. How We Use Your Information**
    The information we collect is used solely for the following purposes:
    - To analyze your FoodPanda expenses and provide insights into your spending habits.
    - To display your total spending, average order value, and monthly breakdowns within the App.

    We do **not**:
    - Share your data with third parties.
    - Use your data for advertising or marketing purposes.
    - Store your data permanently. All data is processed in real-time and discarded after your session ends.

    ### **3. Data Storage and Security**
    - **Temporary Storage**: The App processes your data in real-time and does not store it permanently. Once your session ends, all data is discarded.
    - **Security**: We use industry-standard security practices to protect your data during transmission and processing. However, no method of data transmission over the internet is 100% secure, and we cannot guarantee absolute security.

    ### **4. Google OAuth and Permissions**
    To access your Gmail account, the App uses Google OAuth 2.0 for authentication. This process grants the App limited access to your Gmail account, specifically:
    - **Read-Only Access**: The App can only read FoodPanda order confirmation emails. It cannot modify, delete, or send emails on your behalf.
    - **Scope Limitation**: The App requests the minimum necessary permissions (`https://www.googleapis.com/auth/gmail.readonly`) to function.

    You can revoke the App's access to your Gmail account at any time by visiting your [Google Account Security Settings](https://myaccount.google.com/permissions).

    ### **5. Third-Party Services**
    The App uses the following third-party services:
    - **Google APIs**: To authenticate your Gmail account and retrieve order confirmation emails.
    - **Streamlit Cloud**: To host the App and provide the user interface.

    These services have their own privacy policies, and we encourage you to review them:
    - [Google Privacy Policy](https://policies.google.com/privacy)
    - [Streamlit Privacy Policy](https://streamlit.io/privacy-policy)

    ### **6. Your Rights**
    You have the following rights regarding your data:
    - **Access**: You can request a summary of the data processed by the App during your session.
    - **Deletion**: Since the App does not store your data permanently, no deletion is necessary. You can revoke the App's access to your Gmail account at any time.
    - **Correction**: If you believe the App has processed incorrect data, please contact us.

    ### **7. Changes to This Privacy Policy**
    We may update this Privacy Policy from time to time. Any changes will be posted on this page, and the "Last Updated" date will be revised. We encourage you to review this policy periodically.

    ### **8. Contact Us**
    If you have any questions or concerns about this Privacy Policy or the App's data practices, please contact us at:
    - **Email:** [Your Email Address]
    - **Website:** [Your Website URL]

    ### **9. Consent**
    By using the **FoodPanda Expense Tracker**, you consent to the terms of this Privacy Policy.
    """)


else:  # Home page
    st.title("🐼 FoodPanda Expense Tracker")
    st.markdown("Track and analyze your FoodPanda ordering habits")

    # Handle OAuth callback
    if "code" in st.query_params:
        try:
            auth_code = st.query_params["code"]
            if isinstance(auth_code, list):
                auth_code = auth_code[0]
            tokens = exchange_code_for_tokens(auth_code)
            st.session_state["credentials"] = {
                "token": tokens["access_token"],
                "refresh_token": tokens.get("refresh_token"),
                "token_uri": TOKEN_URL,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "scopes": SCOPES,
            }
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Authentication failed: {str(e)}")

    # Check if user is already logged in
    if st.session_state["credentials"]:
        st.success("✅ Connected to Gmail")
        credentials = google.oauth2.credentials.Credentials(**st.session_state["credentials"])
        
        days_to_analyze = st.slider("Select days to analyze", 30, 365, 365)
        
        if st.button("📊 Analyze My Food Expenses", type="primary"):
            with st.spinner(f"Analyzing your FoodPanda orders from the last {days_to_analyze} days..."):
                get_gmail_messages(credentials)
        
        if st.button("🔓 Disconnect Gmail", type="secondary"):
            del st.session_state["credentials"]
            st.rerun()

    else:
        st.markdown("""
        ### 🔑 Connect Your Gmail
        To analyze your FoodPanda expenses, connect your Gmail account where you receive FoodPanda order confirmations.
        """)
        
        auth_url = get_authorization_url()
        st.markdown(f'<a href="{auth_url}" target="_blank"><button style="background-color:#FF2B85;color:white;padding:8px 16px;border:none;border-radius:4px;cursor:pointer;">🔐 Connect Gmail Account</button></a>', 
                unsafe_allow_html=True)
        
        st.markdown("""
        ---
        ##### 🔒 Privacy Note
        This app only reads your FoodPanda order confirmation emails. No data is stored or shared.
        """)