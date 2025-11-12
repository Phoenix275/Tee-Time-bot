# Tee Time Auto Booker ⛳

This Python automation script logs into the **Sharpstown Golf Course** website and automatically books a tee time that matches your chosen parameters.  
It uses **Playwright** to control a Chromium browser and simulate human actions (login, parameter selection, and booking).

---

## 🧩 Features

- Prompts for your **email** and **password** securely at runtime  
- Automatically logs into the Sharpstown booking portal  
- Chooses:
  - **Date:** November 11 2025  
  - **Players:** 4  
  - **Time of Day:** Midday  
  - **Holes:** 18  
  - **Cart:** No  
- Selects the earliest available tee time and confirms the reservation  
- Takes screenshots at each step for verification  
- Saves login cookies so you stay logged in for future runs  

---

## 🖥️ Requirements

- macOS, Linux, or Windows  
- Python 3.9 or newer  
- Google Chrome is **not** required (Playwright installs its own Chromium build)

---

## 🧰 Setup Instructions

1. **Clone the repository**

   ```bash
   git clone https://github.com/<your-username>/tee-bot.git
   cd tee-bot
