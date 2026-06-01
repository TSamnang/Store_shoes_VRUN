# Implementation Plan - Dynamic Payment Methods Linked to User Accounts

Implement dynamic, secure, database-backed payment methods that persist in the MongoDB user document. This allows users to add, remove, and manage cards under their accounts (surviving browser clears), as well as select them seamlessly during checkout or save new cards entered during checkout.

## User Review Required

> [!NOTE]
> All card data is securely masked (e.g. `•••• •••• •••• 4242`) and CVVs are strictly verified in memory but never stored in the database. Only card brands, cardholder names, masked card numbers, and expiration dates are saved in MongoDB for compliance and security.

> [!IMPORTANT]
> The `/settings` page will now support addition of cards, deletion of cards, and setting default cards, with real-time feedback using flash notifications. The Checkout page will list the user's saved cards to speed up checkout.

## Proposed Changes

We will modify three key components of the application:
1. **User Settings Route (`/settings` in `app.py`)** - Handle card additions, setting default, and card deletions.
2. **Settings Template (`settings.html`)** - Dynamically list saved cards, open an elegant "Add Card" modal, and support form actions for deletion and setting default.
3. **Checkout Page (`checkout.html` and `/checkout` in `app.py`)** - Enable selection of saved cards or entering a new card, with an option to automatically save the new card to the user's account.

---

### Backend Components

#### [MODIFY] [app.py](file:///d:/year%203/sa/Store_shoes_VRUN/app.py)

- **Helper Functions / Logic**:
  - Add helper utility to parse the card brand based on card number (e.g., Visa, Mastercard, American Express, generic card).
- **Settings Route (`/settings`)**:
  - Add request handlers for three new POST actions:
    1. `add_payment_method`: Expects `cc_name`, `cc_number`, `cc_exp`, `cc_cvv`, and optional `set_default`. Validates fields, creates a card dictionary with a unique ID (`pm_xxxxxx`), masks the card number, detects the brand, and pushes it to `db.users`.
    2. `delete_payment_method`: Expects `payment_method_id`. Pulls the card from the list. If it was the default card, sets the next remaining card as default.
    3. `set_default_payment_method`: Expects `payment_method_id`. Toggles `is_default` for all card documents of the user.
- **Checkout Route (`/checkout`)**:
  - Enhance POST request processing:
    - If `payment == 'Card'`, inspect `selected_card_id`.
    - If a saved card is selected, use that saved card's masked number for the order document's payment method description.
    - If a new card is used:
      - Mask the entered card number.
      - Save card details to order history.
      - If `save_card` checkbox is checked, save the card to the user's account under `db.users`.

---

### Frontend Components

#### [MODIFY] [settings.html](file:///d:/year%203/sa/Store_shoes_VRUN/templates/front/settings.html)

- Include standard flash messages template to show operation feedback.
- Render dynamic list of cards from `current_user.get('payment_methods', [])` with brand icons, masked card numbers, expiration dates, and cardholder names.
- Create form elements to handle "Delete Card" and "Set Default" actions.
- Add a stunning, dark-themed Bootstrap modal `addCardModal` for credit card input (Name, Card Number with 15/16 digit pattern, Expiry Date with `MM/YY` pattern, and CVV).

#### [MODIFY] [checkout.html](file:///d:/year%203/sa/Store_shoes_VRUN/templates/front/checkout.html)

- If the user has saved cards, show an interactive selector displaying saved cards with brand icons.
- Include a "Use a New Card" option in the list.
- Add JS toggle: when a saved card is selected, hide the manual card entry details; when "Use a New Card" is selected, show card fields and include a "Save this card to my account" checkbox.

---

## Verification Plan

### Automated Tests
We can verify the changes by running standard Flask request workflows:
1. Ensure the Flask dev server runs with zero startup errors.
2. Sign in as a test customer.

### Manual Verification
1. **Adding Cards**: Navigate to Settings -> Payment Methods. Click "Add Card". Enter correct card details. Click Add and verify that the card appears with the correct brand icon, masked representation, and is set as Default.
2. **Adding Multiple Cards**: Add a second card. Verify it displays correctly.
3. **Setting Default**: Click "Set Default" on the second card. Confirm it shifts the default badge to the new card and persists on page refresh.
4. **Deleting Card**: Click Delete on the default card. Verify it removes the card and shifts the default badge to the remaining card.
5. **Checkout Integration**: Go to the shopping cart, proceed to Checkout. Verify saved cards are listed with the default one active.
6. **Checkout with Saved Card**: Select the saved card, fill in shipping address, click Complete Purchase. Verify that the order receipt and order documents in the db correctly identify the specific card used.
7. **Checkout with New Card and Save**: Check out with a new card and choose "Save this card". Check Settings to verify it has been added successfully.
