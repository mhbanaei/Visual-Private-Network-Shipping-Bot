# 🚀 Visual Private Network (VPN) Management Bot

A Telegram bot for selling and managing VPN services on **3x-ui** panels, with a manual **card-to-card** payment flow, a **ZarinPal** variant, a **referral program**, and a built-in **web admin panel**.

---

## ✨ Features

* **🛒 VPN sales:** automatic client creation on the 3x-ui panel (VLESS/VMess).
* **💳 Manual payment (card version):** users upload receipts; admins approve or reject from the bot.
* **🌐 ZarinPal gateway:** a sandbox-free alternative entry point (`Visual-Private-Network-Shipping.py`).
* **🎁 Free trial:** one-time 1GB / 1-day trial for new users.
* **🔗 Referral program:** unique links, per-user commission percentage, earning history.
* **📚 Connection tutorials:** Android (V2rayNG), iOS (V2Box), Windows (Hiddify) and more.
* **🖥 Web admin panel (port 9997):** runs inside the bot process. Dashboard, users, search/sort, balance editing, full profile editing (name, @username, referral percentage, earnings, referrer, notes), settle/withdraw, reset trial, services CRUD, receipts, transactions, broadcast.
* **🎛 Live service management in the panel:** pick any service and see traffic used / remaining, expiry date and days left, online state, allowed device count. Rename the client (subscription link follows the new name), set or adjust volume, extend expiry by days or pick an exact date, change `limitIp`, enable/disable, reset traffic, delete. Every change is notified to the user in Telegram.
* **🔁 Sync with 3x-ui:** a service renamed inside the 3x-ui panel itself is detected by UUID and saved back into the bot's database.
* **📂 Storage:** a single local SQLite file (`botdata.db`) created automatically on first run.

---

## 🛠 Prerequisites

* **Python 3.10+**
* **3x-ui panel** ([MHSanaei/3x-ui](https://github.com/MHSanaei/3x-ui)) with the API reachable
* **Telegram bot token** from [@BotFather](https://t.me/BotFather)

---

## 🚀 Installation

1. Clone the repository and enter the folder.
2. Install the dependencies:

   ```bash
   pip install python-telegram-bot requests "qrcode[pil]"
   ```

3. Configure the credentials:

   * `servers.py` → panel URL (including the secret path), username/password or `api_token`, `inbound_id` (`0` = last inbound), server address and subscription port.
   * `BOT_TOKEN` and `ADMIN_CHAT_IDS` at the top of the bot file you are going to run.
   * `CARD_NUMBER` in the card version.
   * `ZARINPAL_MERCHANT_ID` in the ZarinPal version.
   * The admin panel password is read from the `PANEL_PASSWORD` environment variable (and `PANEL_PORT`, default `9997`).

4. Run it:

   ```bash
   python Visual-Private-Network-Shipping-CardVersion.py
   ```

   or on Windows double-click `start-card.bat` / `start-zarinpal.bat`.

   The web panel starts together with the bot at <http://127.0.0.1:9997>.

> The bot refuses to start if another copy is already polling Telegram with the same token, so you never get `409 Conflict` errors.

---

## 👨‍💻 Admin Commands

| Command | Description |
| :--- | :--- |
| `/start` | Main menu. |
| `/check` | User details (by ID or by replying to a user message). |
| `/add [ID] [Amount]` | Add credit to a wallet. |
| `/addall [Amount]` | Add credit to every user. |
| `/allmembers` | List all users. |
| `/announce [Msg]` | Broadcast to every user. |

---

## 📂 Project Structure

* `Visual-Private-Network-Shipping-CardVersion.py` — card-to-card bot (main version, includes custom purchase and renewal flows).
* `Visual-Private-Network-Shipping.py` — ZarinPal gateway version.
* `admin_panel.py` — web admin panel served on port 9997 from inside the bot process.
* `db.py` — SQLite storage layer (`botdata.db`).
* `servers.py` — 3x-ui server configuration shared by every entry point.
* `xui_api.py` — synchronous 3x-ui API client used by the panel.
* `botdata.db` — created automatically at runtime; holds users, services, transactions, receipts, trials.

`botdata.db`, `*.log` and `__pycache__` are ignored by git and must never be committed.

---

## 🛡 Disclaimer

This tool is for educational purposes. Make sure you comply with your local laws and with the terms of service of your hosting provider.

## 📄 License

MIT
