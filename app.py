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

# Store monthly budget in session
if "monthly_budget" not in st.session_state:
    st.session_state["monthly_budget"] = 0

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
    
    # Display metrics in a container
    with st.container():
        col1, col2 = st.columns(2)
        with col1:
            st.metric("💰 Total Spent", f"PKR {total_spent:,.2f}")
            st.metric("📦 Total Orders", f"{total_orders:,}")
        with col2:
            st.metric("📊 Average Order", f"PKR {avg_order:,.2f}")
            st.metric("📅 Monthly Average", f"PKR {monthly_average:,.2f}")
    
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
    
    # Display Budget Tracker if budget is set
    if st.session_state["monthly_budget"] > 0:
        st.markdown("### 💰 Budget Status (Current Month)")
        budget_status = calculate_budget_status(df, st.session_state["monthly_budget"])
        
        if budget_status:
            # Determine status styling
            if budget_status['status'] == 'over':
                status_emoji = "🚨"
                status_text = "Over Budget"
                progress_color = "#ff4444"
            elif budget_status['status'] == 'warning':
                status_emoji = "⚠️"
                status_text = "Approaching Limit"
                progress_color = "#ff9800"
            else:
                status_emoji = "✅"
                status_text = "On Track"
                progress_color = "#4CAF50"
            
            # Display budget card
            st.markdown(f"""
                <div class="budget-card budget-{budget_status['status']}">
                    <div class="budget-header">
                        <span class="budget-emoji">{status_emoji}</span>
                        <span class="budget-status-text">{status_text}</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            # Display metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("💵 Budget", f"PKR {budget_status['budget']:,.0f}")
            with col2:
                st.metric("💸 Spent", f"PKR {budget_status['spent']:,.0f}")
            with col3:
                st.metric("💰 Remaining", f"PKR {budget_status['remaining']:,.0f}")
            with col4:
                st.metric("📊 Used", f"{budget_status['percentage_used']:.1f}%")
            
            # Progress bar
            progress_value = min(budget_status['percentage_used'] / 100, 1.0)
            st.progress(progress_value)
            
            # Projection
            if budget_status['days_remaining'] > 0:
                st.caption(f"📈 **Projection:** At current rate (PKR {budget_status['daily_rate']:,.0f}/day), you'll spend PKR {budget_status['projected_spending']:,.0f} this month.")
    
    st.markdown("---")
    
    # Create tabs for different analysis sections
    tab1, tab2, tab3 = st.tabs(["📈 Spending Trends", "⏰ Time Analysis", "🏪 Restaurant Analysis"])
    
    with tab1:
        st.markdown("### Monthly Spending Trend")
        
        # Create monthly aggregation
        monthly_data = df.groupby(df['date'].dt.to_period('M'))\
            .agg({'price': 'sum'})\
            .reset_index()
        monthly_data['date'] = monthly_data['date'].dt.to_timestamp()
        monthly_data = monthly_data.sort_values('date')

        # Create the bar chart with budget line
        fig = create_monthly_spending_chart(monthly_data, st.session_state["monthly_budget"])
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
    
    # Insight 1: Favorite Restaurant
    if not df.empty:
        top_restaurant = df.groupby('restaurant')['restaurant'].count().sort_values(ascending=False).index[0]
        top_restaurant_orders = df.groupby('restaurant')['restaurant'].count().sort_values(ascending=False).iloc[0]
        insights.append({
            'icon': '🏆',
            'title': 'Top Restaurant',
            'description': f"You've ordered from **{top_restaurant}** {top_restaurant_orders} times!"
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
    
    return insights[:6]  # Return up to 6 insights

def calculate_budget_status(df, monthly_budget):
    """Calculate budget status for the current month."""
    if monthly_budget == 0:
        return None
    
    # Get current month data - handle timezone-aware dates
    current_month = pd.Timestamp.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Make timezone-aware if dataframe dates are timezone-aware
    if df['date'].dt.tz is not None:
        current_month = current_month.tz_localize(df['date'].dt.tz)
    df_current = df[df['date'] >= current_month]
    
    current_month_spending = df_current['price'].sum()
    remaining = monthly_budget - current_month_spending
    percentage_used = (current_month_spending / monthly_budget) * 100 if monthly_budget > 0 else 0
    
    # Calculate daily rate and projection
    now = pd.Timestamp.now()
    days_in_month = now.day
    # Calculate last day of current month
    next_month = (now.replace(day=1) + pd.Timedelta(days=32)).replace(day=1)
    last_day_of_month = (next_month - pd.Timedelta(days=1)).day
    days_remaining = last_day_of_month - days_in_month
    
    daily_rate = current_month_spending / days_in_month if days_in_month > 0 else 0
    projected_spending = current_month_spending + (daily_rate * days_remaining)
    
    # Determine status
    if percentage_used >= 100:
        status = "over"
        status_color = "red"
    elif percentage_used >= 80:
        status = "warning"
        status_color = "orange"
    else:
        status = "good"
        status_color = "green"
    
    return {
        'budget': monthly_budget,
        'spent': current_month_spending,
        'remaining': remaining,
        'percentage_used': percentage_used,
        'status': status,
        'status_color': status_color,
        'daily_rate': daily_rate,
        'projected_spending': projected_spending,
        'days_remaining': days_remaining
    }

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

def display_analysis(df):
    """Display the full analysis for either preview or actual data."""
    # Display metrics in a container
    with st.container():
        total_spent = df['price'].sum()
        total_orders = len(df)
        avg_order = total_spent / total_orders if total_orders > 0 else 0
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("💰 Total Spent", f"PKR {total_spent:,.2f}")
        with col2:
            st.metric("📦 Total Orders", str(total_orders))
        with col3:
            st.metric("📊 Average Order", f"PKR {avg_order:,.2f}")
    
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
    
    st.markdown("---")
    
    # Create tabs for different analysis sections
    tab1, tab2 = st.tabs(["📈 Spending Trends", "⏰ Time Analysis"])
    
    with tab1:
        st.markdown("### Monthly Spending Trend")
        monthly_data = df.groupby(df['date'].dt.to_period('M'))\
            .agg({'price': 'sum'})\
            .reset_index()
        monthly_data['date'] = monthly_data['date'].dt.to_timestamp()
        monthly_data = monthly_data.sort_values('date')
        
        # Pass budget to chart for preview (use 0 as default)
        fig = create_monthly_spending_chart(monthly_data, 0)
        st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
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

# Add budget tracker in sidebar
st.sidebar.markdown("---")
st.sidebar.markdown("### 💰 Monthly Budget Tracker")
monthly_budget = st.sidebar.number_input(
    "Set your monthly budget (PKR)",
    min_value=0,
    value=st.session_state["monthly_budget"],
    step=1000,
    help="Set a monthly budget to track your spending"
)
st.session_state["monthly_budget"] = monthly_budget

if monthly_budget > 0:
    st.sidebar.markdown(f"**Budget:** PKR {monthly_budget:,.0f}")
    st.sidebar.caption("Your budget will be displayed in the analysis section.")

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
        with st.expander("👀 Preview Sample Analysis", expanded=False):
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
    }
    
    .insight-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 4px 16px rgba(255, 43, 133, 0.15);
    }
    
    .insight-icon {
        font-size: 2rem;
        margin-bottom: 0.5rem;
    }
    
    .insight-title {
        font-weight: 600;
        font-size: 1rem;
        color: #2c3e50;
        margin-bottom: 0.5rem;
    }
    
    .insight-description {
        font-size: 0.9rem;
        color: #555;
        line-height: 1.4;
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
    </style>
    """, unsafe_allow_html=True)
