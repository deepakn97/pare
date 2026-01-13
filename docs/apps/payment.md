# Stateful Payment App

`pas.apps.payment.app.StatefulPaymentApp` extends PAS navigation with a Payment application that manages payments, requests, transactions, contacts, and payment methods. It launches in `HomeView` and navigates between different views based on user actions and completed backend operations.

## Navigation States

### HomeView

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `get_feed()` | `StatefulPaymentApp.get_feed()` | List of feed items with transaction details, sorted by date (newest first) | Remains in `HomeView` |
| `get_balance()` | `StatefulPaymentApp.get_balance()` | Dictionary containing balance amount and currency | Remains in `HomeView` |
| `view_contacts()` | `StatefulPaymentApp.list_contacts()` | List of user's Payment contacts with names and usernames | Completed event transitions to `ContactListView` |
| `view_transactions()` | `StatefulPaymentApp.list_transactions()` | List of all user's transactions sorted by date | Completed event transitions to `TransactionListView` |
| `view_payment_methods()` | `StatefulPaymentApp.list_payment_methods()` | List of linked payment methods (bank accounts, cards) | Completed event transitions to `PaymentMethodsView` |

### PaymentView

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `search_users(query: str)` | `StatefulPaymentApp.search_users(query=query)` | List of matching user profiles | Remains in `PaymentView` |
| `get_user(user_id: str)` | `StatefulPaymentApp.get_user(user_id=user_id)` | User profile information including name, username, and profile picture | Remains in `PaymentView` |
| `send_payment(recipient_id: str, amount: float, note: str, privacy: str = "friends", payment_method_id: str | None = None)` | `StatefulPaymentApp.send_payment(...)` | Transaction ID of the completed payment | Completed event transitions to `TransactionDetail(transaction_id)` |
| `request_payment(recipient_id: str, amount: float, note: str, privacy: str = "friends")` | `StatefulPaymentApp.request_payment(...)` | Request ID of the created payment request | Completed event transitions to `TransactionDetail(transaction_id)` |

### TransactionListView

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_transactions(filter_type: str | None = None)` | `StatefulPaymentApp.list_transactions(filter_type=filter_type)` | List of transaction summaries sorted by date (newest first) | Remains in `TransactionListView` |
| `open_transaction(transaction_id: str)` | `StatefulPaymentApp.get_transaction(transaction_id=transaction_id)` | Complete transaction details including participants, amount, and status | Completed event transitions to `TransactionDetail(transaction_id)` |
| `list_pending_requests()` | `StatefulPaymentApp.list_pending_requests()` | List of pending requests that need action | Remains in `TransactionListView` |

### TransactionDetail

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `get_transaction(transaction_id: str)` | `StatefulPaymentApp.get_transaction(transaction_id=transaction_id)` | Complete transaction information including sender, recipient, amount, note, status, and timestamps | Remains in `TransactionDetail` |
| `pay_request(request_id: str, payment_method_id: str | None = None)` | `StatefulPaymentApp.pay_request(request_id=request_id, payment_method_id=payment_method_id)` | Transaction ID of the completed payment | Remains in `TransactionDetail` (shows updated status) |
| `decline_request(request_id: str)` | `StatefulPaymentApp.decline_request(request_id=request_id)` | Confirmation message that request was declined | Completed event transitions to `TransactionListView` |
| `cancel_request(request_id: str)` | `StatefulPaymentApp.cancel_request(request_id=request_id)` | Confirmation message that request was cancelled | Completed event transitions to `TransactionListView` |

### ContactListView

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_contacts()` | `StatefulPaymentApp.list_contacts()` | List of contact profiles with names and usernames | Remains in `ContactListView` |
| `search_users(query: str)` | `StatefulPaymentApp.search_users(query=query)` | List of matching user profiles | Remains in `ContactListView` |
| `open_contact(user_id: str)` | `StatefulPaymentApp.get_user_profile(user_id=user_id)` | User profile with recent transaction history | Completed event transitions to `UserProfile(user_id)` |
| `add_friend(user_id: str)` | `StatefulPaymentApp.add_friend(user_id=user_id)` | Confirmation message that friend request was sent | Remains in `ContactListView` |
| `remove_friend(user_id: str)` | `StatefulPaymentApp.remove_friend(user_id=user_id)` | Confirmation message that friend was removed | Remains in `ContactListView` |

### UserProfile

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `get_user_profile(user_id: str)` | `StatefulPaymentApp.get_user_profile(user_id=user_id)` | User profile including name, username, friend status, and recent transaction history with this user | Remains in `UserProfile` |
| `get_transaction_history(user_id: str)` | `StatefulPaymentApp.get_transaction_history(user_id=user_id)` | List of transactions between current user and specified user | Remains in `UserProfile` |
| `pay_user(user_id: str)` | Internal navigation helper | None | Transitions to `PaymentView(recipient_id=user_id)` |

### PaymentMethodsView

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_payment_methods()` | `StatefulPaymentApp.list_payment_methods()` | List of payment methods including bank accounts and cards with masked numbers and verification status | Remains in `PaymentMethodsView` |
| `add_bank_account(account_number: str, routing_number: str, account_type: str)` | `StatefulPaymentApp.add_bank_account(...)` | Payment method ID of the newly added account | Remains in `PaymentMethodsView` |
| `add_card(card_number: str, expiry: str, cvv: str, billing_zip: str)` | `StatefulPaymentApp.add_card(...)` | Payment method ID of the newly added card | Remains in `PaymentMethodsView` |
| `set_default_payment_method(payment_method_id: str)` | `StatefulPaymentApp.set_default_payment_method(payment_method_id=payment_method_id)` | Confirmation message with the updated default method | Remains in `PaymentMethodsView` |
| `remove_payment_method(payment_method_id: str)` | `StatefulPaymentApp.remove_payment_method(payment_method_id=payment_method_id)` | Confirmation message that payment method was removed | Remains in `PaymentMethodsView` |
| `view_transfer()` | `StatefulPaymentApp.get_balance()` | Current balance information | Completed event transitions to `TransferView` |

### TransferView

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `get_balance()` | `StatefulPaymentApp.get_balance()` | Dictionary containing balance amount and available transfer options | Remains in `TransferView` |
| `transfer_to_bank(amount: float, bank_account_id: str, speed: str = "standard")` | `StatefulPaymentApp.transfer_to_bank(amount=amount, bank_account_id=bank_account_id, speed=speed)` | Confirmation message with transfer amount and estimated completion time | Remains in `TransferView` |
| `add_money_from_bank(amount: float, bank_account_id: str)` | `StatefulPaymentApp.add_money_from_bank(amount=amount, bank_account_id=bank_account_id)` | Confirmation message with transfer amount and estimated completion time | Remains in `TransferView` |

## Navigation Helpers

- `go_back()` appears automatically when navigation history exists and pops to the prior screen, returning messages such as `Navigated back to the state HomeView`.
- All forward transitions are triggered by completed Meta-ARE events via `handle_state_transition()`.
- `PaymentView` can be initialized with a pre-selected `recipient_id` when navigating from `UserProfile`.
- `TransactionDetail` remains in place after `pay_request` to show the updated transaction status, but transitions back to `TransactionListView` after declining or cancelling requests.
