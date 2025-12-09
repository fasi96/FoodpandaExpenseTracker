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
import numpy as np
import os
import plotly.graph_objects as go

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
                restaurant = restaurant.group(1).strip() if restaurant else "Panda Mart"
            except:
                restaurant = "Panda Mart"
            
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

def save_to_csv(data_dict):
    """Save order data to a CSV file."""
    try:
        df = pd.DataFrame(data_dict)
        df.to_csv('foodpanda_orders.csv', index=False)
        st.success("✅ Order data saved successfully!")
    except Exception as e:
        st.error(f"Error saving data: {str(e)}")

def load_from_csv():
    """Load order data from CSV file if it exists."""
    try:
        if os.path.exists('foodpanda_orders.csv'):
            df = pd.read_csv('foodpanda_orders.csv')
            return {
                'date': df['date'].tolist(),
                'price': df['price'].tolist(),
                'restaurant': df['restaurant'].tolist()
            }
        return None
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
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
    
    # Convert to DataFrame and process dates
    df = pd.DataFrame(data_dict)
    df['date'] = pd.to_datetime(df['date'])
    
    # Calculate date range for display
    latest_order = df['date'].max()
    earliest_order = df['date'].min()
    date_range = f"{earliest_order.strftime('%B %d, %Y')} - {latest_order.strftime('%B %d, %Y')}"
    
    # Display header
    st.markdown("## 📊 Analysis Results")
    st.markdown(f"### 📅 Period: {date_range}")
    
    # Calculate key metrics
    total_spent = df['price'].sum()
    total_orders = len(df)
    avg_order = total_spent / total_orders if total_orders > 0 else 0
    months_diff = (latest_order.year - earliest_order.year) * 12 + (latest_order.month - earliest_order.month) + 1
    monthly_average = total_spent / months_diff if months_diff > 0 else 0
    
    # Calculate daily average
    total_days = (latest_order - earliest_order).days + 1
    daily_average = total_spent / total_days if total_days > 0 else 0
    
    # Display metrics in a container
    with st.container():
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("💰 Total Spent", f"PKR {total_spent:,.2f}")
            st.metric("📦 Total Orders", f"{total_orders:,}")
        with col2:
            st.metric("📊 Average Order", f"PKR {avg_order:,.2f}")
            st.metric("📅 Monthly Average", f"PKR {monthly_average:,.2f}")
        with col3:
            st.metric("📆 Daily Average", f"PKR {daily_average:,.2f}")
    
    # Display Hero Section
    display_hero_section(df)
    
    # Display Insights Section
    st.markdown("### 💡 Key Insights")
    insights = generate_insights(df, total_spent, total_orders, avg_order)
    
    # Display insights in rows of 3
    for i in range(0, len(insights), 3):
        cols = st.columns(3)
        for j, col in enumerate(cols):
            if i + j < len(insights):
                insight = insights[i + j]
                with col:
                    st.markdown(f"""
                        <div class="insight-card">
                            <div class="insight-icon">{insight['icon']}</div>
                            <div class="insight-title">{insight['title']}</div>
                            <div class="insight-description">{insight['description']}</div>
                        </div>
                    """, unsafe_allow_html=True)
    
    # Display Current Month Section
    st.markdown("### 📍 Current Month Overview")
    
    # Calculate current month data
    current_month = pd.Timestamp.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if df['date'].dt.tz is not None:
        current_month = current_month.tz_localize(df['date'].dt.tz)
    df_current = df[df['date'] >= current_month]
    
    current_month_spending = df_current['price'].sum()
    current_month_orders = len(df_current)
    current_month_avg = current_month_spending / current_month_orders if current_month_orders > 0 else 0
    
    # Calculate days
    now = pd.Timestamp.now()
    days_elapsed = now.day
    next_month = (now.replace(day=1) + pd.Timedelta(days=32)).replace(day=1)
    last_day_of_month = (next_month - pd.Timedelta(days=1)).day
    days_remaining = last_day_of_month - days_elapsed
    
    # Calculate daily rate
    daily_rate = current_month_spending / days_elapsed if days_elapsed > 0 else 0
    
    # Display current month header (compact)
    st.markdown(f"""
        <div class="current-month-header">
            {now.strftime('%B %Y')}
        </div>
    """, unsafe_allow_html=True)
    
    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("💸 Spent This Month", f"PKR {current_month_spending:,.0f}")
    with col2:
        st.metric("📦 Orders", f"{current_month_orders}")
    with col3:
        st.metric("📊 Avg per Order", f"PKR {current_month_avg:,.0f}")
    with col4:
        st.metric("📅 Daily Rate", f"PKR {daily_rate:,.0f}")
    
    # Progress through month
    progress_pct = (days_elapsed / last_day_of_month) * 100
    st.caption(f"📆 **Day {days_elapsed} of {last_day_of_month}** ({progress_pct:.0f}% through the month · {days_remaining} days remaining)")
    
    st.markdown("---")
    
    # Create tabs for different analysis sections
    tab_wrapped, tab_diversity, tab_fun, tab1, tab2, tab3 = st.tabs(["🎁 Wrapped", "📊 Diversity", "💡 Fun Facts", "📈 Spending Trends", "⏰ Time Analysis", "🏪 Restaurant Analysis"])
    
    with tab_wrapped:
        st.markdown("### 🎁 Your Foodpanda Wrapped")
        st.markdown("Experience your food journey like never before!")
        display_wrapped_experience(df)
    
    with tab_diversity:
        st.markdown("### 🎯 Restaurant Diversity Score")
        st.markdown("Are you an explorer or a loyalist?")
        display_diversity_section(df)
    
    with tab_fun:
        display_fun_comparisons(df)
    
    with tab1:
        st.markdown("### Monthly Spending Trend")
        
        # Create monthly aggregation
        monthly_data = df.groupby(df['date'].dt.to_period('M'))\
            .agg({'price': 'sum'})\
            .reset_index()
        monthly_data['date'] = monthly_data['date'].dt.to_timestamp()
        monthly_data = monthly_data.sort_values('date')

        # Create the bar chart
        fig = create_monthly_spending_chart(monthly_data, 0)
        st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        st.markdown("### Order Timing Analysis")
        
        # Extract hour from datetime
        timing_df = df.copy()
        timing_df['hour'] = timing_df['date'].dt.hour
        timing_df['day_of_week'] = timing_df['date'].dt.day_name()
        
        st.markdown("##### 24-Hour Order Distribution")
        
        # Calculate time period statistics
        def get_time_period(hour):
            if 5 <= hour < 12:
                return 'Morning'
            elif 12 <= hour < 17:
                return 'Afternoon'
            elif 17 <= hour < 22:
                return 'Evening'
            else:
                return 'Late Night'

        timing_df['time_period'] = timing_df['hour'].apply(get_time_period)
        period_stats = timing_df.groupby('time_period').agg({
            'price': ['sum', 'mean']
        }).round(2)

        # Prepare data for radial chart
        hour_counts = timing_df['hour'].value_counts().sort_index()
        
        # Create the radial chart
        fig_radial = go.Figure()
        
        max_value = max(hour_counts.values)
        separators = [75, 180, 255, 330]
        for angle in separators:
            fig_radial.add_trace(go.Scatterpolar(
                r=[max_value * 1.4, max_value * 1.8],
                theta=[angle, angle],
                mode='lines',
                line=dict(color='rgba(255, 255, 255, 0.5)', width=1),
                hoverinfo='skip',
                showlegend=False
            ))
        
        fig_radial.add_trace(go.Barpolar(
            r=hour_counts.values,
            theta=hour_counts.index.map(lambda x: x * 15),
            width=15,
            marker=dict(
                color=hour_counts.values,
                colorscale=[[0, '#FFE5EE'], [1, '#FF2B85']],
                showscale=False
            ),
            hovertemplate="Hour: %{customdata}<br>Orders: %{r}<extra></extra>",
            customdata=[f'{i:02d}:00' for i in hour_counts.index]
        ))

        most_common_hour = timing_df['hour'].mode().iloc[0]
        most_common_hour_formatted = f"{most_common_hour:02d}:00"

        fig_radial.update_layout(
            polar=dict(
                radialaxis=dict(showticklabels=False, ticks='', range=[0, max_value ]),
                angularaxis=dict(
                    tickmode='array',
                    ticktext=['12 AM', '3 AM', '6 AM', '9 AM', '12 PM', '3 PM', '6 PM', '9 PM'],
                    tickvals=[0, 45, 90, 135, 180, 225, 270, 315],
                    direction='clockwise',
                    rotation=90,
                ),
                domain=dict(x=[0.15, 0.85], y=[0.15, 0.85])
            ),
            height=600,
            margin=dict(t=100, b=80, l=50, r=50),
            showlegend=False,
            title=dict(
                text=f"🕒 Peak Order Time: {most_common_hour_formatted}",
                y=0.95,
                x=0.5,
                xanchor='center',
                yanchor='top',
                font=dict(size=16, color='#FF2B85')
            ),
            annotations=[
                dict(
                    x=0.5, y=1.07,
                    text=f"🌅 Morning (5-11:59 AM)<br><b>Total: {period_stats.loc['Morning', ('price', 'sum')]/1000:.1f}K</b> | Avg: {period_stats.loc['Morning', ('price', 'mean')]/1000:.1f}K",
                    showarrow=False,
                    font=dict(size=11),
                    align='center',
                    xref='paper',
                    yref='paper'
                ),
                dict(
                    x=1.07, y=0.5,
                    text=f"🌞 Afternoon (12-4:59 PM)<br><b>Total: {period_stats.loc['Afternoon', ('price', 'sum')]/1000:.1f}K</b> | Avg: {period_stats.loc['Afternoon', ('price', 'mean')]/1000:.1f}K",
                    showarrow=False,
                    font=dict(size=11),
                    align='left',
                    xref='paper',
                    yref='paper'
                ),
                dict(
                    x=0.5, y=-0.07,
                    text=f"🌆 Evening (5-9:59 PM)<br><b>Total: {period_stats.loc['Evening', ('price', 'sum')]/1000:.1f}K</b> | Avg: {period_stats.loc['Evening', ('price', 'mean')]/1000:.1f}K",
                    showarrow=False,
                    font=dict(size=11),
                    align='center',
                    xref='paper',
                    yref='paper'
                ),
                dict(
                    x=-0.07, y=0.5,
                    text=f"🌙 Late Night (10 PM - 4:59 AM)<br><b>Total: {period_stats.loc['Late Night', ('price', 'sum')]/1000:.1f}K</b> | Avg: {period_stats.loc['Late Night', ('price', 'mean')]/1000:.1f}K",
                    showarrow=False,
                    font=dict(size=11),
                    align='right',
                    xref='paper',
                    yref='paper'
                )
            ]
        )
        
        st.plotly_chart(fig_radial, use_container_width=True)

        st.caption("""
        📌 **K** = Thousands (PKR)  
        🛒 **Total** = Total spending in this time range  
        📊 **Avg** = Average order amount  
        """)
    
    with tab3:
        st.markdown("### Restaurant Analysis")
        
        # Overall top restaurants
        restaurant_summary = df.groupby('restaurant').agg({
            'price': ['sum', 'count', 'mean']
        }).round(2)
        restaurant_summary.columns = ['Total Spent', 'Number of Orders', 'Average Order']
        restaurant_summary = restaurant_summary.sort_values('Number of Orders', ascending=False)
        
        # Display top 10 most ordered from restaurants
        st.markdown("#### Top 10 Most Ordered From Restaurants")
        top_restaurants = restaurant_summary.head(10)
        st.dataframe(top_restaurants, use_container_width=True)
        
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
            
            formatted_top_3 = [
                f"{restaurant} ({orders} - PKR {spent:,.0f})"
                for restaurant, (spent, orders) in top_3.iterrows()
            ]
            
            while len(formatted_top_3) < 3:
                formatted_top_3.append("")
                
            monthly_summary.append({
                'Month': month,
                '1st': formatted_top_3[0],
                '2nd': formatted_top_3[1],
                '3rd': formatted_top_3[2]
            })
        
        monthly_summary_df = pd.DataFrame(monthly_summary)
        st.dataframe(monthly_summary_df, hide_index=True, use_container_width=True)

def generate_insights(df, total_spent, total_orders, avg_order):
    """Generate intelligent insights from the order data."""
    insights = []
    
    # Insight 1: Top 3 Restaurants
    if not df.empty:
        top_restaurants = df.groupby('restaurant')['restaurant'].count().sort_values(ascending=False).head(3)
        
        # Format top 3 restaurants
        top_3_text = []
        medals = ['🥇', '🥈', '🥉']
        for i, (restaurant, count) in enumerate(top_restaurants.items()):
            if i < 3:
                top_3_text.append(f"{medals[i]} **{restaurant}** ({int(count)})")
        
        insights.append({
            'icon': '🏆',
            'title': 'Top 3 Restaurants',
            'description': "<br>".join(top_3_text)
        })
    
    # Insight 2: Most Ordered Day of Week
    df_with_day = df.copy()
    df_with_day['day_of_week'] = df_with_day['date'].dt.day_name()
    most_common_day = df_with_day['day_of_week'].mode().iloc[0]
    day_count = (df_with_day['day_of_week'] == most_common_day).sum()
    insights.append({
        'icon': '📅',
        'title': 'Favorite Order Day',
        'description': f"**{most_common_day}** is your go-to day with {day_count} orders!"
    })
    
    # Insight 3: Most Expensive Order
    max_order = df['price'].max()
    max_restaurant = df[df['price'] == max_order]['restaurant'].iloc[0]
    insights.append({
        'icon': '💎',
        'title': 'Biggest Splurge',
        'description': f"PKR {max_order:,.0f} from **{max_restaurant}** was your priciest order!"
    })
    
    # Insight 4: Peak Ordering Time
    df_with_hour = df.copy()
    df_with_hour['hour'] = df_with_hour['date'].dt.hour
    peak_hour = df_with_hour['hour'].mode().iloc[0]
    
    # Format time period
    if 5 <= peak_hour < 12:
        time_period = "Morning"
        emoji = "🌅"
    elif 12 <= peak_hour < 17:
        time_period = "Afternoon"
        emoji = "🌞"
    elif 17 <= peak_hour < 22:
        time_period = "Evening"
        emoji = "🌆"
    else:
        time_period = "Late Night"
        emoji = "🌙"
    
    insights.append({
        'icon': emoji,
        'title': 'Peak Order Time',
        'description': f"Most orders around **{peak_hour:02d}:00** - You're a {time_period} orderer!"
    })
    
    # Insight 5: Spending Trend (last 3 months)
    df_recent = df.copy()
    df_recent['month'] = df_recent['date'].dt.to_period('M')
    monthly_spending = df_recent.groupby('month')['price'].sum().sort_index()
    
    if len(monthly_spending) >= 2:
        recent_avg = monthly_spending.tail(2).mean()
        older_avg = monthly_spending.head(max(1, len(monthly_spending) - 2)).mean()
        
        if recent_avg > older_avg * 1.1:
            trend_icon = "📈"
            trend_text = "increasing"
            pct_change = ((recent_avg - older_avg) / older_avg) * 100
            insights.append({
                'icon': trend_icon,
                'title': 'Spending Trend',
                'description': f"Your spending is **{trend_text}** by {pct_change:.0f}% lately!"
            })
        elif recent_avg < older_avg * 0.9:
            trend_icon = "📉"
            trend_text = "decreasing"
            pct_change = ((older_avg - recent_avg) / older_avg) * 100
            insights.append({
                'icon': trend_icon,
                'title': 'Spending Trend',
                'description': f"Great job! Spending is **{trend_text}** by {pct_change:.0f}%!"
            })
    
    # Insight 6: Average Order Value Insight
    if avg_order > 1500:
        insights.append({
            'icon': '🍽️',
            'title': 'Premium Orders',
            'description': f"Your average order of PKR {avg_order:,.0f} is above typical!"
        })
    elif avg_order < 800:
        insights.append({
            'icon': '💰',
            'title': 'Budget-Friendly',
            'description': f"You keep it economical with PKR {avg_order:,.0f} average orders!"
        })
    
    # Insight 7: Restaurant by Time of Day
    df_time = df.copy()
    df_time['hour'] = df_time['date'].dt.hour
    
    # Define time periods
    def get_time_period_for_insight(hour):
        if 5 <= hour < 12:
            return 'Morning'
        elif 12 <= hour < 17:
            return 'Afternoon'
        elif 17 <= hour < 22:
            return 'Evening'
        else:
            return 'Late Night'
    
    df_time['time_period'] = df_time['hour'].apply(get_time_period_for_insight)
    
    # Get most ordered restaurant for each time period
    time_restaurants = []
    time_emojis = {'Morning': '🌅', 'Afternoon': '🌞', 'Evening': '🌆', 'Late Night': '🌙'}
    
    for period in ['Morning', 'Afternoon', 'Evening', 'Late Night']:
        period_df = df_time[df_time['time_period'] == period]
        if not period_df.empty:
            top_rest = period_df.groupby('restaurant').size().sort_values(ascending=False)
            if len(top_rest) > 0:
                restaurant = top_rest.index[0]
                count = int(top_rest.iloc[0])
                time_restaurants.append(f"{time_emojis[period]} **{restaurant}** ({count})")
    
    if time_restaurants:
        insights.append({
            'icon': '⏰',
            'title': 'Time-Based Favorites',
            'description': "<br>".join(time_restaurants)
        })
    
    return insights  # Return all insights

def display_hero_section(df):
    """Display hero section spotlighting favorite restaurant."""
    if df.empty:
        return
    
    # Calculate favorite restaurant stats
    restaurant_stats = df.groupby('restaurant').agg({
        'price': ['sum', 'count']
    }).round(2)
    restaurant_stats.columns = ['total_spent', 'order_count']
    restaurant_stats = restaurant_stats.sort_values('order_count', ascending=False)
    
    if len(restaurant_stats) == 0:
        return
    
    # Get top restaurant
    fav_restaurant = restaurant_stats.index[0]
    fav_orders = int(restaurant_stats.iloc[0]['order_count'])
    fav_spent = restaurant_stats.iloc[0]['total_spent']
    
    # Calculate percentage
    total_orders = len(df)
    percentage = (fav_orders / total_orders * 100) if total_orders > 0 else 0
    
    # Choose emoji based on restaurant name
    if 'pizza' in fav_restaurant.lower():
        emoji = '🍕'
    elif 'burger' in fav_restaurant.lower() or 'bun' in fav_restaurant.lower():
        emoji = '🍔'
    elif 'panda mart' in fav_restaurant.lower():
        emoji = '🛒'
    elif 'chinese' in fav_restaurant.lower() or 'wok' in fav_restaurant.lower():
        emoji = '🥡'
    elif 'desi' in fav_restaurant.lower() or 'karahi' in fav_restaurant.lower():
        emoji = '🍛'
    elif 'cafe' in fav_restaurant.lower() or 'coffee' in fav_restaurant.lower():
        emoji = '☕'
    else:
        emoji = '⭐'
    
    # Display hero section
    st.markdown(f"""
        <div class="hero-section">
            <div class="hero-icon">{emoji}</div>
            <div class="hero-title">Your Go-To Spot: <span class="hero-restaurant">{fav_restaurant}</span></div>
            <div class="hero-stats">
                <span class="hero-stat-number">{fav_orders}</span> orders · 
                <span class="hero-stat-number">PKR {fav_spent:,.0f}</span> spent
            </div>
            <div class="hero-message">
                🎯 <strong>{fav_restaurant}</strong> is your #1 choice, representing <strong>{percentage:.1f}%</strong> of all your orders!
            </div>
        </div>
    """, unsafe_allow_html=True)

def create_monthly_spending_chart(monthly_data, monthly_budget=0):
    """Create and return the monthly spending trend chart."""
    fig = go.Figure()
    
    # Add bars
    fig.add_trace(go.Bar(
        x=monthly_data['date'],
        y=monthly_data['price'],
        marker_color='#FF2B85',
        opacity=0.7,
        hovertemplate=(
            "<b>%{x|%B %Y}</b><br>" +
            "PKR %{y:,.0f}<br>" +
            "<extra></extra>"
        )
    ))
    
    # Add budget line if budget is set
    if monthly_budget > 0:
        fig.add_trace(go.Scatter(
            x=monthly_data['date'],
            y=[monthly_budget] * len(monthly_data),
            mode='lines',
            name='Budget',
            line=dict(color='green', width=2, dash='dash'),
            hovertemplate="Budget: PKR %{y:,.0f}<extra></extra>"
        ))
    
    # Add price labels in thousands above bars
    for i, row in monthly_data.iterrows():
        fig.add_annotation(
            x=row['date'],
            y=row['price'],
            text=f"{row['price']/1000:.1f}K",
            showarrow=False,
            yshift=10,
            font=dict(size=10, color='#FF2B85')
        )
    
    # Update layout
    fig.update_layout(
        showlegend=True if monthly_budget > 0 else False,
        plot_bgcolor='white',
        height=400,
        xaxis=dict(
            title="",
            tickformat="%b %Y",
            tickangle=45,
            gridcolor='rgba(128, 128, 128, 0.2)',
            showline=True,
            linewidth=1,
            linecolor='rgba(128, 128, 128, 0.2)',
            dtick="M1",
            tickmode='linear',
        ),
        yaxis=dict(
            title="Amount (PKR)",
            gridcolor='rgba(128, 128, 128, 0.2)',
            showline=True,
            linewidth=1,
            linecolor='rgba(128, 128, 128, 0.2)'
        ),
        margin=dict(l=20, r=20, t=40, b=40),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    return fig

def create_time_analysis_chart(timing_df, period_stats):
    """Create and return the time analysis radial chart."""
    hour_counts = timing_df['hour'].value_counts().sort_index()
    fig_radial = go.Figure()
    
    max_value = max(hour_counts.values)
    separators = [75, 180, 255, 330]
    
    # Add separator lines
    for angle in separators:
        fig_radial.add_trace(go.Scatterpolar(
            r=[max_value * 1.4, max_value * 1.8],
            theta=[angle, angle],
            mode='lines',
            line=dict(color='rgba(255, 255, 255, 0.5)', width=1),
            hoverinfo='skip',
            showlegend=False
        ))
    
    # Add radial bars
    fig_radial.add_trace(go.Barpolar(
        r=hour_counts.values,
        theta=hour_counts.index.map(lambda x: x * 15),
        width=15,
        marker=dict(
            color=hour_counts.values,
            colorscale=[[0, '#FFE5EE'], [1, '#FF2B85']],
            showscale=False
        ),
        hovertemplate="Hour: %{customdata}<br>Orders: %{r}<extra></extra>",
        customdata=[f'{i:02d}:00' for i in hour_counts.index]
    ))
    
    most_common_hour = timing_df['hour'].mode().iloc[0]
    most_common_hour_formatted = f"{most_common_hour:02d}:00"
    
    # Update layout with annotations
    fig_radial.update_layout(
        polar=dict(
            radialaxis=dict(showticklabels=False, ticks='', range=[0, max_value]),
            angularaxis=dict(
                tickmode='array',
                ticktext=['12 AM', '3 AM', '6 AM', '9 AM', '12 PM', '3 PM', '6 PM', '9 PM'],
                tickvals=[0, 45, 90, 135, 180, 225, 270, 315],
                direction='clockwise',
                rotation=90,
            ),
            domain=dict(x=[0.15, 0.85], y=[0.15, 0.85])
        ),
        height=500,
        margin=dict(t=100, b=80, l=50, r=50),
        showlegend=False,
        title=dict(
            text=f"🕒 Peak Order Time: {most_common_hour_formatted}",
            y=0.95,
            x=0.5,
            xanchor='center',
            yanchor='top',
            font=dict(size=16, color='#FF2B85')
        ),
        annotations=[
            dict(
                x=0.5, y=1.15,
                text=f"🌅 Morning (5-11:59 AM)<br><b>Total: {period_stats.loc['Morning', ('price', 'sum')]/1000:.1f}K</b> | Avg: {period_stats.loc['Morning', ('price', 'mean')]/1000:.1f}K",
                showarrow=False,
                font=dict(size=11),
                align='center',
                xref='paper',
                yref='paper'
            ),
            dict(
                x=1.1, y=0.5,
                text=f"🌞 Afternoon (12-4:59 PM)<br><b>Total: {period_stats.loc['Afternoon', ('price', 'sum')]/1000:.1f}K</b> | Avg: {period_stats.loc['Afternoon', ('price', 'mean')]/1000:.1f}K",
                showarrow=False,
                font=dict(size=11),
                align='left',
                xref='paper',
                yref='paper'
            ),
            dict(
                x=0.5, y=-0.15,
                text=f"🌆 Evening (5-9:59 PM)<br><b>Total: {period_stats.loc['Evening', ('price', 'sum')]/1000:.1f}K</b> | Avg: {period_stats.loc['Evening', ('price', 'mean')]/1000:.1f}K",
                showarrow=False,
                font=dict(size=11),
                align='center',
                xref='paper',
                yref='paper'
            ),
            dict(
                x=-0.1, y=0.5,
                text=f"🌙 Late Night (10 PM - 4:59 AM)<br><b>Total: {period_stats.loc['Late Night', ('price', 'sum')]/1000:.1f}K</b> | Avg: {period_stats.loc['Late Night', ('price', 'mean')]/1000:.1f}K",
                showarrow=False,
                font=dict(size=11),
                align='right',
                xref='paper',
                yref='paper'
            )
        ]
    )
    
    return fig_radial

def display_metrics(df):
    """Display the metrics section with total spent, orders, and average."""
    total_spent = df['price'].sum()
    total_orders = len(df)
    avg_order = total_spent / total_orders if total_orders > 0 else 0
    
    col1, col2, col3 = st.columns([1.5, 0.8, 1])
    with col1:
        st.metric("Total Spent", f"PKR {total_spent:,.2f}")
    with col2:
        st.metric("Total Orders", str(total_orders))
    with col3:
        st.metric("Average Order", f"PKR {avg_order:,.2f}")

def get_time_period(hour):
    """Determine the time period based on hour."""
    if 5 <= hour < 12:
        return 'Morning'
    elif 12 <= hour < 17:
        return 'Afternoon'
    elif 17 <= hour < 22:
        return 'Evening'
    else:
        return 'Late Night'

def prepare_time_analysis_data(df):
    """Prepare data for time analysis."""
    timing_df = df.copy()
    timing_df['hour'] = timing_df['date'].dt.hour
    timing_df['day_of_week'] = timing_df['date'].dt.day_name()
    timing_df['time_period'] = timing_df['hour'].apply(get_time_period)
    
    period_stats = timing_df.groupby('time_period').agg({
        'price': ['sum', 'mean']
    }).round(2)
    
    return timing_df, period_stats

def calculate_diversity_score(df):
    """Calculate restaurant diversity score and return personality insights."""
    total_orders = len(df)
    unique_restaurants = df['restaurant'].nunique()
    
    # Diversity ratio (0-100)
    diversity_ratio = (unique_restaurants / total_orders) * 100 if total_orders > 0 else 0
    
    # Get top 3 restaurants order percentage
    top_restaurants = df['restaurant'].value_counts().head(3)
    top_3_percentage = (top_restaurants.sum() / total_orders) * 100 if total_orders > 0 else 0
    
    # Determine personality
    if diversity_ratio >= 40:
        personality = "Adventurous Explorer"
        personality_emoji = "🌍"
        personality_desc = "You love trying new places! Your taste buds are always on an adventure."
    elif diversity_ratio >= 20:
        personality = "Balanced Foodie"
        personality_emoji = "⚖️"
        personality_desc = "You've found the sweet spot between loyalty and discovery."
    else:
        personality = "Loyal Regular"
        personality_emoji = "🏠"
        personality_desc = "You know what you like and stick to it. Your favorite spots love you!"
    
    # Check for loyalty badge
    is_super_loyal = top_3_percentage >= 50
    
    return {
        'diversity_ratio': diversity_ratio,
        'unique_restaurants': unique_restaurants,
        'total_orders': total_orders,
        'personality': personality,
        'personality_emoji': personality_emoji,
        'personality_desc': personality_desc,
        'top_3_percentage': top_3_percentage,
        'is_super_loyal': is_super_loyal,
        'top_restaurants': top_restaurants
    }

def generate_fun_comparisons(total_spent, total_orders, df):
    """Generate fun spending comparisons with PKR-relevant equivalents."""
    comparisons = []
    
    # Calculate days in period
    date_range = (df['date'].max() - df['date'].min()).days + 1
    orders_frequency = date_range / total_orders if total_orders > 0 else 0
    
    # PKR-based comparisons (Pakistani context)
    chai_price = 50  # Average chai price
    biryani_price = 350  # Average biryani plate
    movie_ticket = 800  # Average cinema ticket
    petrol_liter = 280  # Petrol per liter
    pizza_price = 1500  # Medium pizza
    iphone_price = 450000  # iPhone 15
    bike_price = 250000  # Average 70cc bike
    
    # Chai comparison
    chai_count = int(total_spent / chai_price)
    comparisons.append({
        'emoji': '☕',
        'title': 'Chai Equivalent',
        'value': f'{chai_count:,}',
        'unit': 'cups of chai',
        'subtitle': f"That's {chai_count // 30} months of daily chai!"
    })
    
    # Biryani comparison
    biryani_count = int(total_spent / biryani_price)
    comparisons.append({
        'emoji': '🍚',
        'title': 'Biryani Counter',
        'value': f'{biryani_count:,}',
        'unit': 'plates of biryani',
        'subtitle': f"Enough to feed a cricket team {biryani_count // 11} times!"
    })
    
    # Movie tickets
    movie_count = int(total_spent / movie_ticket)
    comparisons.append({
        'emoji': '🎬',
        'title': 'Cinema Trips',
        'value': f'{movie_count:,}',
        'unit': 'movie tickets',
        'subtitle': f"You could've watched every Marvel movie {movie_count // 35} times!"
    })
    
    # Petrol comparison
    petrol_liters = int(total_spent / petrol_liter)
    km_distance = petrol_liters * 15  # Assuming 15km per liter
    comparisons.append({
        'emoji': '⛽',
        'title': 'Fuel Fund',
        'value': f'{petrol_liters:,}',
        'unit': 'liters of petrol',
        'subtitle': f"Drive {km_distance:,} km - that's Karachi to Islamabad {km_distance // 1400} times!"
    })
    
    # Order frequency
    comparisons.append({
        'emoji': '📅',
        'title': 'Order Rhythm',
        'value': f'Every {orders_frequency:.1f}',
        'unit': 'days',
        'subtitle': f"You ordered {total_orders} times in {date_range} days!"
    })
    
    # Fun percentage comparisons
    iphone_percent = (total_spent / iphone_price) * 100
    if iphone_percent >= 100:
        iphone_count = total_spent // iphone_price
        comparisons.append({
            'emoji': '📱',
            'title': 'iPhone Fund',
            'value': f'{int(iphone_count)}',
            'unit': 'iPhones worth',
            'subtitle': f"Your food spending = {int(iphone_count)} iPhone(s)!"
        })
    else:
        comparisons.append({
            'emoji': '📱',
            'title': 'iPhone Progress',
            'value': f'{iphone_percent:.0f}%',
            'unit': 'of an iPhone',
            'subtitle': f"PKR {iphone_price - total_spent:,.0f} more to buy an iPhone!"
        })
    
    return comparisons

def get_wrapped_slides_data(df):
    """Generate data for the wrapped story slides."""
    total_orders = len(df)
    total_spent = df['price'].sum()
    
    # Date calculations
    date_range = (df['date'].max() - df['date'].min()).days + 1
    orders_frequency = date_range / total_orders if total_orders > 0 else 0
    
    # Top restaurant
    top_restaurant = df['restaurant'].value_counts().index[0]
    top_restaurant_orders = df['restaurant'].value_counts().iloc[0]
    top_restaurant_spent = df[df['restaurant'] == top_restaurant]['price'].sum()
    
    # Peak hour
    df_copy = df.copy()
    df_copy['hour'] = df_copy['date'].dt.hour
    peak_hour = df_copy['hour'].mode().iloc[0]
    
    # Time personality
    if 5 <= peak_hour < 12:
        time_personality = "Early Bird Foodie 🌅"
        time_desc = "You fuel up early! Morning orders are your thing."
    elif 12 <= peak_hour < 17:
        time_personality = "Lunch Break Legend 🌞"
        time_desc = "Midday munchies hit you hard. Lunch is your prime time!"
    elif 17 <= peak_hour < 22:
        time_personality = "Evening Enthusiast 🌆"
        time_desc = "Dinner delivery is your specialty. Evening cravings rule!"
    else:
        time_personality = "Night Owl Foodie 🌙"
        time_desc = "Late night cravings? You own them!"
    
    # Get diversity data
    diversity_data = calculate_diversity_score(df)
    
    # Get comparisons
    comparisons = generate_fun_comparisons(total_spent, total_orders, df)
    
    return {
        'total_orders': total_orders,
        'total_spent': total_spent,
        'date_range': date_range,
        'orders_frequency': orders_frequency,
        'top_restaurant': top_restaurant,
        'top_restaurant_orders': top_restaurant_orders,
        'top_restaurant_spent': top_restaurant_spent,
        'peak_hour': peak_hour,
        'time_personality': time_personality,
        'time_desc': time_desc,
        'diversity_data': diversity_data,
        'comparisons': comparisons,
        'earliest_date': df['date'].min().strftime('%B %d, %Y'),
        'latest_date': df['date'].max().strftime('%B %d, %Y')
    }

def display_wrapped_experience(df):
    """Display the Spotify Wrapped-style story experience."""
    
    # Initialize slide state
    if 'wrapped_slide' not in st.session_state:
        st.session_state.wrapped_slide = 0
    
    # Get wrapped data
    data = get_wrapped_slides_data(df)
    
    # Total slides
    total_slides = 5
    current_slide = st.session_state.wrapped_slide
    
    # Navigation
    col_prev, col_progress, col_next = st.columns([1, 3, 1])
    
    with col_prev:
        if st.button("◀ Back", disabled=current_slide == 0, key="wrapped_prev"):
            st.session_state.wrapped_slide -= 1
            st.rerun()
    
    with col_progress:
        # Progress dots
        dots = ""
        for i in range(total_slides):
            if i == current_slide:
                dots += "● "
            else:
                dots += "○ "
        st.markdown(f"<div style='text-align: center; font-size: 1.5rem; letter-spacing: 8px;'>{dots}</div>", unsafe_allow_html=True)
    
    with col_next:
        if current_slide < total_slides - 1:
            if st.button("Next ▶", key="wrapped_next"):
                st.session_state.wrapped_slide += 1
                st.rerun()
        else:
            if st.button("🔄 Restart", key="wrapped_restart"):
                st.session_state.wrapped_slide = 0
                st.rerun()
    
    # Display current slide
    if current_slide == 0:
        # Slide 1: Intro
        st.markdown(f"""
            <div class="wrapped-slide slide-intro">
                <div class="wrapped-year">🐼 Your Food Journey</div>
                <div class="wrapped-period">{data['earliest_date']} — {data['latest_date']}</div>
                <div class="wrapped-big-number">{data['total_orders']}</div>
                <div class="wrapped-label">orders delivered to your door</div>
                <div class="wrapped-subtitle">Let's unwrap your foodie story...</div>
            </div>
        """, unsafe_allow_html=True)
    
    elif current_slide == 1:
        # Slide 2: Top Restaurant
        st.markdown(f"""
            <div class="wrapped-slide slide-restaurant">
                <div class="wrapped-small-text">Your #1 spot was...</div>
                <div class="wrapped-restaurant-name">🏆 {data['top_restaurant']}</div>
                <div class="wrapped-stats-row">
                    <div class="wrapped-stat">
                        <span class="stat-number">{data['top_restaurant_orders']}</span>
                        <span class="stat-label">orders</span>
                    </div>
                    <div class="wrapped-stat">
                        <span class="stat-number">PKR {data['top_restaurant_spent']:,.0f}</span>
                        <span class="stat-label">spent</span>
                    </div>
                </div>
                <div class="wrapped-fun-fact">That's {(data['top_restaurant_orders']/data['total_orders']*100):.0f}% of all your orders!</div>
            </div>
        """, unsafe_allow_html=True)
    
    elif current_slide == 2:
        # Slide 3: Spending with fun context
        comparisons = data['comparisons'][:3]  # Get first 3 comparisons
        comparison_html = ""
        for comp in comparisons:
            comparison_html += f'<div class="comparison-item"><span class="comp-emoji">{comp["emoji"]}</span><span class="comp-value">{comp["value"]}</span><span class="comp-unit">{comp["unit"]}</span></div>'
        
        st.markdown(f'<div class="wrapped-slide slide-spending"><div class="wrapped-small-text">You spent a total of...</div><div class="wrapped-big-money">PKR {data["total_spent"]:,.0f}</div><div class="wrapped-equivalents"><div class="equiv-title">That\'s equivalent to:</div>{comparison_html}</div><div class="wrapped-frequency">📅 You ordered every {data["orders_frequency"]:.1f} days on average</div></div>', unsafe_allow_html=True)
    
    elif current_slide == 3:
        # Slide 4: Time personality
        st.markdown(f"""
            <div class="wrapped-slide slide-time">
                <div class="wrapped-small-text">Based on your ordering times...</div>
                <div class="wrapped-personality">{data['time_personality']}</div>
                <div class="wrapped-peak-time">
                    <div class="peak-label">Peak ordering hour</div>
                    <div class="peak-value">{data['peak_hour']:02d}:00</div>
                </div>
                <div class="wrapped-time-desc">{data['time_desc']}</div>
            </div>
        """, unsafe_allow_html=True)
    
    elif current_slide == 4:
        # Slide 5: Summary card
        diversity = data['diversity_data']
        st.markdown(f"""
            <div class="wrapped-slide slide-summary">
                <div class="summary-header">🐼 Your Foodpanda Wrapped</div>
                <div class="summary-grid">
                    <div class="summary-item">
                        <span class="summary-emoji">📦</span>
                        <span class="summary-value">{data['total_orders']}</span>
                        <span class="summary-label">Orders</span>
                    </div>
                    <div class="summary-item">
                        <span class="summary-emoji">💰</span>
                        <span class="summary-value">PKR {data['total_spent']/1000:.1f}K</span>
                        <span class="summary-label">Spent</span>
                    </div>
                    <div class="summary-item">
                        <span class="summary-emoji">🏆</span>
                        <span class="summary-value">{data['top_restaurant'][:15]}...</span>
                        <span class="summary-label">#1 Spot</span>
                    </div>
                    <div class="summary-item">
                        <span class="summary-emoji">🕐</span>
                        <span class="summary-value">{data['peak_hour']:02d}:00</span>
                        <span class="summary-label">Peak Hour</span>
                    </div>
                </div>
                <div class="summary-personality">
                    <span>{diversity['personality_emoji']}</span>
                    <span>{diversity['personality']}</span>
                </div>
                <div class="summary-footer">{data['earliest_date']} — {data['latest_date']}</div>
            </div>
        """, unsafe_allow_html=True)

def display_diversity_section(df):
    """Display the restaurant diversity score section."""
    diversity = calculate_diversity_score(df)
    
    st.markdown(f"""
        <div class="diversity-card">
            <div class="diversity-header">
                <span class="diversity-emoji">{diversity['personality_emoji']}</span>
                <span class="diversity-title">{diversity['personality']}</span>
            </div>
            <div class="diversity-score-container">
                <div class="diversity-score">{diversity['diversity_ratio']:.0f}%</div>
                <div class="diversity-score-label">Diversity Score</div>
            </div>
            <div class="diversity-desc">{diversity['personality_desc']}</div>
            <div class="diversity-stats">
                <div class="div-stat">
                    <span class="div-stat-value">{diversity['unique_restaurants']}</span>
                    <span class="div-stat-label">unique restaurants</span>
                </div>
                <div class="div-stat">
                    <span class="div-stat-value">{diversity['total_orders']}</span>
                    <span class="div-stat-label">total orders</span>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    # Loyalty badge
    if diversity['is_super_loyal']:
        st.markdown(f"""
            <div class="loyalty-badge">
                <span class="badge-emoji">🏅</span>
                <span class="badge-text">Super Loyal! {diversity['top_3_percentage']:.0f}% of orders from your top 3 restaurants</span>
            </div>
        """, unsafe_allow_html=True)
    
    # Top restaurants breakdown
    st.markdown("#### Your Top Restaurants")
    for i, (restaurant, count) in enumerate(diversity['top_restaurants'].items()):
        percentage = (count / diversity['total_orders']) * 100
        medal = ['🥇', '🥈', '🥉'][i] if i < 3 else '📍'
        st.markdown(f"""
            <div class="top-restaurant-bar">
                <span class="tr-medal">{medal}</span>
                <span class="tr-name">{restaurant}</span>
                <div class="tr-bar-container">
                    <div class="tr-bar" style="width: {percentage}%;"></div>
                </div>
                <span class="tr-count">{count} ({percentage:.0f}%)</span>
            </div>
        """, unsafe_allow_html=True)

def display_fun_comparisons(df):
    """Display the fun spending comparisons section."""
    total_spent = df['price'].sum()
    total_orders = len(df)
    comparisons = generate_fun_comparisons(total_spent, total_orders, df)
    
    st.markdown("### 💡 Your Spending In Perspective")
    
    # Display comparisons in a grid
    for i in range(0, len(comparisons), 3):
        cols = st.columns(3)
        for j, col in enumerate(cols):
            if i + j < len(comparisons):
                comp = comparisons[i + j]
                with col:
                    st.markdown(f"""
                        <div class="comparison-card">
                            <div class="comp-card-emoji">{comp['emoji']}</div>
                            <div class="comp-card-title">{comp['title']}</div>
                            <div class="comp-card-value">{comp['value']}</div>
                            <div class="comp-card-unit">{comp['unit']}</div>
                            <div class="comp-card-subtitle">{comp['subtitle']}</div>
                        </div>
                    """, unsafe_allow_html=True)

def display_analysis(df):
    """Display the full analysis for either preview or actual data."""
    # Display metrics in a container
    with st.container():
        total_spent = df['price'].sum()
        total_orders = len(df)
        avg_order = total_spent / total_orders if total_orders > 0 else 0
        
        # Calculate daily average
        date_range = (df['date'].max() - df['date'].min()).days + 1
        daily_average = total_spent / date_range if date_range > 0 else 0
        
        # Calculate monthly average (total months in period)
        months_diff = ((df['date'].max().year - df['date'].min().year) * 12 + 
                      (df['date'].max().month - df['date'].min().month) + 1)
        monthly_average = total_spent / months_diff if months_diff > 0 else 0
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("💰 Total Spent", f"PKR {total_spent:,.2f}")
            st.metric("📦 Total Orders", str(total_orders))
        with col2:
            st.metric("📊 Average Order", f"PKR {avg_order:,.2f}")
            st.metric("📅 Monthly Average", f"PKR {monthly_average:,.2f}")
        with col3:
            st.metric("📆 Daily Average", f"PKR {daily_average:,.2f}")
    
    # Display Hero Section
    display_hero_section(df)
    
    # Display Insights Section
    st.markdown("### 💡 Key Insights")
    insights = generate_insights(df, total_spent, total_orders, avg_order)
    
    # Display insights in rows of 3
    for i in range(0, len(insights), 3):
        cols = st.columns(3)
        for j, col in enumerate(cols):
            if i + j < len(insights):
                insight = insights[i + j]
                with col:
                    st.markdown(f"""
                        <div class="insight-card">
                            <div class="insight-icon">{insight['icon']}</div>
                            <div class="insight-title">{insight['title']}</div>
                            <div class="insight-description">{insight['description']}</div>
                        </div>
                    """, unsafe_allow_html=True)
    
    # Display Current Month Section
    st.markdown("### 📍 Current Month Overview")
    
    # Calculate current month data
    current_month = pd.Timestamp.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if df['date'].dt.tz is not None:
        current_month = current_month.tz_localize(df['date'].dt.tz)
    df_current = df[df['date'] >= current_month]
    
    current_month_spending = df_current['price'].sum()
    current_month_orders = len(df_current)
    current_month_avg = current_month_spending / current_month_orders if current_month_orders > 0 else 0
    
    # Calculate days
    now = pd.Timestamp.now()
    days_elapsed = now.day
    next_month = (now.replace(day=1) + pd.Timedelta(days=32)).replace(day=1)
    last_day_of_month = (next_month - pd.Timedelta(days=1)).day
    days_remaining = last_day_of_month - days_elapsed
    
    # Calculate daily rate
    daily_rate = current_month_spending / days_elapsed if days_elapsed > 0 else 0
    
    # Display current month header (compact)
    st.markdown(f"""
        <div class="current-month-header">
            {now.strftime('%B %Y')}
        </div>
    """, unsafe_allow_html=True)
    
    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("💸 Spent This Month", f"PKR {current_month_spending:,.0f}")
    with col2:
        st.metric("📦 Orders", f"{current_month_orders}")
    with col3:
        st.metric("📊 Avg per Order", f"PKR {current_month_avg:,.0f}")
    with col4:
        st.metric("📅 Daily Rate", f"PKR {daily_rate:,.0f}")
    
    # Progress through month
    progress_pct = (days_elapsed / last_day_of_month) * 100
    st.caption(f"📆 **Day {days_elapsed} of {last_day_of_month}** ({progress_pct:.0f}% through the month · {days_remaining} days remaining)")
    
    st.markdown("---")
    
    # Create tabs for different analysis sections
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🎁 Wrapped", "📊 Diversity Score", "💡 Fun Facts", "📈 Spending Trends", "⏰ Time Analysis"])
    
    with tab1:
        st.markdown("### 🎁 Your Foodpanda Wrapped")
        st.markdown("Experience your food journey like never before!")
        display_wrapped_experience(df)
    
    with tab2:
        st.markdown("### 🎯 Restaurant Diversity Score")
        st.markdown("Are you an explorer or a loyalist?")
        display_diversity_section(df)
    
    with tab3:
        display_fun_comparisons(df)
    
    with tab4:
        st.markdown("### Monthly Spending Trend")
        monthly_data = df.groupby(df['date'].dt.to_period('M'))\
            .agg({'price': 'sum'})\
            .reset_index()
        monthly_data['date'] = monthly_data['date'].dt.to_timestamp()
        monthly_data = monthly_data.sort_values('date')
        
        # Pass budget to chart for preview (use 0 as default)
        fig = create_monthly_spending_chart(monthly_data, 0)
        st.plotly_chart(fig, use_container_width=True)
    
    with tab5:
        st.markdown("### Order Timing Analysis")
        timing_df, period_stats = prepare_time_analysis_data(df)
        
        st.markdown("##### 24-Hour Order Distribution")
        fig_radial = create_time_analysis_chart(timing_df, period_stats)
        st.plotly_chart(fig_radial, use_container_width=True)
        
        st.caption("""
        📌 **K** = Thousands (PKR)  
        🛒 **Total** = Total spending in this time range  
        📊 **Avg** = Average order amount  
        """)

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
    If you have any questions or concerns about this Privacy Policy or the App's data practices, please contact us:
    - **LinkedIn:** [Muhammad Fasi-ur-Rehman](https://www.linkedin.com/in/muhammad-fasi-ur-rehman-5aaa7b131/)
    - **Email:** mofasiulrehman@gmail.com

    ### **9. Consent**
    By using the **FoodPanda Expense Tracker**, you consent to the terms of this Privacy Policy.
    """)


else:  # Home page
    st.title("🐼 FoodPanda Expense Tracker")
    st.markdown("Track and analyze your FoodPanda ordering habits")

    # Add developer contacts at the top
    st.markdown("""
    ##### 👨‍💻 Developer Contact
    - [LinkedIn](https://www.linkedin.com/in/muhammad-fasi-ur-rehman-5aaa7b131/)
    - Email: mofasiurrehman@gmail.com
    ---
    """)

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
        # Sign-in section
        st.markdown("""
        ### Connect Your Gmail
        To analyze your FoodPanda expenses, connect your Gmail account where you receive FoodPanda order confirmations.
        
        ⚠️ **Important Note About Google Security Warning**
        When connecting your Gmail account, you'll see a security warning from Google because this app isn't verified. This is normal for open-source projects. The app:
        - Only reads emails from "no-reply@mail.foodpanda.pk"
        - Cannot access any other emails or perform any actions
        - Doesn't store any of your data
        
        You can review our source code on [GitHub](https://github.com/fasi96/FoodpandaExpenseTracker) to verify the security and privacy of the app.
        """)
        
        auth_url = get_authorization_url()
        st.markdown(f'<a href="{auth_url}" target="_blank"><button style="background-color:#FF2B85;color:white;padding:8px 16px;border:none;border-radius:4px;cursor:pointer;">🔐 Connect Gmail Account</button></a>', 
                unsafe_allow_html=True)
        
        st.markdown("""
        ---
        ##### 🔒 Privacy Note
        This app only reads your FoodPanda order confirmation emails. No data is stored or shared.
        """)

        # Preview section at the bottom
        with st.expander("👀 Preview Sample Analysis", expanded=True):
            try:
                # Load sample data from CSV
                preview_df = pd.read_csv('preview_sample.csv')
                preview_df['date'] = pd.to_datetime(preview_df['date'])
                
                # Calculate date range
                latest_order = preview_df['date'].max()
                earliest_order = preview_df['date'].min()
                date_range = f"{earliest_order.strftime('%B %d, %Y')} - {latest_order.strftime('%B %d, %Y')}"
                
                # Display Summary Section
                st.markdown("## 📊 Sample Analysis Preview")
                st.markdown(f"### 📅 Analysis Period: {date_range}")
                
                # Display all analysis sections using the display_analysis function
                display_analysis(preview_df)
                
                # Restaurant Analysis Tab
                st.markdown("---")
                st.markdown("### 🏪 Restaurant Analysis")
                
                tab_rest1, tab_rest2 = st.tabs(["Top Restaurants", "Monthly Top 3"])
                
                with tab_rest1:
                    # Overall top restaurants
                    restaurant_summary = preview_df.groupby('restaurant').agg({
                        'price': ['sum', 'count', 'mean']
                    }).round(2)
                    restaurant_summary.columns = ['Total Spent', 'Number of Orders', 'Average Order']
                    restaurant_summary = restaurant_summary.sort_values('Number of Orders', ascending=False)
                    
                    st.markdown("#### Top 10 Most Ordered From Restaurants")
                    top_restaurants = restaurant_summary.head(10)
                    st.dataframe(top_restaurants, use_container_width=True)
                
                with tab_rest2:
                    # Monthly top 3 restaurants
                    st.markdown("#### Monthly Top 3 Restaurants")
                    preview_df['month_year'] = preview_df['date'].dt.strftime('%B %Y')
                    
                    # Sort months in descending order
                    months = sorted(preview_df['month_year'].unique(), 
                                  key=lambda x: pd.to_datetime(x, format='%B %Y'), 
                                  reverse=True)
                    
                    monthly_summary = []
                    for month in months:
                        month_data = preview_df[preview_df['month_year'] == month]
                        top_3 = month_data.groupby('restaurant').agg({
                            'price': 'sum',
                            'restaurant': 'count'
                        }).round(2)
                        top_3.columns = ['Total Spent', 'Orders']
                        top_3 = top_3.sort_values('Total Spent', ascending=False).head(3)
                        
                        formatted_top_3 = [
                            f"{restaurant} ({orders} - PKR {spent:,.0f})"
                            for restaurant, (spent, orders) in top_3.iterrows()
                        ]
                        
                        while len(formatted_top_3) < 3:
                            formatted_top_3.append("")
                            
                        monthly_summary.append({
                            'Month': month,
                            '1st': formatted_top_3[0],
                            '2nd': formatted_top_3[1],
                            '3rd': formatted_top_3[2]
                        })
                    
                    monthly_summary_df = pd.DataFrame(monthly_summary)
                    st.dataframe(monthly_summary_df, hide_index=True, use_container_width=True)
                
            except Exception as e:
                st.error(f"Error loading preview data: {str(e)}")
                st.info("Preview sample data file not found or could not be loaded.")

# Update metrics styling and add comprehensive CSS
st.markdown("""
    <style>
    /* Metric values */
    [data-testid="stMetricValue"] {
        color: #FF2B85;
        font-weight: 600;
    }
    
    /* Container styling for card-like sections */
    .stContainer {
        background-color: #ffffff;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        margin-bottom: 1rem;
    }
    
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #f8f9fa;
        padding: 0.5rem;
        border-radius: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        background-color: transparent;
        border-radius: 6px;
        color: #666;
        font-weight: 500;
        padding: 0 24px;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #FF2B85;
        color: white;
    }
    
    /* Expander styling */
    .streamlit-expanderHeader {
        background-color: #fff5f8;
        border-radius: 8px;
        font-weight: 600;
    }
    
    /* Dataframe styling */
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
    }
    
    /* Button styling */
    .stButton > button {
        border-radius: 8px;
        font-weight: 500;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(255, 43, 133, 0.3);
    }
    
    /* Section headers */
    h2, h3 {
        color: #2c3e50;
        margin-top: 1.5rem;
    }
    
    /* Card container for metrics */
    div[data-testid="stMetricValue"] {
        font-size: 1.8rem;
    }
    
    /* Improve spacing */
    .block-container {
        padding-top: 2rem;
        max-width: 1200px;
    }
    
    /* Insight Cards */
    .insight-card {
        background: linear-gradient(135deg, #fff5f8 0%, #ffffff 100%);
        border-left: 4px solid #FF2B85;
        border-radius: 10px;
        padding: 1.2rem;
        margin-bottom: 1rem;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
        transition: all 0.3s ease;
        height: 100%;
        min-height: 200px;
        display: flex;
        flex-direction: column;
    }
    
    .insight-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 4px 16px rgba(255, 43, 133, 0.15);
    }
    
    .insight-icon {
        font-size: 2rem;
        margin-bottom: 0.5rem;
        flex-shrink: 0;
    }
    
    .insight-title {
        font-weight: 600;
        font-size: 1rem;
        color: #2c3e50;
        margin-bottom: 0.5rem;
        flex-shrink: 0;
    }
    
    .insight-description {
        font-size: 0.9rem;
        color: #555;
        line-height: 1.4;
        flex-grow: 1;
    }
    
    /* Budget Cards */
    .budget-card {
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 1rem;
        text-align: center;
    }
    
    .budget-good {
        background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
        border: 2px solid #4CAF50;
    }
    
    .budget-warning {
        background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%);
        border: 2px solid #ff9800;
    }
    
    .budget-over {
        background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%);
        border: 2px solid #f44336;
    }
    
    .budget-header {
        font-size: 1.2rem;
        font-weight: 600;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.5rem;
    }
    
    .budget-emoji {
        font-size: 1.5rem;
    }
    
    .budget-status-text {
        color: #2c3e50;
    }
    
    /* Progress bar styling */
    .stProgress > div > div > div {
        background-color: #4CAF50;
    }
    
    /* Current Month Header */
    .current-month-header {
        text-align: center;
        font-size: 1.1rem;
        font-weight: 600;
        color: #2c3e50;
        padding: 0.8rem 1rem;
        background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
        border-radius: 8px;
        margin-bottom: 1rem;
        border-left: 4px solid #4CAF50;
    }
    
    /* Hero Section */
    .hero-section {
        background: linear-gradient(135deg, #ffffff 0%, #fff5f8 100%);
        border-radius: 12px;
        padding: 2rem;
        margin: 1.5rem 0;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.12);
        border-left: 5px solid #FF2B85;
        text-align: center;
        animation: heroFadeIn 0.6s ease-out;
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }
    
    .hero-section:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 24px rgba(255, 43, 133, 0.2);
    }
    
    @keyframes heroFadeIn {
        from {
            opacity: 0;
            transform: translateY(20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    .hero-icon {
        font-size: 3rem;
        margin-bottom: 0.5rem;
        animation: heroIconBounce 1s ease-out;
    }
    
    @keyframes heroIconBounce {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.1); }
    }
    
    .hero-title {
        font-size: 1.3rem;
        color: #2c3e50;
        margin-bottom: 0.8rem;
        font-weight: 500;
    }
    
    .hero-restaurant {
        color: #FF2B85;
        font-weight: 700;
        font-size: 1.4rem;
    }
    
    .hero-stats {
        font-size: 1.1rem;
        color: #555;
        margin-bottom: 1rem;
        font-weight: 500;
    }
    
    .hero-stat-number {
        color: #FF2B85;
        font-weight: 700;
    }
    
    .hero-message {
        font-size: 1rem;
        color: #666;
        line-height: 1.6;
        padding: 1rem;
        background: rgba(255, 43, 133, 0.05);
        border-radius: 8px;
        margin-top: 1rem;
    }
    
    /* Responsive adjustments for hero */
    @media (max-width: 768px) {
        .hero-section {
            padding: 1.5rem 1rem;
        }
        
        .hero-icon {
            font-size: 2.5rem;
        }
        
        .hero-title {
            font-size: 1.1rem;
        }
        
        .hero-restaurant {
            font-size: 1.2rem;
        }
        
        .hero-stats {
            font-size: 1rem;
        }
        
        .hero-message {
            font-size: 0.9rem;
        }
    }
    
    /* ============================================
       WRAPPED EXPERIENCE STYLES
       ============================================ */
    
    /* Wrapped Slides Container */
    .wrapped-slide {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        border-radius: 20px;
        padding: 3rem 2rem;
        min-height: 400px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
        color: white;
        margin: 1rem 0;
        animation: slideIn 0.5s ease-out;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
    }
    
    @keyframes slideIn {
        from {
            opacity: 0;
            transform: translateX(30px);
        }
        to {
            opacity: 1;
            transform: translateX(0);
        }
    }
    
    /* Slide 1: Intro */
    .slide-intro {
        background: linear-gradient(135deg, #FF2B85 0%, #e91e63 50%, #9c27b0 100%);
    }
    
    .wrapped-year {
        font-size: 1.5rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
        opacity: 0.9;
    }
    
    .wrapped-period {
        font-size: 1rem;
        opacity: 0.8;
        margin-bottom: 2rem;
    }
    
    .wrapped-big-number {
        font-size: 6rem;
        font-weight: 800;
        line-height: 1;
        background: linear-gradient(to bottom, #ffffff, #f0f0f0);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        text-shadow: 0 4px 20px rgba(255, 255, 255, 0.3);
        animation: numberPop 0.8s ease-out 0.3s both;
    }
    
    @keyframes numberPop {
        from {
            transform: scale(0.5);
            opacity: 0;
        }
        to {
            transform: scale(1);
            opacity: 1;
        }
    }
    
    .wrapped-label {
        font-size: 1.3rem;
        margin-top: 1rem;
        opacity: 0.9;
    }
    
    .wrapped-subtitle {
        font-size: 1rem;
        margin-top: 2rem;
        opacity: 0.7;
        font-style: italic;
    }
    
    /* Slide 2: Restaurant */
    .slide-restaurant {
        background: linear-gradient(135deg, #f39c12 0%, #e74c3c 100%);
    }
    
    .wrapped-small-text {
        font-size: 1.2rem;
        opacity: 0.9;
        margin-bottom: 1rem;
    }
    
    .wrapped-restaurant-name {
        font-size: 2.5rem;
        font-weight: 700;
        margin: 1rem 0;
        text-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
        animation: revealName 1s ease-out 0.3s both;
    }
    
    @keyframes revealName {
        from {
            opacity: 0;
            transform: translateY(20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    .wrapped-stats-row {
        display: flex;
        gap: 3rem;
        margin: 2rem 0;
    }
    
    .wrapped-stat {
        display: flex;
        flex-direction: column;
    }
    
    .wrapped-stat .stat-number {
        font-size: 2rem;
        font-weight: 700;
    }
    
    .wrapped-stat .stat-label {
        font-size: 0.9rem;
        opacity: 0.8;
    }
    
    .wrapped-fun-fact {
        font-size: 1.1rem;
        background: rgba(255, 255, 255, 0.2);
        padding: 0.8rem 1.5rem;
        border-radius: 30px;
        margin-top: 1rem;
    }
    
    /* Slide 3: Spending */
    .slide-spending {
        background: linear-gradient(135deg, #2ecc71 0%, #27ae60 50%, #1abc9c 100%);
    }
    
    .wrapped-big-money {
        font-size: 3.5rem;
        font-weight: 800;
        margin: 1rem 0;
        text-shadow: 0 2px 15px rgba(0, 0, 0, 0.2);
    }
    
    .wrapped-equivalents {
        background: rgba(255, 255, 255, 0.15);
        border-radius: 15px;
        padding: 1.5rem;
        margin: 1.5rem 0;
        width: 100%;
        max-width: 400px;
    }
    
    .equiv-title {
        font-size: 0.9rem;
        opacity: 0.8;
        margin-bottom: 1rem;
    }
    
    .comparison-item {
        display: flex;
        align-items: center;
        gap: 0.8rem;
        padding: 0.5rem 0;
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    .comparison-item:last-child {
        border-bottom: none;
    }
    
    .comp-emoji {
        font-size: 1.5rem;
    }
    
    .comp-value {
        font-weight: 700;
        font-size: 1.2rem;
    }
    
    .comp-unit {
        opacity: 0.8;
    }
    
    .wrapped-frequency {
        font-size: 1rem;
        margin-top: 1rem;
        opacity: 0.9;
    }
    
    /* Slide 4: Time */
    .slide-time {
        background: linear-gradient(135deg, #3498db 0%, #2980b9 50%, #8e44ad 100%);
    }
    
    .wrapped-personality {
        font-size: 2.5rem;
        font-weight: 700;
        margin: 1.5rem 0;
        animation: personalityReveal 0.8s ease-out 0.3s both;
    }
    
    @keyframes personalityReveal {
        from {
            opacity: 0;
            transform: scale(0.8);
        }
        to {
            opacity: 1;
            transform: scale(1);
        }
    }
    
    .wrapped-peak-time {
        background: rgba(255, 255, 255, 0.2);
        border-radius: 15px;
        padding: 1.5rem 2.5rem;
        margin: 1.5rem 0;
    }
    
    .peak-label {
        font-size: 0.9rem;
        opacity: 0.8;
    }
    
    .peak-value {
        font-size: 3rem;
        font-weight: 800;
    }
    
    .wrapped-time-desc {
        font-size: 1.1rem;
        max-width: 300px;
        line-height: 1.5;
        opacity: 0.9;
    }
    
    /* Slide 5: Summary */
    .slide-summary {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        padding: 2rem;
    }
    
    .summary-header {
        font-size: 1.8rem;
        font-weight: 700;
        margin-bottom: 2rem;
        color: #FF2B85;
    }
    
    .summary-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 1.5rem;
        width: 100%;
        max-width: 400px;
        margin-bottom: 2rem;
    }
    
    .summary-item {
        background: rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 1.2rem;
        display: flex;
        flex-direction: column;
        align-items: center;
    }
    
    .summary-emoji {
        font-size: 1.5rem;
        margin-bottom: 0.3rem;
    }
    
    .summary-value {
        font-size: 1.3rem;
        font-weight: 700;
    }
    
    .summary-label {
        font-size: 0.8rem;
        opacity: 0.7;
    }
    
    .summary-personality {
        background: linear-gradient(90deg, #FF2B85, #e91e63);
        padding: 0.8rem 2rem;
        border-radius: 30px;
        font-size: 1.1rem;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin-bottom: 1.5rem;
    }
    
    .summary-footer {
        font-size: 0.9rem;
        opacity: 0.6;
    }
    
    /* ============================================
       DIVERSITY SCORE STYLES
       ============================================ */
    
    .diversity-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 20px;
        padding: 2rem;
        color: white;
        text-align: center;
        margin: 1rem 0;
        box-shadow: 0 8px 30px rgba(102, 126, 234, 0.3);
    }
    
    .diversity-header {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.8rem;
        margin-bottom: 1.5rem;
    }
    
    .diversity-emoji {
        font-size: 2.5rem;
    }
    
    .diversity-title {
        font-size: 1.8rem;
        font-weight: 700;
    }
    
    .diversity-score-container {
        background: rgba(255, 255, 255, 0.2);
        border-radius: 15px;
        padding: 1.5rem;
        display: inline-block;
        margin-bottom: 1.5rem;
    }
    
    .diversity-score {
        font-size: 3.5rem;
        font-weight: 800;
    }
    
    .diversity-score-label {
        font-size: 0.9rem;
        opacity: 0.8;
    }
    
    .diversity-desc {
        font-size: 1.1rem;
        line-height: 1.5;
        max-width: 400px;
        margin: 0 auto 1.5rem;
        opacity: 0.9;
    }
    
    .diversity-stats {
        display: flex;
        justify-content: center;
        gap: 3rem;
    }
    
    .div-stat {
        display: flex;
        flex-direction: column;
    }
    
    .div-stat-value {
        font-size: 2rem;
        font-weight: 700;
    }
    
    .div-stat-label {
        font-size: 0.85rem;
        opacity: 0.8;
    }
    
    .loyalty-badge {
        background: linear-gradient(90deg, #f39c12, #e74c3c);
        border-radius: 10px;
        padding: 1rem 1.5rem;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.8rem;
        margin: 1rem 0;
        color: white;
        font-weight: 600;
    }
    
    .badge-emoji {
        font-size: 1.5rem;
    }
    
    .top-restaurant-bar {
        display: flex;
        align-items: center;
        gap: 0.8rem;
        padding: 0.8rem;
        background: rgba(255, 43, 133, 0.05);
        border-radius: 8px;
        margin: 0.5rem 0;
    }
    
    .tr-medal {
        font-size: 1.3rem;
    }
    
    .tr-name {
        flex: 1;
        font-weight: 500;
        min-width: 120px;
    }
    
    .tr-bar-container {
        flex: 2;
        height: 8px;
        background: rgba(255, 43, 133, 0.1);
        border-radius: 4px;
        overflow: hidden;
    }
    
    .tr-bar {
        height: 100%;
        background: linear-gradient(90deg, #FF2B85, #e91e63);
        border-radius: 4px;
        transition: width 0.8s ease-out;
    }
    
    .tr-count {
        font-size: 0.9rem;
        color: #666;
        min-width: 80px;
        text-align: right;
    }
    
    /* ============================================
       FUN COMPARISONS STYLES
       ============================================ */
    
    .comparison-card {
        background: linear-gradient(135deg, #fff5f8 0%, #ffffff 100%);
        border-radius: 15px;
        padding: 1.5rem;
        text-align: center;
        border: 2px solid rgba(255, 43, 133, 0.1);
        transition: all 0.3s ease;
        min-height: 200px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        margin-bottom: 1rem;
    }
    
    .comparison-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 10px 30px rgba(255, 43, 133, 0.15);
        border-color: #FF2B85;
    }
    
    .comp-card-emoji {
        font-size: 2.5rem;
        margin-bottom: 0.5rem;
    }
    
    .comp-card-title {
        font-size: 0.9rem;
        color: #666;
        margin-bottom: 0.5rem;
    }
    
    .comp-card-value {
        font-size: 2.5rem;
        font-weight: 800;
        color: #FF2B85;
        line-height: 1.2;
    }
    
    .comp-card-unit {
        font-size: 1rem;
        color: #555;
        margin-bottom: 0.5rem;
    }
    
    .comp-card-subtitle {
        font-size: 0.85rem;
        color: #888;
        line-height: 1.4;
    }
    
    /* Responsive adjustments for wrapped */
    @media (max-width: 768px) {
        .wrapped-slide {
            padding: 2rem 1rem;
            min-height: 350px;
        }
        
        .wrapped-big-number {
            font-size: 4rem;
        }
        
        .wrapped-restaurant-name {
            font-size: 1.8rem;
        }
        
        .wrapped-big-money {
            font-size: 2.5rem;
        }
        
        .wrapped-personality {
            font-size: 1.8rem;
        }
        
        .summary-grid {
            gap: 1rem;
        }
        
        .diversity-score {
            font-size: 2.5rem;
        }
        
        .comparison-card {
            min-height: 180px;
        }
    }
    </style>
    """, unsafe_allow_html=True)
