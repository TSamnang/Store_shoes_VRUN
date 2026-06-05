# Implementation Plan - Secure Telegram Bot Notification for Completed Orders

Introduce a Telegram notification feature that sends a message containing order details to a configured Telegram chat whenever a customer successfully completes checkout. The credentials will be loaded from a `.env` file to keep the integration safe when pushing to GitHub or zipping the code.

## User Review Required

> [!IMPORTANT]
> The Telegram Bot configuration will be kept secure by reading from environment variables.
> You will need to create a **Telegram Bot** and get your **Chat ID** to enable notifications.
> We will create a `.env` file in the project folder (which is already ignored by Git) to store these credentials.

## Proposed Changes

### Configuration & Dependencies

#### [MODIFY] [requirements.txt](file:///d:/year%203/sa/Store_shoes_VRUN/requirements.txt)
- Add `python-dotenv` to list of requirements to enable loading configuration from a `.env` file.

#### [NEW] [.env.example](file:///d:/year%203/sa/Store_shoes_VRUN/.env.example)
- Create a template env configuration file with instructions on how to set up the Telegram Bot token and Chat ID.

#### [NEW] [.env](file:///d:/year%203/sa/Store_shoes_VRUN/.env)
- Create a local, git-ignored `.env` file containing placeholders for local setup.

---

### Backend Logic

#### [MODIFY] [app.py](file:///d:/year%203/sa/Store_shoes_VRUN/app.py)
- Import and initialize `dotenv` at the top of the file using a try-except fallback block (so that missing packages won't crash the server).
- Create a `send_telegram_notification(order_id, user, shipping_address, shipping_method, shipping_cost, total, items)` helper function using Python's native `urllib` module (no extra external HTTP libraries needed).
- Call this helper inside the `checkout()` route after the order is successfully created in MongoDB (line ~788).

---

## Code Drafts

### Telegram Message Format
The bot will send a message formatted like this:
```html
<b>📦 New Order Received!</b>

<b>Order ID:</b> <code>123456789abcdef</code>
<b>Customer:</b> john_doe (john@example.com)
<b>Shipping Method:</b> Standard ($5.00)
<b>Address:</b> 123 Street, Phnom Penh
<b>Total Amount:</b> $185.00

<b>🛒 Items Ordered:</b>
• 1x Air Jordan 1 Retro High OG - $180.00
```

---

## Verification Plan

### Manual Verification
1. Configure `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` inside your local `.env`.
2. Start/Restart the Flask server.
3. Add a product to the cart, proceed to checkout, and complete the order.
4. Verify that a message is successfully received on Telegram containing the details of the order.
