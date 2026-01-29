"""State definitions for the stateful Payment app."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from are.simulation.types import OperationType, disable_events

from pas.apps.core import AppState
from pas.apps.tool_decorators import pas_event_registered, user_tool

if TYPE_CHECKING:
    from pas.apps.payment.app import StatefulPaymentApp


class HomeView(AppState):
    """Home state for viewing feed and navigating to main features.

    Users can view their transaction feed, access payment features,
    and navigate to other sections of the app.
    """

    def on_enter(self) -> None:
        """Called when entering home view state."""
        pass

    def on_exit(self) -> None:
        """Called when leaving home view state."""
        pass

    @user_tool()
    @pas_event_registered()
    def get_feed(self) -> list[dict[str, Any]]:
        """View transaction feed showing recent payments and requests.

        Returns:
            List of feed items with transaction details, sorted by date (newest first).
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).get_feed()

    @user_tool()
    @pas_event_registered()
    def get_balance(self) -> dict[str, Any]:
        """Get current Payment balance.

        Returns:
            Dictionary containing balance amount and currency.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).get_balance()

    @user_tool()
    @pas_event_registered()
    def view_contacts(self) -> list[dict[str, Any]]:
        """Navigate to contacts list.

        Returns:
            List of user's Payment contacts with names and usernames.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).list_contacts()

    @user_tool()
    @pas_event_registered()
    def view_transactions(self) -> list[dict[str, Any]]:
        """Navigate to transaction history.

        Returns:
            List of all user's transactions sorted by date.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).list_transactions()

    @user_tool()
    @pas_event_registered()
    def view_payment_methods(self) -> list[dict[str, Any]]:
        """Navigate to payment methods management.

        Returns:
            List of linked payment methods (bank accounts, cards).
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).list_payment_methods()


class PaymentView(AppState):
    """State for sending or requesting money.

    Users can select recipients, enter amounts, add notes, and choose
    whether to pay or request money.

    Attributes:
        recipient_id: Optional pre-selected recipient ID.
    """

    def __init__(self, recipient_id: str | None = None) -> None:
        """Initialize payment view state.

        Args:
            recipient_id: Optional unique identifier of pre-selected recipient.
        """
        super().__init__()
        self.recipient_id = recipient_id

    def on_enter(self) -> None:
        """Called when entering payment view state."""
        pass

    def on_exit(self) -> None:
        """Called when leaving payment view state."""
        pass

    @user_tool()
    @pas_event_registered()
    def search_users(self, query: str) -> list[dict[str, Any]]:
        """Search for Payment users to pay or request from.

        Args:
            query: Search term to match against username, name, or phone.

        Returns:
            List of matching user profiles.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).search_users(query)

    @user_tool()
    @pas_event_registered()
    def get_user(self, user_id: str) -> dict[str, Any]:
        """Get details of a specific user.

        Args:
            user_id: Unique identifier of the user.

        Returns:
            User profile information including name, username, and profile picture.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).get_user(user_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def send_payment(
        self,
        recipient_id: str,
        amount: float,
        note: str,
        privacy: str = "friends",
        payment_method_id: str | None = None,
    ) -> str:
        """Send money to another user.

        Args:
            recipient_id: Unique identifier of the recipient.
            amount: Amount to send in USD.
            note: Payment description or message.
            privacy: Privacy setting ("public", "friends", "private").
            payment_method_id: Optional specific payment method to use.

        Returns:
            Transaction ID of the completed payment.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).send_payment(
                recipient_id, amount, note, privacy, payment_method_id
            )

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def request_payment(
        self,
        recipient_id: str,
        amount: float,
        note: str,
        privacy: str = "friends",
    ) -> str:
        """Request money from another user.

        Args:
            recipient_id: Unique identifier of the person to request from.
            amount: Amount to request in USD.
            note: Request description or reason.
            privacy: Privacy setting ("public", "friends", "private").

        Returns:
            Request ID of the created payment request.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).request_payment(recipient_id, amount, note, privacy)


class TransactionListView(AppState):
    """State for viewing transaction history.

    Users can view all their past transactions, filter by type,
    and select individual transactions to view details.
    """

    def on_enter(self) -> None:
        """Called when entering transaction list state."""
        pass

    def on_exit(self) -> None:
        """Called when leaving transaction list state."""
        pass

    @user_tool()
    @pas_event_registered()
    def list_transactions(self, filter_type: str | None = None) -> list[dict[str, Any]]:
        """List user's transaction history.

        Args:
            filter_type: Optional filter ("sent", "received", "pending", "all").

        Returns:
            List of transaction summaries sorted by date (newest first).
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).list_transactions(filter_type)

    @user_tool()
    @pas_event_registered()
    def open_transaction(self, transaction_id: str) -> dict[str, Any]:
        """Open detail page for a specific transaction.

        Args:
            transaction_id: Unique identifier of the transaction.

        Returns:
            Complete transaction details including participants, amount, and status.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).get_transaction(transaction_id)

    @user_tool()
    @pas_event_registered()
    def list_pending_requests(self) -> list[dict[str, Any]]:
        """View all pending payment requests (sent and received).

        Returns:
            List of pending requests that need action.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).list_pending_requests()


class TransactionDetail(AppState):
    """State for viewing a specific transaction's details.

    Users can view complete transaction information, refund payments,
    or take action on pending requests.

    Attributes:
        transaction_id: ID of the transaction being viewed.
    """

    def __init__(self, transaction_id: str) -> None:
        """Initialize transaction detail state.

        Args:
            transaction_id: Unique identifier of the transaction.
        """
        super().__init__()
        self.transaction_id = transaction_id

    def on_enter(self) -> None:
        """Called when entering transaction detail state."""
        pass

    def on_exit(self) -> None:
        """Called when leaving transaction detail state."""
        pass

    @user_tool()
    @pas_event_registered()
    def get_transaction(self, transaction_id: str) -> dict[str, Any]:
        """Fetch full transaction details.

        Args:
            transaction_id: Unique identifier of the transaction.

        Returns:
            Complete transaction information including sender, recipient,
            amount, note, status, and timestamps.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).get_transaction(transaction_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def pay_request(self, request_id: str, payment_method_id: str | None = None) -> str:
        """Pay a pending payment request.

        Args:
            request_id: Unique identifier of the request to pay.
            payment_method_id: Optional specific payment method to use.

        Returns:
            Transaction ID of the completed payment.

        Note:
            Only pending incoming requests can be paid.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).pay_request(request_id, payment_method_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def decline_request(self, request_id: str) -> str:
        """Decline a pending payment request.

        Args:
            request_id: Unique identifier of the request to decline.

        Returns:
            Confirmation message that request was declined.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).decline_request(request_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def cancel_request(self, request_id: str) -> str:
        """Cancel a pending outgoing payment request.

        Args:
            request_id: Unique identifier of the request to cancel.

        Returns:
            Confirmation message that request was cancelled.

        Note:
            Only pending outgoing requests can be cancelled.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).cancel_request(request_id)


class ContactListView(AppState):
    """State for managing contacts and friends.

    Users can view their contacts, search for new users,
    and manage friend connections.
    """

    def on_enter(self) -> None:
        """Called when entering contact list state."""
        pass

    def on_exit(self) -> None:
        """Called when leaving contact list state."""
        pass

    @user_tool()
    @pas_event_registered()
    def list_contacts(self) -> list[dict[str, Any]]:
        """List all user's Payment contacts.

        Returns:
            List of contact profiles with names and usernames.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).list_contacts()

    @user_tool()
    @pas_event_registered()
    def search_users(self, query: str) -> list[dict[str, Any]]:
        """Search for Payment users by name, username, or phone.

        Args:
            query: Search term to find users.

        Returns:
            List of matching user profiles.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).search_users(query)

    @user_tool()
    @pas_event_registered()
    def open_contact(self, user_id: str) -> dict[str, Any]:
        """Open a contact's profile page.

        Args:
            user_id: Unique identifier of the contact.

        Returns:
            User profile with recent transaction history.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).get_user_profile(user_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def add_friend(self, user_id: str) -> str:
        """Send friend request to a user.

        Args:
            user_id: Unique identifier of the user to add.

        Returns:
            Confirmation message that friend request was sent.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).add_friend(user_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def remove_friend(self, user_id: str) -> str:
        """Remove a user from friends list.

        Args:
            user_id: Unique identifier of the friend to remove.

        Returns:
            Confirmation message that friend was removed.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).remove_friend(user_id)


class UserProfile(AppState):
    """State for viewing a specific user's profile.

    Users can view profile information, recent transactions with this user,
    and initiate payments or requests.

    Attributes:
        user_id: ID of the user profile being viewed.
    """

    def __init__(self, user_id: str) -> None:
        """Initialize user profile state.

        Args:
            user_id: Unique identifier of the user.
        """
        super().__init__()
        self.user_id = user_id

    def on_enter(self) -> None:
        """Called when entering user profile state."""
        pass

    def on_exit(self) -> None:
        """Called when leaving user profile state."""
        pass

    @user_tool()
    @pas_event_registered()
    def get_user_profile(self, user_id: str) -> dict[str, Any]:
        """Get detailed user profile information.

        Args:
            user_id: Unique identifier of the user.

        Returns:
            User profile including name, username, friend status, and recent
            transaction history with this user.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).get_user_profile(user_id)

    @user_tool()
    @pas_event_registered()
    def get_transaction_history(self, user_id: str) -> list[dict[str, Any]]:
        """Get transaction history with this user.

        Args:
            user_id: Unique identifier of the user.

        Returns:
            List of transactions between current user and specified user.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).get_transaction_history(user_id)

    @user_tool()
    @pas_event_registered()
    def pay_user(self, user_id: str) -> None:
        """Navigate to payment view with this user pre-selected.

        Args:
            user_id: Unique identifier of the user to pay.

        Returns:
            None (navigates to PaymentView state via transition logic).
        """
        pass


class PaymentMethodsView(AppState):
    """State for managing payment methods.

    Users can view linked bank accounts and cards, add new payment methods,
    set default methods, and remove existing ones.
    """

    def on_enter(self) -> None:
        """Called when entering payment methods state."""
        pass

    def on_exit(self) -> None:
        """Called when leaving payment methods state."""
        pass

    @user_tool()
    @pas_event_registered()
    def list_payment_methods(self) -> list[dict[str, Any]]:
        """List all linked payment methods.

        Returns:
            List of payment methods including bank accounts and cards
            with masked numbers and verification status.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).list_payment_methods()

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def add_bank_account(self, account_number: str, routing_number: str, account_type: str) -> str:
        """Link a new bank account.

        Args:
            account_number: Bank account number.
            routing_number: Bank routing number.
            account_type: Type of account ("checking" or "savings").

        Returns:
            Payment method ID of the newly added account.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).add_bank_account(account_number, routing_number, account_type)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def add_card(self, card_number: str, expiry: str, cvv: str, billing_zip: str) -> str:
        """Link a new debit or credit card.

        Args:
            card_number: Card number.
            expiry: Expiration date in MM/YY format.
            cvv: Card security code.
            billing_zip: Billing ZIP code.

        Returns:
            Payment method ID of the newly added card.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).add_card(card_number, expiry, cvv, billing_zip)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def set_default_payment_method(self, payment_method_id: str) -> str:
        """Set a payment method as default.

        Args:
            payment_method_id: Unique identifier of the payment method.

        Returns:
            Confirmation message with the updated default method.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).set_default_payment_method(payment_method_id)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def remove_payment_method(self, payment_method_id: str) -> str:
        """Remove a linked payment method.

        Args:
            payment_method_id: Unique identifier of the payment method to remove.

        Returns:
            Confirmation message that payment method was removed.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).remove_payment_method(payment_method_id)

    @user_tool()
    @pas_event_registered()
    def view_transfer(self) -> dict[str, Any]:
        """Navigate to transfer view for transferring money to/from bank accounts.

        Returns:
            Current balance information.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).get_balance()


class TransferView(AppState):
    """State for transferring money to/from bank accounts.

    Users can transfer their Payment balance to linked bank accounts
    or add money from bank accounts to their Payment balance.
    """

    def on_enter(self) -> None:
        """Called when entering transfer view state."""
        pass

    def on_exit(self) -> None:
        """Called when leaving transfer view state."""
        pass

    @user_tool()
    @pas_event_registered()
    def get_balance(self) -> dict[str, Any]:
        """Get current Payment balance.

        Returns:
            Dictionary containing balance amount and available transfer options.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).get_balance()

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def transfer_to_bank(self, amount: float, bank_account_id: str, speed: str = "standard") -> str:
        """Transfer money from Payment to bank account.

        Args:
            amount: Amount to transfer in USD.
            bank_account_id: Unique identifier of destination bank account.
            speed: Transfer speed ("standard" for 1-3 days, "instant" for immediate).

        Returns:
            Transfer ID and estimated completion time.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).transfer_to_bank(amount, bank_account_id, speed)

    @user_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def add_money_from_bank(self, amount: float, bank_account_id: str) -> str:
        """Add money from bank account to Payment balance.

        Args:
            amount: Amount to add in USD.
            bank_account_id: Unique identifier of source bank account.

        Returns:
            Transfer ID and estimated completion time.
        """
        with disable_events():
            return cast("StatefulPaymentApp", self.app).add_money_from_bank(amount, bank_account_id)
