from __future__ import annotations

import errno

# OS-level resource errors that are transient in parallel execution.
# Used by multi_scenario_runner (retry logic) and caching (cache write retry).
RETRYABLE_ERRNOS = {errno.EMFILE, errno.ENFILE, errno.ENOMEM}

APP_ALIAS = {
    "StatefulEmailApp": ["EmailClientV2", "Mail", "Emails"],
    "StatefulApartmentListingApp": ["RentAFlat"],
    "StatefulContactsApp": ["Contacts"],
    "StatefulMessagingApp": ["Messages", "Chats"],
    "StatefulCalendarApp": ["Calendar"],
    "StatefulShoppingApp": ["Shopping"],
    "StatefulCabApp": ["Cabs"],
    "SandboxLocalFileSystem": ["Files"],
}
