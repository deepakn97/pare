"""Tests for the stateful payment app navigation flow."""

from __future__ import annotations

from typing import Any

import pytest
from are.simulation.types import (
    Action,
    CompletedEvent,
    EventMetadata,
    EventType,
)

from pas.apps.proactive_aui import PASAgentUserInterface
from pas.apps.payment.app import StatefulPaymentApp
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
from pas.apps.system import HomeScreenSystemApp
from pas.environment import StateAwareEnvironmentWrapper



def _home_state(app: StatefulPaymentApp) -> HomeView:
    """Assert and return app is in HomeView state."""
    state = app.current_state
    assert isinstance(state, HomeView)
    return state


def _payment_state(app: StatefulPaymentApp) -> PaymentView:
    """Assert and return app is in PaymentView state."""
    state = app.current_state
    assert isinstance(state, PaymentView)
    return state


def _transaction_list_state(app: StatefulPaymentApp) -> TransactionListView:
    """Assert and return app is in TransactionListView state."""
    state = app.current_state
    assert isinstance(state, TransactionListView)
    return state


def _transaction_detail_state(app: StatefulPaymentApp) -> TransactionDetail:
    """Assert and return app is in TransactionDetail state."""
    state = app.current_state
    assert isinstance(state, TransactionDetail)
    return state


def _contact_list_state(app: StatefulPaymentApp) -> ContactListView:
    """Assert and return app is in ContactListView state."""
    state = app.current_state
    assert isinstance(state, ContactListView)
    return state


def _payment_methods_state(app: StatefulPaymentApp) -> PaymentMethodsView:
    """Assert and return app is in PaymentMethodsView state."""
    state = app.current_state
    assert isinstance(state, PaymentMethodsView)
    return state


def _make_event(
    app: StatefulPaymentApp,
    func: callable,
    result: Any | None = None,
    **kwargs: Any,
) -> CompletedEvent:
    """Utility to build a minimal CompletedEvent for state transition tests.

    Args:
        app: The StatefulPaymentApp instance
        func: The function/method being called
        result: Optional return value for metadata
        **kwargs: Arguments to pass in the action
    """
    action = Action(function=func, args={"self": app, **kwargs}, app=app)

    metadata = EventMetadata()
    metadata.return_value = result

    return CompletedEvent(
        event_type=EventType.USER,
        action=action,
        metadata=metadata,
        event_time=0,
        event_id="payment-test-event",
    )


@pytest.fixture
def payment_app() -> StatefulPaymentApp:
    """Create a payment app with test data."""
    app = StatefulPaymentApp(name="payment")

    # Create test users
    user1_id = app.create_user(
        username="alice",
        display_name="Alice Smith",
        phone="555-0100",
        email="alice@example.com",
        is_friend=True,
    )
    user2_id = app.create_user(
        username="bob",
        display_name="Bob Jones",
        phone="555-0200",
        email="bob@example.com",
        is_friend=False,
    )
    user3_id = app.create_user(
        username="charlie",
        display_name="Charlie Brown",
        phone="555-0300",
        email="charlie@example.com",
        is_friend=True,
    )

    # Set current user
    app.set_current_user(user1_id)
    app.balance = 100.0

    # Add payment methods
    bank_id = app.add_bank_account(
        account_number="1234567890",
        routing_number="123456789",
        account_type="checking",
    )
    card_id = app.add_card(
        card_number="4111111111111111",
        expiry="12/25",
        cvv="123",
        billing_zip="12345",
    )

    # Create some transactions
    app.create_transaction_with_time(
        transaction_type="payment",
        sender_id=user1_id,
        recipient_id=user2_id,
        amount=25.0,
        note="Lunch",
        status="completed",
        created_at="2025-01-15 12:00:00",
        privacy="friends",
    )
    app.create_transaction_with_time(
        transaction_type="request",
        sender_id=user2_id,
        recipient_id=user1_id,
        amount=50.0,
        note="Dinner",
        status="pending",
        created_at="2025-01-16 18:00:00",
        privacy="friends",
    )

    return app


@pytest.fixture
def env_with_payment() -> StateAwareEnvironmentWrapper:
    """Create environment with payment app registered and opened."""
    env = StateAwareEnvironmentWrapper()
    system_app = HomeScreenSystemApp(name="HomeScreen")
    aui_app = PASAgentUserInterface()
    payment_app = StatefulPaymentApp(name="payment")

    # Create test user and set as current
    user_id = payment_app.create_user(
        username="testuser",
        display_name="Test User",
        phone="555-0000",
        email="test@example.com",
    )
    payment_app.set_current_user(user_id)
    payment_app.balance = 50.0

    env.register_apps([system_app, aui_app, payment_app])
    env._open_app("payment")
    return env




def test_starts_in_home(payment_app: StatefulPaymentApp) -> None:
    """App should start in HomeView with empty navigation stack."""
    assert isinstance(payment_app.current_state, HomeView)
    assert payment_app.navigation_stack == []




def test_view_transactions_transition(payment_app: StatefulPaymentApp) -> None:
    """Handler: view_transactions event transitions to TransactionListView."""
    event = _make_event(payment_app, payment_app.current_state.view_transactions)
    payment_app.handle_state_transition(event)

    assert isinstance(payment_app.current_state, TransactionListView)
    assert len(payment_app.navigation_stack) == 1


def test_view_contacts_transition(payment_app: StatefulPaymentApp) -> None:
    """Handler: view_contacts event transitions to ContactListView."""
    event = _make_event(payment_app, payment_app.current_state.view_contacts)
    payment_app.handle_state_transition(event)

    assert isinstance(payment_app.current_state, ContactListView)
    assert len(payment_app.navigation_stack) == 1


def test_view_payment_methods_transition(payment_app: StatefulPaymentApp) -> None:
    """Handler: view_payment_methods event transitions to PaymentMethodsView."""
    event = _make_event(payment_app, payment_app.current_state.view_payment_methods)
    payment_app.handle_state_transition(event)

    assert isinstance(payment_app.current_state, PaymentMethodsView)
    assert len(payment_app.navigation_stack) == 1


def test_send_payment_transition(payment_app: StatefulPaymentApp) -> None:
    """Handler: send_payment event transitions to TransactionDetail."""
    recipient_id = [uid for uid in payment_app.users.keys() if uid != payment_app.user_id][0]

    payment_state = PaymentView()
    payment_app.set_current_state(payment_state)

    transaction_id = "test_txn_123"
    event = _make_event(
        payment_app,
        payment_app.current_state.send_payment,
        result=transaction_id,
        recipient_id=recipient_id,
        amount=10.0,
        note="Test payment",
    )
    payment_app.handle_state_transition(event)

    assert isinstance(payment_app.current_state, TransactionDetail)
    assert payment_app.current_state.transaction_id == transaction_id


def test_request_payment_transition(payment_app: StatefulPaymentApp) -> None:
    """Handler: request_payment event transitions to TransactionDetail."""
    recipient_id = [uid for uid in payment_app.users.keys() if uid != payment_app.user_id][0]

    payment_state = PaymentView()
    payment_app.set_current_state(payment_state)

    transaction_id = "test_request_123"
    event = _make_event(
        payment_app,
        payment_app.current_state.request_payment,
        result=transaction_id,
        recipient_id=recipient_id,
        amount=20.0,
        note="Test request",
    )
    payment_app.handle_state_transition(event)

    assert isinstance(payment_app.current_state, TransactionDetail)
    assert payment_app.current_state.transaction_id == transaction_id


def test_open_transaction_transition(payment_app: StatefulPaymentApp) -> None:
    """Handler: open_transaction event transitions to TransactionDetail."""
    transaction_list_state = TransactionListView()
    payment_app.set_current_state(transaction_list_state)

    transaction_id = list(payment_app.transactions.keys())[0]
    event = _make_event(
        payment_app,
        payment_app.current_state.open_transaction,
        transaction_id=transaction_id,
    )
    payment_app.handle_state_transition(event)

    assert isinstance(payment_app.current_state, TransactionDetail)
    assert payment_app.current_state.transaction_id == transaction_id


def test_decline_request_transition(payment_app: StatefulPaymentApp) -> None:
    """Handler: decline_request event transitions to TransactionListView."""
    pending_requests = [
        t for t in payment_app.transactions.values()
        if t.transaction_type == "request" and t.status == "pending"
    ]
    if not pending_requests:
        pytest.skip("No pending requests in test data")

    request = pending_requests[0]
    detail_state = TransactionDetail(transaction_id=request.transaction_id)
    payment_app.set_current_state(detail_state)

    event = _make_event(
        payment_app,
        payment_app.current_state.decline_request,
        result=f"Request {request.transaction_id} declined",
        request_id=request.transaction_id,
    )
    payment_app.handle_state_transition(event)

    assert isinstance(payment_app.current_state, TransactionListView)


def test_open_contact_transition(payment_app: StatefulPaymentApp) -> None:
    """Handler: open_contact event transitions to UserProfile."""
    contact_list_state = ContactListView()
    payment_app.set_current_state(contact_list_state)

    friend_id = [
        uid for uid, user in payment_app.users.items()
        if user.is_friend and uid != payment_app.user_id
    ][0]

    event = _make_event(
        payment_app,
        payment_app.current_state.open_contact,
        user_id=friend_id,
    )
    payment_app.handle_state_transition(event)

    assert isinstance(payment_app.current_state, UserProfile)
    assert payment_app.current_state.user_id == friend_id


def test_pay_user_transition(payment_app: StatefulPaymentApp) -> None:
    """Handler: pay_user event transitions to PaymentView with recipient_id."""
    other_user_id = [uid for uid in payment_app.users.keys() if uid != payment_app.user_id][0]
    profile_state = UserProfile(user_id=other_user_id)
    payment_app.set_current_state(profile_state)

    event = _make_event(
        payment_app,
        payment_app.current_state.pay_user,
        user_id=other_user_id,
    )
    payment_app.handle_state_transition(event)

    assert isinstance(payment_app.current_state, PaymentView)
    assert payment_app.current_state.recipient_id == other_user_id


def test_view_transfer_transition(payment_app: StatefulPaymentApp) -> None:
    """Handler: view_transfer event transitions to TransferView."""
    payment_methods_state = PaymentMethodsView()
    payment_app.set_current_state(payment_methods_state)

    event = _make_event(
        payment_app,
        payment_app.current_state.view_transfer,
    )
    payment_app.handle_state_transition(event)

    assert isinstance(payment_app.current_state, TransferView)




def test_send_payment_flow(env_with_payment: StateAwareEnvironmentWrapper) -> None:
    """Integration: Home -> PaymentView -> send_payment -> TransactionDetail."""
    env = env_with_payment
    app = env.get_app_with_class(StatefulPaymentApp)

    recipient_id = app.create_user(
        username="recipient",
        display_name="Recipient User",
        phone="555-9999",
    )

    assert isinstance(app.current_state, HomeView)

    app.navigate_to_payment(recipient_id)
    assert isinstance(app.current_state, PaymentView)
    assert app.current_state.recipient_id == recipient_id
    assert len(app.navigation_stack) == 1

    initial_balance = app.balance
    _payment_state(app).send_payment(
        recipient_id=recipient_id,
        amount=10.0,
        note="Test payment",
    )

    assert isinstance(app.current_state, TransactionDetail)
    assert len(app.navigation_stack) == 2
    assert app.balance == initial_balance - 10.0


def test_go_back_navigation(env_with_payment: StateAwareEnvironmentWrapper) -> None:
    """Integration: Test go_back through multiple states."""
    env = env_with_payment
    app = env.get_app_with_class(StatefulPaymentApp)

    _home_state(app).view_transactions()
    assert isinstance(app.current_state, TransactionListView)
    assert len(app.navigation_stack) == 1

    app.go_back()
    assert isinstance(app.current_state, HomeView)
    assert len(app.navigation_stack) == 0

    _home_state(app).view_payment_methods()
    _payment_methods_state(app).view_transfer()
    assert isinstance(app.current_state, TransferView)
    assert len(app.navigation_stack) == 2

    app.go_back()
    assert isinstance(app.current_state, PaymentMethodsView)
    assert len(app.navigation_stack) == 1

    app.go_back()
    assert isinstance(app.current_state, HomeView)
    assert len(app.navigation_stack) == 0





def test_send_payment(payment_app: StatefulPaymentApp) -> None:
    """Test sending a payment."""
    recipient_id = [uid for uid in payment_app.users.keys() if uid != payment_app.user_id][0]
    initial_balance = payment_app.balance

    transaction_id = payment_app.send_payment(
        recipient_id=recipient_id,
        amount=15.0,
        note="Test payment",
    )

    assert transaction_id in payment_app.transactions
    assert payment_app.balance == initial_balance - 15.0
    assert payment_app.transactions[transaction_id].status == "completed"


def test_request_payment(payment_app: StatefulPaymentApp) -> None:
    """Test requesting a payment."""
    recipient_id = [uid for uid in payment_app.users.keys() if uid != payment_app.user_id][0]

    request_id = payment_app.request_payment(
        recipient_id=recipient_id,
        amount=30.0,
        note="Test request",
    )

    assert request_id in payment_app.transactions
    assert payment_app.transactions[request_id].transaction_type == "request"
    assert payment_app.transactions[request_id].status == "pending"


def test_pay_request(payment_app: StatefulPaymentApp) -> None:
    """Test paying a pending request."""
    pending_requests = [
        t for t in payment_app.transactions.values()
        if t.transaction_type == "request" and t.status == "pending"
        and t.recipient_id == payment_app.user_id
    ]
    if not pending_requests:
        sender_id = [uid for uid in payment_app.users.keys() if uid != payment_app.user_id][0]
        request_id = payment_app.create_transaction_with_time(
            transaction_type="request",
            sender_id=sender_id,
            recipient_id=payment_app.user_id,
            amount=20.0,
            note="Test request",
            status="pending",
            created_at="2025-01-17 10:00:00",
        )
        pending_requests = [payment_app.transactions[request_id]]

    request = pending_requests[0]
    initial_balance = payment_app.balance

    payment_app.pay_request(request.transaction_id)

    assert payment_app.transactions[request.transaction_id].status == "completed"
    assert payment_app.balance == initial_balance - request.amount




def test_send_payment_insufficient_balance(payment_app: StatefulPaymentApp) -> None:
    """Test sending payment with insufficient balance (should raise error)."""
    recipient_id = [uid for uid in payment_app.users.keys() if uid != payment_app.user_id][0]
    payment_app.balance = 5.0

    with pytest.raises(ValueError, match="Insufficient balance"):
        payment_app.send_payment(
            recipient_id=recipient_id,
            amount=100.0,
            note="Too much",
        )


def test_invalid_user_id_raises_error(payment_app: StatefulPaymentApp) -> None:
    """Test that operations with invalid user IDs raise errors."""
    with pytest.raises(KeyError):
        payment_app.set_current_user("nonexistent_user")

    with pytest.raises(KeyError):
        payment_app.send_payment(
            recipient_id="nonexistent_user",
            amount=10.0,
            note="Test",
        )


def test_pay_request_wrong_recipient(payment_app: StatefulPaymentApp) -> None:
    """Test that paying a request not directed to current user raises error."""
    recipient_id = [uid for uid in payment_app.users.keys() if uid != payment_app.user_id][0]
    request_id = payment_app.request_payment(
        recipient_id=recipient_id,
        amount=10.0,
        note="Test",
    )

    with pytest.raises(ValueError, match="Cannot pay request not directed to you"):
        payment_app.pay_request(request_id)
