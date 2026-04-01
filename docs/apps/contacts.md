# Stateful Contacts App

`pare.apps.contacts.app.StatefulContactsApp` extends the Meta-ARE `ContactsApp` with PARE navigation. It launches in `ContactsList` and moves between list, detail, and edit flows based on the backend tool that just completed.

## Navigation States

### ContactsList

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `list_contacts(offset: int = 0)` | `ContactsApp.get_contacts(offset=offset)` | Meta-ARE pagination dict containing contacts and cursors | Remains in `ContactsList` |
| `search_contacts(query: str)` | `ContactsApp.search_contacts(query=query)` | `list[Contact]` filtered server-side | Remains in `ContactsList` |
| `open_contact(contact_id: str)` | Queues intent, then `ContactsApp.get_contact(contact_id=contact_id)` | `Contact` for the requested id | After the event completes, transitions to `ContactDetail(contact_id)` |
| `view_current_user()` | `ContactsApp.get_current_user_details()` | Persona `Contact` record for the signed-in user | No navigation change |
| `create_contact(**fields)` | `ContactsApp.add_new_contact(**fields)` with all provided kwargs | Newly created contact id string | Remains in `ContactsList` until caller opens the contact |

### ContactDetail

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `view_contact()` | `ContactsApp.get_contact(contact_id=current)` | Latest `Contact` snapshot | Remains in `ContactDetail` |
| `start_edit_contact()` | Queues edit intent, then `ContactsApp.get_contact(contact_id=current)` | `Contact` data used to seed edit form | Completed event pushes `ContactEdit(contact_id)` |
| `delete_contact()` | `ContactsApp.delete_contact(contact_id=current)` | Backend confirmation string | Pops back to the previous state (typically `ContactsList`) |

### ContactEdit

| Tool | Backend call(s) | Returns | Navigation effect |
| --- | --- | --- | --- |
| `view_contact()` | `ContactsApp.get_contact(contact_id=current)` | Current `Contact` contents | Remains in `ContactEdit` |
| `update_contact(updates: dict[str, object])` | `ContactsApp.edit_contact(contact_id=current, updates=updates)` | `None` on success (Meta-ARE convention) | Successful update returns to the detail state for the same contact |

## Navigation Helpers
- `go_back()` appears automatically when navigation history exists and pops to the prior screen, returning messages such as `Navigated back to the state ContactsList`.
- Internal helper `queue_contact_transition(intent, contact_id)` coordinates delayed transitions after backend calls finish.
