# 🚀 Visual Private Network (VPN) Management Bot

A comprehensive Telegram Bot for selling and managing VPN services (X-UI) featuring a manual **Card-to-Card** payment system, a **Referral Program**, and **Detailed Tutorials**.

---

## ✨ Features

* **🛒 VPN Service Sales:** Automated account creation on X-UI panels (V2Ray/Vmess).
* **💳 Manual Payment System:** Users upload payment receipts (screenshots); Admins approve/reject directly from the bot.
* **🎁 Free Trial System:** One-time 1GB/1 Day trial service for new users to test connectivity.
* **🔗 Advanced Referral Program:** * Unique referral links for every user.
    * Automatic commission credits to balance upon sub-user purchases.
    * Detailed referral history and earning tracking.
* **📚 Connection Tutorials:** Built-in guides for Android (V2rayNG), iOS (V2Box), Windows (Hiddify), and more.
* **🛠 Powerful Admin Dashboard:**
    * **User Investigation:** View detailed profiles, balance, and services using `/check`.
    * **Financial Control:** Manually add/edit balance or edit user notes.
    * **Broadcast System:** Send announcements to all bot users using `/announce`.
    * **Real-time Alerts:** Notifications for new users and pending payment receipts.
* **📂 Persistent Storage:** Uses local JSON databases—no complex SQL setup required.

---

## 🛠 Prerequisites

* **Python 3.10+**
* **X-UI Panel** (Sanaei or Alireza fork) with API enabled.
* **Telegram Bot Token** from [@BotFather](https://t.me/BotFather).

---

## 🚀 Installation

1.  **Clone the Repository:**
    ```bash
    git clone [https://github.com/your-username/your-repo-name.git](https://github.com/your-username/your-repo-name.git)
    cd your-repo-name
    ```

2.  **Install Requirements:**
    ```bash
    pip install python-telegram-bot requests
    ```

3.  **Configuration:**
    Open the script and update the following variables with your credentials:
    * `BOT_TOKEN`: Your bot token.
    * `ADMIN_CHAT_IDS`: Your numeric Telegram ID.
    * `SERVERS_CONFIG`: Your X-UI URL, Username, and Password.
    * `CARD_NUMBER`: Your payment card details.

4.  **Run the Bot:**
    ```bash
    python Visual-Private-Network-Shipping-CardVersion.py
    ```

---

## 👨‍💻 Admin Commands

| Command | Description |
| :--- | :--- |
| `/start` | Launch the main menu. |
| `/check` | View user details (via ID or by replying to a user's message). |
| `/add [ID] [Amount]` | Manually add credit to a user's wallet. |
| `/announce [Msg]` | Send a global notification to all users. |

---

## 📂 Project Structure

* `users.json`: Stores user profiles, balance, and status.
* `pending_receipts.json`: Queue for admin approval of payments.
* `transaction_history.json`: Logs of all purchases and credits.
* `referral_data.json`: Tracks invite chains and commissions.

---

## 🛡 Disclaimer
This tool is for educational purposes. Ensure you comply with your local laws and the terms of service of your hosting provider.

## 📄 License
This project is licensed under the [MIT License](LICENSE).