"""Stateful Payment app with PAS navigation."""

from __future__ import annotations

import contextlib
import logging
import textwrap
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from are.simulation.tool_utils import OperationType, app_tool, data_tool
from are.simulation.types import EventType
from are.simulation.utils import get_state_dict, uuid_hex
from are.simulation.utils.type_utils import type_check

if TYPE_CHECKING:
    from are.simulation.types import CompletedEvent

from pas.apps.core import StatefulApp
from pas.apps.payment.states import (
    ContactListView,
    HomeView,
    PaymentMethodsView,
    PaymentView,
    TransactionDetail,
    TransactionListView,
    TransferView,
    UserProfile,
)
from pas.apps.tool_decorators import pas_event_registered

logger = logging.getLogger(__name__)


@dataclass
class PaymentUser:
    """Payment user profile model."""

    user_id: str
    username: str
    display_name: str
    phone: str = ""
    email: str = ""
    profile_picture: str = ""
    is_friend: bool = False

    def __str__(self) -> str:
        return textwrap.dedent(
            f"""
            ID: {self.user_id}
            Username: @{self.username}
            Name: {self.display_name}
            Phone: {self.phone}
            Email: {self.email}
            Friend: {self.is_friend}
            """
        )

    def get_state(self) -> dict[str, Any]:
        """Serialize user state."""
        return get_state_dict(
            self, ["user_id", "username", "display_name", "phone", "email", "profile_picture", "is_friend"]
        )

    def load_state(self, state_dict: dict[str, Any]) -> None:
        """Restore user from serialized state."""
        self.user_id = state_dict["user_id"]
        self.username = state_dict["username"]
        self.display_name = state_dict["display_name"]
        self.phone = state_dict.get("phone", "")
        self.email = state_dict.get("email", "")
        self.profile_picture = state_dict.get("profile_picture", "")
        self.is_friend = state_dict.get("is_friend", False)


@dataclass
class PaymentMethod:
    """Payment method model (bank account or card)."""

    payment_method_id: str
    method_type: str  # "bank_account" or "card"
    last_four: str
    name: str = ""
    is_default: bool = False
    verified: bool = False

    def __str__(self) -> str:
        return textwrap.dedent(
            f"""
            ID: {self.payment_method_id}
            Type: {self.method_type}
            Name: {self.name}
            Last Four: ****{self.last_four}
            Default: {self.is_default}
            Verified: {self.verified}
            """
        )

    def get_state(self) -> dict[str, Any]:
        """Serialize payment method state."""
        return get_state_dict(self, ["payment_method_id", "method_type", "last_four", "name", "is_default", "verified"])

    def load_state(self, state_dict: dict[str, Any]) -> None:
        """Restore payment method from serialized state."""
        self.payment_method_id = state_dict["payment_method_id"]
        self.method_type = state_dict["method_type"]
        self.last_four = state_dict["last_four"]
        self.name = state_dict.get("name", "")
        self.is_default = state_dict.get("is_default", False)
        self.verified = state_dict.get("verified", False)


@dataclass
class Transaction:
    """Transaction model for payments and requests."""

    transaction_id: str
    transaction_type: str  # "payment", "request", "transfer"
    sender_id: str
    recipient_id: str
    amount: float
    note: str
    status: str  # "completed", "pending", "cancelled", "declined"
    privacy: str  # "public", "friends", "private"
    created_at: datetime | float
    payment_method_id: str | None = None

    def __str__(self) -> str:
        created_str = (
            datetime.fromtimestamp(self.created_at, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
            if isinstance(self.created_at, (int, float))
            else str(self.created_at)
        )
        return textwrap.dedent(
            f"""
            ID: {self.transaction_id}
            Type: {self.transaction_type}
            From: {self.sender_id}
            To: {self.recipient_id}
            Amount: ${self.amount:.2f}
            Note: {self.note}
            Status: {self.status}
            Created: {created_str}
            """
        )

    def get_state(self) -> dict[str, Any]:
        """Serialize transaction state."""
        return {
            "transaction_id": self.transaction_id,
            "transaction_type": self.transaction_type,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "amount": self.amount,
            "note": self.note,
            "status": self.status,
            "privacy": self.privacy,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "payment_method_id": self.payment_method_id,
        }

    def load_state(self, state_dict: dict[str, Any]) -> None:
        """Restore transaction from serialized state."""
        self.transaction_id = state_dict["transaction_id"]
        self.transaction_type = state_dict["transaction_type"]
        self.sender_id = state_dict["sender_id"]
        self.recipient_id = state_dict["recipient_id"]
        self.amount = state_dict["amount"]
        self.note = state_dict["note"]
        self.status = state_dict["status"]
        self.privacy = state_dict["privacy"]
        self.payment_method_id = state_dict.get("payment_method_id")

        if isinstance(state_dict["created_at"], str):
            try:
                self.created_at = datetime.fromisoformat(state_dict["created_at"])
            except ValueError:
                # If ISO format parsing fails, try alternative format and convert to timestamp
                try:
                    dt = datetime.strptime(state_dict["created_at"], "%Y-%m-%d %H:%M:%S")
                    self.created_at = dt.replace(tzinfo=UTC).timestamp()
                except ValueError:
                    # Last resort: use current timestamp
                    self.created_at = datetime.now(UTC).timestamp()
        else:
            self.created_at = state_dict["created_at"]


@dataclass
class StatefulPaymentApp(StatefulApp):
    """A Payment application that manages payments, requests, transactions, contacts, and payment methods with state-aware transitions.

    Key Features:
    - User Management: Search users, manage contacts and friends
    - Payment Management: Send money, request money with privacy settings
    - Transaction Management: View history, pay/decline requests, cancel requests
    - Payment Methods: Add/remove bank accounts and cards, set defaults
    - Balance Management: View balance, transfer to/from bank accounts
    - Feed: View public/friends transaction feed

    Notes:
    - Current user is identified by user_id
    - All monetary values are in USD
    - Transaction IDs are automatically generated
    - Privacy settings: "public", "friends", "private"
    """

    name: str | None = None
    user_id: str = ""  # Current user ID
    users: dict[str, PaymentUser] = field(default_factory=dict)
    transactions: dict[str, Transaction] = field(default_factory=dict)
    payment_methods: dict[str, PaymentMethod] = field(default_factory=dict)
    balance: float = 0.0

    def __post_init__(self) -> None:
        """Initialize the Payment app."""
        super().__init__(self.name or "payment")
        self.load_root_state()

    def create_root_state(self) -> HomeView:
        """Create the root navigation state."""
        return HomeView()

    def reset(self) -> None:
        """Reset the app to empty state."""
        super().reset()
        self.users.clear()
        self.transactions.clear()
        self.payment_methods.clear()
        self.balance = 0.0

    def _get_user_by_id(self, user_id: str) -> PaymentUser:
        """Get user by ID with validation."""
        if user_id not in self.users:
            raise KeyError(f"User {user_id} not found")
        return self.users[user_id]

    def _get_transaction_by_id(self, transaction_id: str) -> Transaction:
        """Get transaction by ID with validation."""
        if transaction_id not in self.transactions:
            raise KeyError(f"Transaction {transaction_id} not found")
        return self.transactions[transaction_id]

    def _get_payment_method_by_id(self, payment_method_id: str) -> PaymentMethod:
        """Get payment method by ID with validation."""
        if payment_method_id not in self.payment_methods:
            raise KeyError(f"Payment method {payment_method_id} not found")
        return self.payment_methods[payment_method_id]

    @type_check
    @data_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def create_user(
        self,
        username: str,
        display_name: str,
        phone: str = "",
        email: str = "",
        is_friend: bool = False,
    ) -> str:
        """Create a new Payment user."""
        if not isinstance(username, str) or len(username.strip()) == 0:
            raise ValueError("Username must be non-empty string")
        if not isinstance(display_name, str) or len(display_name.strip()) == 0:
            raise ValueError("Display name must be non-empty string")

        user_id = uuid_hex(self.rng)
        user = PaymentUser(
            user_id=user_id,
            username=username,
            display_name=display_name,
            phone=phone,
            email=email,
            is_friend=is_friend,
        )
        self.users[user_id] = user
        return user_id

    @type_check
    @data_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def set_current_user(self, user_id: str) -> str:
        """Set the current user for the app session."""
        if user_id not in self.users:
            raise KeyError(f"User {user_id} not found")
        self.user_id = user_id
        return f"Current user set to {self.users[user_id].display_name}"

    @type_check
    @data_tool()
    @pas_event_registered(operation_type=OperationType.WRITE)
    def create_transaction_with_time(
        self,
        transaction_type: str,
        sender_id: str,
        recipient_id: str,
        amount: float,
        note: str,
        status: str,
        created_at: str,
        privacy: str = "friends",
        payment_method_id: str | None = None,
    ) -> str:
        """Create a transaction with specific timestamp."""
        try:
            timestamp = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).timestamp()
        except ValueError as e:
            raise ValueError("Invalid datetime format. Use YYYY-MM-DD HH:MM:SS") from e

        if transaction_type not in ["payment", "request", "transfer"]:
            raise ValueError("Transaction type must be 'payment', 'request', or 'transfer'")
        if status not in ["completed", "pending", "cancelled", "declined"]:
            raise ValueError("Status must be 'completed', 'pending', 'cancelled', or 'declined'")
        if privacy not in ["public", "friends", "private"]:
            raise ValueError("Privacy must be 'public', 'friends', or 'private'")
        if amount <= 0:
            raise ValueError("Amount must be positive")

        transaction_id = uuid_hex(self.rng)
        transaction = Transaction(
            transaction_id=transaction_id,
            transaction_type=transaction_type,
            sender_id=sender_id,
            recipient_id=recipient_id,
            amount=amount,
            note=note,
            status=status,
            privacy=privacy,
            created_at=timestamp,
            payment_method_id=payment_method_id,
        )
        self.transactions[transaction_id] = transaction
        return transaction_id

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def get_balance(self) -> dict[str, Any]:
        """Get current Payment balance."""
        return {
            "balance": self.balance,
            "currency": "USD",
        }

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def get_feed(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get transaction feed showing recent public/friends transactions."""
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("Limit must be positive integer")

        visible_transactions = [
            t for t in self.transactions.values() if t.privacy in ["public", "friends"] and t.status == "completed"
        ]

        sorted_transactions = sorted(
            visible_transactions,
            key=lambda t: t.created_at.timestamp()
            if isinstance(t.created_at, datetime)
            else (t.created_at if isinstance(t.created_at, (int, float)) else 0),
            reverse=True,
        )[:limit]

        return [
            {
                "transaction_id": t.transaction_id,
                "sender": self.users[t.sender_id].display_name if t.sender_id in self.users else "Unknown",
                "recipient": self.users[t.recipient_id].display_name if t.recipient_id in self.users else "Unknown",
                "amount": t.amount,
                "note": t.note,
                "created_at": t.created_at,
            }
            for t in sorted_transactions
        ]

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def search_users(self, query: str) -> list[dict[str, Any]]:
        """Search for Payment users by username, name, or phone."""
        if not isinstance(query, str) or len(query.strip()) == 0:
            raise ValueError("Query must be non-empty string")

        query_lower = query.lower()
        return [
            {
                "user_id": u.user_id,
                "username": u.username,
                "display_name": u.display_name,
                "profile_picture": u.profile_picture,
                "is_friend": u.is_friend,
            }
            for u in self.users.values()
            if u.user_id != self.user_id
            and (query_lower in u.username.lower() or query_lower in u.display_name.lower() or query_lower in u.phone)
        ]

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def get_user(self, user_id: str) -> dict[str, Any]:
        """Get basic user profile information."""
        if not isinstance(user_id, str) or len(user_id) == 0:
            raise ValueError("User ID must be non-empty string")

        user = self._get_user_by_id(user_id)
        return {
            "user_id": user.user_id,
            "username": user.username,
            "display_name": user.display_name,
            "profile_picture": user.profile_picture,
            "is_friend": user.is_friend,
        }

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def get_user_profile(self, user_id: str) -> dict[str, Any]:
        """Get detailed Payment user profile with transaction history."""
        if not isinstance(user_id, str) or len(user_id) == 0:
            raise ValueError("User ID must be non-empty string")

        user = self._get_user_by_id(user_id)

        user_transactions = [
            t
            for t in self.transactions.values()
            if (t.sender_id == self.user_id and t.recipient_id == user_id)
            or (t.sender_id == user_id and t.recipient_id == self.user_id)
        ]

        sorted_transactions = sorted(
            user_transactions,
            key=lambda t: t.created_at.timestamp()
            if isinstance(t.created_at, datetime)
            else (t.created_at if isinstance(t.created_at, (int, float)) else 0),
            reverse=True,
        )[:10]

        return {
            "user_id": user.user_id,
            "username": user.username,
            "display_name": user.display_name,
            "profile_picture": user.profile_picture,
            "is_friend": user.is_friend,
            "recent_transactions": [
                {
                    "transaction_id": t.transaction_id,
                    "type": t.transaction_type,
                    "amount": t.amount,
                    "note": t.note,
                    "status": t.status,
                    "created_at": t.created_at,
                }
                for t in sorted_transactions
            ],
        }

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def send_payment(
        self,
        recipient_id: str,
        amount: float,
        note: str,
        privacy: str = "friends",
        payment_method_id: str | None = None,
    ) -> str:
        """Send money to another user."""
        if not isinstance(recipient_id, str) or len(recipient_id) == 0:
            raise ValueError("Recipient ID must be non-empty string")
        if not isinstance(amount, (int, float)) or amount <= 0:
            raise ValueError("Amount must be positive number")
        if not isinstance(note, str) or len(note.strip()) == 0:
            raise ValueError("Note must be non-empty string")
        if privacy not in ["public", "friends", "private"]:
            raise ValueError("Privacy must be 'public', 'friends', or 'private'")

        recipient = self._get_user_by_id(recipient_id)

        if payment_method_id and payment_method_id not in self.payment_methods:
            raise KeyError(f"Payment method {payment_method_id} not found")

        if self.balance < amount and not payment_method_id:
            raise ValueError("Insufficient balance")

        transaction_id = uuid_hex(self.rng)
        transaction = Transaction(
            transaction_id=transaction_id,
            transaction_type="payment",
            sender_id=self.user_id,
            recipient_id=recipient_id,
            amount=amount,
            note=note,
            status="completed",
            privacy=privacy,
            created_at=self.time_manager.time(),
            payment_method_id=payment_method_id,
        )

        self.transactions[transaction_id] = transaction

        if not payment_method_id:
            self.balance -= amount

        return transaction_id

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def request_payment(
        self,
        recipient_id: str,
        amount: float,
        note: str,
        privacy: str = "friends",
    ) -> str:
        """Request money from another user."""
        if not isinstance(recipient_id, str) or len(recipient_id) == 0:
            raise ValueError("Recipient ID must be non-empty string")
        if not isinstance(amount, (int, float)) or amount <= 0:
            raise ValueError("Amount must be positive number")
        if not isinstance(note, str) or len(note.strip()) == 0:
            raise ValueError("Note must be non-empty string")
        if privacy not in ["public", "friends", "private"]:
            raise ValueError("Privacy must be 'public', 'friends', or 'private'")

        recipient = self._get_user_by_id(recipient_id)

        transaction_id = uuid_hex(self.rng)
        transaction = Transaction(
            transaction_id=transaction_id,
            transaction_type="request",
            sender_id=self.user_id,
            recipient_id=recipient_id,
            amount=amount,
            note=note,
            status="pending",
            privacy=privacy,
            created_at=self.time_manager.time(),
        )

        self.transactions[transaction_id] = transaction
        return transaction_id

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def list_transactions(self, filter_type: str | None = None) -> list[dict[str, Any]]:
        """List user's transaction history with optional filtering."""
        if filter_type and filter_type not in ["sent", "received", "pending", "all"]:
            raise ValueError("Filter type must be 'sent', 'received', 'pending', or 'all'")

        user_transactions = []

        for t in self.transactions.values():
            is_sender = t.sender_id == self.user_id
            is_recipient = t.recipient_id == self.user_id

            if not (is_sender or is_recipient):
                continue

            if filter_type == "sent" and not is_sender:
                continue
            if filter_type == "received" and not is_recipient:
                continue
            if filter_type == "pending" and t.status != "pending":
                continue

            user_transactions.append(t)

        sorted_transactions = sorted(
            user_transactions,
            key=lambda t: t.created_at.timestamp()
            if isinstance(t.created_at, datetime)
            else (t.created_at if isinstance(t.created_at, (int, float)) else 0),
            reverse=True,
        )

        return [
            {
                "transaction_id": t.transaction_id,
                "type": t.transaction_type,
                "sender": self.users[t.sender_id].display_name if t.sender_id in self.users else "Unknown",
                "recipient": self.users[t.recipient_id].display_name if t.recipient_id in self.users else "Unknown",
                "amount": t.amount,
                "note": t.note,
                "status": t.status,
                "created_at": t.created_at,
            }
            for t in sorted_transactions
        ]

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def get_transaction(self, transaction_id: str) -> dict[str, Any]:
        """Get complete details of a specific transaction."""
        if not isinstance(transaction_id, str) or len(transaction_id) == 0:
            raise ValueError("Transaction ID must be non-empty string")

        transaction = self._get_transaction_by_id(transaction_id)

        return {
            "transaction_id": transaction.transaction_id,
            "type": transaction.transaction_type,
            "sender_id": transaction.sender_id,
            "sender_name": self.users[transaction.sender_id].display_name
            if transaction.sender_id in self.users
            else "Unknown",
            "recipient_id": transaction.recipient_id,
            "recipient_name": self.users[transaction.recipient_id].display_name
            if transaction.recipient_id in self.users
            else "Unknown",
            "amount": transaction.amount,
            "note": transaction.note,
            "status": transaction.status,
            "privacy": transaction.privacy,
            "created_at": transaction.created_at,
            "payment_method_id": transaction.payment_method_id,
        }

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def list_pending_requests(self) -> list[dict[str, Any]]:
        """List all pending payment requests (sent and received)."""
        pending = [
            t
            for t in self.transactions.values()
            if t.transaction_type == "request"
            and t.status == "pending"
            and (t.sender_id == self.user_id or t.recipient_id == self.user_id)
        ]

        sorted_pending = sorted(
            pending,
            key=lambda t: t.created_at.timestamp()
            if isinstance(t.created_at, datetime)
            else (t.created_at if isinstance(t.created_at, (int, float)) else 0),
            reverse=True,
        )

        return [
            {
                "transaction_id": t.transaction_id,
                "direction": "incoming" if t.recipient_id == self.user_id else "outgoing",
                "other_user": self.users[other_user_id].display_name
                if (other_user_id := (t.sender_id if t.recipient_id == self.user_id else t.recipient_id)) in self.users
                else "Unknown",
                "amount": t.amount,
                "note": t.note,
                "created_at": t.created_at,
            }
            for t in sorted_pending
        ]

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def pay_request(self, request_id: str, payment_method_id: str | None = None) -> str:
        """Pay a pending payment request."""
        if not isinstance(request_id, str) or len(request_id) == 0:
            raise ValueError("Request ID must be non-empty string")

        transaction = self._get_transaction_by_id(request_id)

        if transaction.transaction_type != "request":
            raise ValueError("Transaction is not a request")
        if transaction.status != "pending":
            raise ValueError(f"Request is not pending (status: {transaction.status})")
        if transaction.recipient_id != self.user_id:
            raise ValueError("Cannot pay request not directed to you")

        if payment_method_id and payment_method_id not in self.payment_methods:
            raise KeyError(f"Payment method {payment_method_id} not found")

        if self.balance < transaction.amount and not payment_method_id:
            raise ValueError("Insufficient balance")

        transaction.status = "completed"
        transaction.payment_method_id = payment_method_id

        if not payment_method_id:
            self.balance -= transaction.amount

        return transaction.transaction_id

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def decline_request(self, request_id: str) -> str:
        """Decline a pending payment request."""
        if not isinstance(request_id, str) or len(request_id) == 0:
            raise ValueError("Request ID must be non-empty string")

        transaction = self._get_transaction_by_id(request_id)

        if transaction.transaction_type != "request":
            raise ValueError("Transaction is not a request")
        if transaction.status != "pending":
            raise ValueError(f"Request is not pending (status: {transaction.status})")
        if transaction.recipient_id != self.user_id:
            raise ValueError("Cannot decline request not directed to you")

        transaction.status = "declined"
        return f"Request {request_id} declined"

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def cancel_request(self, request_id: str) -> str:
        """Cancel a pending outgoing payment request."""
        if not isinstance(request_id, str) or len(request_id) == 0:
            raise ValueError("Request ID must be non-empty string")

        transaction = self._get_transaction_by_id(request_id)

        if transaction.transaction_type != "request":
            raise ValueError("Transaction is not a request")
        if transaction.status != "pending":
            raise ValueError(f"Request is not pending (status: {transaction.status})")
        if transaction.sender_id != self.user_id:
            raise ValueError("Cannot cancel request you didn't send")

        transaction.status = "cancelled"
        return f"Request {request_id} cancelled"

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def list_contacts(self) -> list[dict[str, Any]]:
        """List all user's Payment contacts/friends."""
        friends = [u for u in self.users.values() if u.is_friend and u.user_id != self.user_id]

        return [
            {
                "user_id": u.user_id,
                "username": u.username,
                "display_name": u.display_name,
                "profile_picture": u.profile_picture,
            }
            for u in friends
        ]

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def get_transaction_history(self, user_id: str) -> list[dict[str, Any]]:
        """Get transaction history with a specific user."""
        if not isinstance(user_id, str) or len(user_id) == 0:
            raise ValueError("User ID must be non-empty string")

        user = self._get_user_by_id(user_id)

        user_transactions = [
            t
            for t in self.transactions.values()
            if (t.sender_id == self.user_id and t.recipient_id == user_id)
            or (t.sender_id == user_id and t.recipient_id == self.user_id)
        ]

        sorted_transactions = sorted(
            user_transactions,
            key=lambda t: t.created_at.timestamp()
            if isinstance(t.created_at, datetime)
            else (t.created_at if isinstance(t.created_at, (int, float)) else 0),
            reverse=True,
        )

        return [
            {
                "transaction_id": t.transaction_id,
                "type": t.transaction_type,
                "amount": t.amount,
                "note": t.note,
                "status": t.status,
                "created_at": t.created_at,
            }
            for t in sorted_transactions
        ]

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def add_friend(self, user_id: str) -> str:
        """Send friend request to a user."""
        if not isinstance(user_id, str) or len(user_id) == 0:
            raise ValueError("User ID must be non-empty string")

        user = self._get_user_by_id(user_id)

        if user.is_friend:
            raise ValueError(f"User {user.display_name} is already a friend")

        user.is_friend = True
        return f"Friend request sent to {user.display_name}"

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def remove_friend(self, user_id: str) -> str:
        """Remove a user from friends list."""
        if not isinstance(user_id, str) or len(user_id) == 0:
            raise ValueError("User ID must be non-empty string")

        user = self._get_user_by_id(user_id)

        if not user.is_friend:
            raise ValueError(f"User {user.display_name} is not a friend")

        user.is_friend = False
        return f"Removed {user.display_name} from friends"

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.READ, event_type=EventType.AGENT)
    def list_payment_methods(self) -> list[dict[str, Any]]:
        """List all linked payment methods."""
        return [
            {
                "payment_method_id": pm.payment_method_id,
                "type": pm.method_type,
                "name": pm.name,
                "last_four": pm.last_four,
                "is_default": pm.is_default,
                "verified": pm.verified,
            }
            for pm in self.payment_methods.values()
        ]

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def add_bank_account(self, account_number: str, routing_number: str, account_type: str) -> str:
        """Link a new bank account."""
        if not isinstance(account_number, str) or len(account_number) < 4:
            raise ValueError("Invalid account number")
        if not isinstance(routing_number, str) or len(routing_number) != 9:
            raise ValueError("Routing number must be 9 digits")
        if account_type not in ["checking", "savings"]:
            raise ValueError("Account type must be 'checking' or 'savings'")

        payment_method_id = uuid_hex(self.rng)
        payment_method = PaymentMethod(
            payment_method_id=payment_method_id,
            method_type="bank_account",
            last_four=account_number[-4:],
            name=f"{account_type.capitalize()} Account",
            is_default=len(self.payment_methods) == 0,
            verified=True,
        )

        self.payment_methods[payment_method_id] = payment_method
        return payment_method_id

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def add_card(self, card_number: str, expiry: str, cvv: str, billing_zip: str) -> str:
        """Link a new debit or credit card."""
        if not isinstance(card_number, str) or len(card_number) < 13:
            raise ValueError("Invalid card number")
        if not isinstance(expiry, str) or len(expiry) != 5:
            raise ValueError("Expiry must be in MM/YY format")
        if not isinstance(cvv, str) or len(cvv) not in [3, 4]:
            raise ValueError("Invalid CVV")
        if not isinstance(billing_zip, str) or len(billing_zip) < 5:
            raise ValueError("Invalid billing ZIP code")

        payment_method_id = uuid_hex(self.rng)
        payment_method = PaymentMethod(
            payment_method_id=payment_method_id,
            method_type="card",
            last_four=card_number[-4:],
            name=f"Card ending in {card_number[-4:]}",
            is_default=len(self.payment_methods) == 0,
            verified=True,
        )

        self.payment_methods[payment_method_id] = payment_method
        return payment_method_id

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def set_default_payment_method(self, payment_method_id: str) -> str:
        """Set a payment method as default."""
        if not isinstance(payment_method_id, str) or len(payment_method_id) == 0:
            raise ValueError("Payment method ID must be non-empty string")

        payment_method = self._get_payment_method_by_id(payment_method_id)

        for pm in self.payment_methods.values():
            pm.is_default = False

        payment_method.is_default = True
        return f"Set {payment_method.name} as default payment method"

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def remove_payment_method(self, payment_method_id: str) -> str:
        """Remove a linked payment method."""
        if not isinstance(payment_method_id, str) or len(payment_method_id) == 0:
            raise ValueError("Payment method ID must be non-empty string")

        payment_method = self._get_payment_method_by_id(payment_method_id)
        name = payment_method.name

        del self.payment_methods[payment_method_id]
        return f"Removed {name}"

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def transfer_to_bank(self, amount: float, bank_account_id: str, speed: str = "standard") -> str:
        """Transfer money from Payment to bank account."""
        if not isinstance(amount, (int, float)) or amount <= 0:
            raise ValueError("Amount must be positive number")
        if not isinstance(bank_account_id, str) or len(bank_account_id) == 0:
            raise ValueError("Bank account ID must be non-empty string")
        if speed not in ["standard", "instant"]:
            raise ValueError("Speed must be 'standard' or 'instant'")

        bank_account = self._get_payment_method_by_id(bank_account_id)

        if bank_account.method_type != "bank_account":
            raise ValueError("Payment method is not a bank account")

        if self.balance < amount:
            raise ValueError("Insufficient balance")

        self.balance -= amount

        eta = "1-3 business days" if speed == "standard" else "within 30 minutes"
        return f"Transfer of ${amount:.2f} to {bank_account.name} initiated. ETA: {eta}"

    @type_check
    @app_tool()
    @pas_event_registered(operation_type=OperationType.WRITE, event_type=EventType.AGENT)
    def add_money_from_bank(self, amount: float, bank_account_id: str) -> str:
        """Add money from bank account to Payment balance."""
        if not isinstance(amount, (int, float)) or amount <= 0:
            raise ValueError("Amount must be positive number")
        if not isinstance(bank_account_id, str) or len(bank_account_id) == 0:
            raise ValueError("Bank account ID must be non-empty string")

        bank_account = self._get_payment_method_by_id(bank_account_id)

        if bank_account.method_type != "bank_account":
            raise ValueError("Payment method is not a bank account")

        self.balance += amount
        return f"Added ${amount:.2f} from {bank_account.name}. ETA: 1-3 business days"

    def navigate_to_payment(self, user_id: str) -> None:
        """Navigate to payment view with pre-selected user."""
        self.set_current_state(PaymentView(recipient_id=user_id))

    def get_state(self) -> dict[str, Any]:
        """Serialize complete app state."""
        return {
            "user_id": self.user_id,
            "users": {k: v.get_state() for k, v in self.users.items()},
            "transactions": {k: v.get_state() for k, v in self.transactions.items()},
            "payment_methods": {k: v.get_state() for k, v in self.payment_methods.items()},
            "balance": self.balance,
        }

    def load_state(self, state_dict: dict[str, Any]) -> None:
        """Restore app state from serialized data."""
        self.users.clear()
        self.transactions.clear()
        self.payment_methods.clear()

        self.user_id = state_dict.get("user_id", "")
        self.balance = state_dict.get("balance", 0.0)

        for user_id, user_data in state_dict.get("users", {}).items():
            user = PaymentUser(
                user_id=user_data["user_id"],
                username=user_data["username"],
                display_name=user_data["display_name"],
            )
            user.load_state(user_data)
            self.users[user_id] = user

        for transaction_id, transaction_data in state_dict.get("transactions", {}).items():
            created_at = transaction_data["created_at"]
            if isinstance(created_at, str):
                with contextlib.suppress(ValueError):
                    created_at = datetime.fromisoformat(created_at)

            transaction = Transaction(
                transaction_id=transaction_data["transaction_id"],
                transaction_type=transaction_data["transaction_type"],
                sender_id=transaction_data["sender_id"],
                recipient_id=transaction_data["recipient_id"],
                amount=transaction_data["amount"],
                note=transaction_data["note"],
                status=transaction_data["status"],
                privacy=transaction_data["privacy"],
                created_at=created_at,
            )
            transaction.load_state(transaction_data)
            self.transactions[transaction_id] = transaction

        for pm_id, pm_data in state_dict.get("payment_methods", {}).items():
            payment_method = PaymentMethod(
                payment_method_id=pm_data["payment_method_id"],
                method_type=pm_data["method_type"],
                last_four=pm_data["last_four"],
            )
            payment_method.load_state(pm_data)
            self.payment_methods[pm_id] = payment_method

    def handle_state_transition(self, event: CompletedEvent) -> None:
        """Handle navigation state transitions based on user actions."""
        current_state = self.current_state
        fname = event.function_name()

        if current_state is None or fname is None:
            return

        action = event.action
        args = action.resolved_args or action.args
        metadata_value = event.metadata.return_value if event.metadata else None

        if isinstance(current_state, HomeView):
            self._handle_home_view_transition(fname, args, metadata_value)
        elif isinstance(current_state, PaymentView):
            self._handle_payment_view_transition(fname, args, metadata_value)
        elif isinstance(current_state, TransactionListView):
            self._handle_transaction_list_transition(fname, args, metadata_value)
        elif isinstance(current_state, TransactionDetail):
            self._handle_transaction_detail_transition(fname, args, metadata_value)
        elif isinstance(current_state, ContactListView):
            self._handle_contact_list_transition(fname, args, metadata_value)
        elif isinstance(current_state, UserProfile):
            self._handle_user_profile_transition(current_state, fname, args, metadata_value)
        elif isinstance(current_state, PaymentMethodsView):
            self._handle_payment_methods_transition(fname, args, metadata_value)
        elif isinstance(current_state, TransferView):
            self._handle_transfer_view_transition(fname, args, metadata_value)

    def _handle_home_view_transition(self, fname: str, args: dict[str, Any], metadata: object | None) -> None:
        """Handle transitions from home view state."""
        if fname == "view_transactions":
            self.set_current_state(TransactionListView())
        elif fname == "view_contacts":
            self.set_current_state(ContactListView())
        elif fname == "view_payment_methods":
            self.set_current_state(PaymentMethodsView())

    def _handle_payment_view_transition(self, fname: str, args: dict[str, Any], metadata: object | None) -> None:
        """Handle transitions from payment view state."""
        if fname in ["send_payment", "request_payment"]:
            transaction_id = metadata if isinstance(metadata, str) else None
            if transaction_id:
                self.set_current_state(TransactionDetail(transaction_id=transaction_id))

    def _handle_transaction_list_transition(self, fname: str, args: dict[str, Any], metadata: object | None) -> None:
        """Handle transitions from transaction list state."""
        if fname == "open_transaction":
            transaction_id = args.get("transaction_id")
            if transaction_id:
                self.set_current_state(TransactionDetail(transaction_id=str(transaction_id)))

    def _handle_transaction_detail_transition(self, fname: str, args: dict[str, Any], metadata: object | None) -> None:
        """Handle transitions from transaction detail state."""
        # After paying a request, stay in TransactionDetail to show updated status
        # After declining or cancelling a request, return to TransactionListView
        if fname in ["decline_request", "cancel_request"]:
            self.set_current_state(TransactionListView())
        # pay_request stays in TransactionDetail to show the completed payment

    def _handle_contact_list_transition(self, fname: str, args: dict[str, Any], metadata: object | None) -> None:
        """Handle transitions from contact list state."""
        if fname == "open_contact":
            user_id = args.get("user_id")
            if user_id:
                self.set_current_state(UserProfile(user_id=str(user_id)))

    def _handle_user_profile_transition(
        self, current_state: UserProfile, fname: str, args: dict[str, Any], metadata: object | None
    ) -> None:
        """Handle transitions from user profile state."""
        if fname == "pay_user":
            # Use user_id from current state since we're viewing this user's profile
            self.set_current_state(PaymentView(recipient_id=current_state.user_id))

    def _handle_payment_methods_transition(self, fname: str, args: dict[str, Any], metadata: object | None) -> None:
        """Handle transitions from payment methods view."""
        if fname == "view_transfer":
            self.set_current_state(TransferView())

    def _handle_transfer_view_transition(self, fname: str, args: dict[str, Any], metadata: object | None) -> None:
        """Handle transitions from transfer view state."""
        pass
