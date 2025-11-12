# ⛳ Tee Time Auto Booker

Automates booking tee times on the Sharpstown Golf Course website.  
You enter your email and password at launch, and the bot handles the full booking process.

---

## ⭐ Features

- 🔐 Secure login prompt  
- 📅 Automatically selects:
  - Date: **November 11, 2025**
  - Players: **4**
  - Time of Day: **Midday**
  - Holes: **18**
  - Cart: **No**
- ⚡ Finds the earliest qualifying tee time  
- 🟢 Books the time and confirms your reservation  
- 🖼 Saves screenshots in `tee_bot_artifacts/`  

---

## 💻 macOS Setup Guide

Everything below stays inside this single block.

### 1. 🖥 Open Terminal  
(Located in Applications → Utilities)

### 2. 📥 Clone the Repository  

git clone https://github.com/Phoenix275/Tee-Time-bot.git  
cd Tee-Time-bot

### 3. 🧪 Create Virtual Environment  

python3 -m venv .venv

### 4. ⚙️ Activate Environment  

source .venv/bin/activate

### 5. 📦 Install Dependencies  

pip install playwright python-dateutil  
python3 -m playwright install chromium

### 6. 🚀 Run the Bot  

python3 tee2.py

The script will prompt:

Enter your Sharpstown login email:  
Enter your password:

The bot will then:  
- Log you in  
- Open Online Tee Times  
- Apply all booking filters  
- Select the earliest available time  
- Press **Book Time**  
- Confirm the reservation  
- Verify the booking on your account  
- Save screenshots for every step  

Screenshots appear in:

tee_bot_artifacts/

---

## 🧹 Tips

- Keep your browser window visible to avoid OS throttling  
- If the script stops early, check the screenshots for the exact step  
- For automation, you can later create a cron job once everything works reliably  

---
