# Walkthrough - Dynamic Payment Methods & Autofill

We have successfully replaced all static/mocked payment method behaviors in the application with a database-backed, real-world credit card management system stored securely under each user's account in MongoDB. This ensures that payment methods persist even if the browser cookies or local storage are cleared!

---

## 🛠️ Key Changes Made

### 1. Backend Business Logic (`app.py`)
- **Card Brand Parsing**: Added `detect_card_brand` to parse entered numbers and identify card brands (Visa, Mastercard, Amex, Discover, JCB) by BIN prefixes.
- **Dynamic `/settings` Endpoints**:
  - `add_payment_method`: Adds a card with custom validations. Encodes and masks the card number (e.g. `•••• •••• •••• 4242`), generates a unique ID, and appends it to the user's `payment_methods` array.
  - `delete_payment_method`: Safely removes a card and automatically reassigns default status to the remaining card if the deleted card was default.
  - `set_default_payment_method`: Toggles default status.
- **Integrated `/checkout` Endpoint**:
  - Handles selectable saved cards. When a saved card is selected, its details are loaded.
  - If a new card is used and "Save card to my account" is checked, the card is instantly saved to their account.

### 2. Settings User Interface (`settings.html`)
- Replaced static HTML mock cards with a dynamic loop over `current_user.get('payment_methods', [])`.
- Added brand gradient backgrounds to match Visa, Mastercard, Amex, or standard cards.
- Integrated an elegant, premium, dark-themed Bootstrap modal **"Add Card"** with input masks.
- Included flash message feedback for success and error alerts.

### 3. Premium Autofill & Checkout Page Enhancements (`checkout.html`)
- Renders user's saved cards at checkout with the default card pre-selected.
- Added a **"Use a New Card"** quick-toggle block.
- **Autofill Mechanism**:
  - When the user selects a saved card, the credit card details form (`cc-name`, `cc-number`, `cc-exp`, `cc-cvv`) automatically populates with the stored credentials in real-time.
  - Form fields are set as `readonly` to prevent editing, and their `required` validation statuses are temporarily disabled.
  - The "Save this card" checkbox container hides automatically since it is already stored.
  - When the user selects "Use a New Card", fields clear immediately, edit permissions restore, inputs require validation, and the save checkbox appears.

---

## 🧪 How to Verify & Test

1. **Start the Flask Server**:
   ```bash
   flask run --debug
   ```
2. **Log In to a Customer Account**:
   - Access the website and log in.
3. **Add Credit Cards**:
   - Go to **Settings** -> **Payment Methods**.
   - Click **Add Card**.
   - Enter card details:
     - *Visa*: starting with `4` (e.g. `4242424242424242`)
     - *Mastercard*: starting with `5` (e.g. `5123456789012345`)
   - Check the **Set as default** option. Click Add.
   - Verify the card appears with the correct brand colors, masking, and the yellow "Default" badge.
4. **Delete and Default Toggles**:
   - Add another card.
   - Click **Set Default** on the second card and refresh. Verify the status updates.
   - Click the Trash icon to delete a card. Confirm it deletes from the database.
5. **Autofill Quick Pay Checkout**:
   - Add shoes to your cart and go to **Checkout**.
   - Select your saved card directly.
   - **Observe Autofill**: Watch the credit card input fields automatically fill up with your name, masked number, expiry date, and `•••` placeholder CVV. The fields will set as read-only.
   - Select **Use a New Card**. Watch the fields clear immediately and become editable.
   - Click **Complete Purchase** and check the Order Receipt to confirm the card name is listed!
