# ⛳ Tee Time Auto Booker

This tool logs in to the Sharpstown Golf Course website and books a tee time that matches your settings.  
It asks for your email and password when it starts and handles the full booking flow.

---

## ⭐ Features

- 🔐 Prompts for your email and password at startup  
- 🏌️ Logs in to the Sharpstown booking page  
- 🎯 Selects:
  - 📅 Date: November 11 2025
  - 👥 Players: 4
  - 🌤️ Time of Day: Midday
  - ⛳ Holes: 18
  - 🚫 Cart: No
- ⚡ Picks the earliest tee time
- ✅ Confirms the booking
- 🖼️ Saves screenshots in a folder

---

## 💻 Setup Instructions for macOS  
Everything below stays inside this single code block.

### 1. 🖥️ Open Terminal  
Found in Applications > Utilities.

### 2. 📥 Clone the repository

git clone https://github.com/Phoenix275/Tee-Time-bot.git  
cd Tee-Time-bot

### 3. 🧪 Create a virtual environment  

python3 -m venv .venv

### 4. ⚙️ Activate the environment  

source .venv/bin/activate

### 5. 📦 Install the required packages  

pip install playwright python-dateutil  
python3 -m playwright install chromium

### 6. 🚀 Run the script  

python3 tee_bot_book_fix.py

You will be prompted:

Enter your Sharpstown login email:  
Enter your password:

The bot will automatically:  
- Log in  
- Open Online Tee Times  
- Apply filters  
- Pick the earliest time  
- Press Book Time  
- Confirm the reservation  
- Verify your booking  

Screenshots will be saved in:

tee_bot_artifacts/

---
