# 🍔 Foodpanda Tracker App 📊

## 📌 Description
The **Foodpanda Tracker App** is a **Streamlit** web application that helps users analyze their **Foodpanda spending** over the past **365 days**. The app fetches order data from **Gmail** using the **Gmail API** and provides insightful spending summaries.

---

## 🚀 Features
- 📥 **Fetches Foodpanda receipts** from Gmail
- 📊 **Provides a spending summary** for the last year
- 📅 **Breakdown of monthly expenses**
- 📈 **Visual charts for analysis**
- 🔒 **Secure Google authentication using OAuth 2.0**

---

## 🛠️ Setup Instructions

### **1. Prerequisites**
Ensure you have the following installed:
- **Python 3.8+** – [Download Here](https://www.python.org/downloads/)
- **Streamlit** – For building the web app
- **Google Cloud Project** – To enable Gmail API
- **OAuth Credentials** – Authentication is handled dynamically

---

### **2. Clone the Repository**
```sh
git clone https://github.com/fasi96/FoodpandaExpenseTracker.git
cd foodpanda-tracker
```

---

### **3. Install Dependencies**
Install required Python libraries:
```sh
pip install -r requirements.txt
```

---

### **4. Update Google API Redirect URL**
Since authentication happens **on the fly**, you need to update the redirect URL:
1. Go to **Google Cloud Console**: [https://console.cloud.google.com/](https://console.cloud.google.com/)
2. Navigate to **OAuth 2.0 Credentials**.
3. Edit the **Authorized Redirect URI**:
   - Change **Streamlit Cloud URL** to `http://localhost:8501/` (for local development).
4. Save the changes.

---

### **5. Run the App**
Start the Streamlit app with:
```sh
streamlit run app.py
```

This will launch the app in your browser at `http://localhost:8501`.

---

## 📝 Usage
1. **Sign in with Google** to grant access to Gmail.
2. The app will scan for **Foodpanda receipts** in your emails.
3. View a **summary of your spending** for the past year.
4. Analyze **monthly trends** and visualize data.

---

## 🛠️ Tech Stack
- **Python** 🐍
- **Streamlit** 📊
- **Gmail API** ✉️
- **OAuth 2.0** 🔒
- **Matplotlib/Pandas** for Data Analysis 📈

---

## 🤝 Contributing
1. Fork the repo.
2. Create a feature branch: `git checkout -b feature-name`
3. Commit changes: `git commit -m "Added new feature"`
4. Push branch: `git push origin feature-name`
5. Open a **Pull Request**.

---

## 📩 Contact
Developed by **M. Fasi ur Rehman**  
📧 Email: mofasiurrehman@gmail.com


---

🚀 **Start tracking your Foodpanda expenses today!** 🍽️
