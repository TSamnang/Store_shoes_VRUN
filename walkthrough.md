# Walkthrough - Secure Telegram Notification Implementation

We have added a secure, environment-variable-based Telegram notification system to send details to a Telegram bot when checkout is completed.

## Changes Made

### Configuration Files
- **[requirements.txt](file:///d:/year%203/sa/Store_shoes_VRUN/requirements.txt)**: Added `python-dotenv`.
- **[.env.example](file:///d:/year%203/sa/Store_shoes_VRUN/.env.example)**: Created a template showing how to configure Telegram env variables.
- **[.env](file:///d:/year%203/sa/Store_shoes_VRUN/.env)**: Created local configuration template (git-ignored, so it won't be pushed to GitHub or zipped).

### Backend Changes in [app.py](file:///d:/year%203/sa/Store_shoes_VRUN/app.py)
- **Imports**: Safely loaded `.env` environment variables using `load_dotenv` if available.
- **Helper Function**: Added `send_telegram_notification` to format the order details as clean HTML and POST to the Telegram API.
- **Trigger**: Called the notification logic inside the `/checkout` POST handler right after the order is written to MongoDB.

### Verification Tools
- **[test_telegram.py](file:///d:/year%203/sa/Store_shoes_VRUN/test_telegram.py)**: Created a standalone diagnostics script to test bot configuration without completing a full checkout.

---

## How to Set Up & Verify

### Step 1: Install Requirements
Run the following in your activated virtual environment terminal:
```bash
pip install -r requirements.txt
```

### Step 2: Configure Your Telegram Bot & Chat
1. Open Telegram and search for `@BotFather`. Start a chat and type `/newbot` to create a bot. Copy the generated **API Token**.
2. Open a chat with your new bot and click **Start / Send a Message**.
3. Retrieve your Chat ID. You can do this by sending a message to the bot, then opening the following URL in your web browser:
   `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   Look for the `"chat":{"id":XXXXXXXXX}` field in the JSON response.
4. Open the created [.env](file:///d:/year%203/sa/Store_shoes_VRUN/.env) file and enter your values:
   ```env
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   TELEGRAM_CHAT_ID=your_chat_id_here
   ```

### Step 3: Run the Test Script
In your terminal, run the following:
```bash
python test_telegram.py
```
If configured correctly, you will receive a test message directly in your Telegram!

### Step 4: Complete a checkout
Start the server, add items to your cart, fill in checkout details, and click **Complete Order**. You will receive an immediate Telegram update with the order ID, items list, customer profile, and total sum.
