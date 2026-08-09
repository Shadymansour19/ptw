"""Client-side vocabulary for the /events SSE broadcast envelope.

Mirrors server/models/SSE.py so the client can interpret the `{object, object_id,
action, by}` payload pushed over the SSE stream without any per-event branching.
"""

import enum


class SSEObject(enum.StrEnum):
    """The kind of record an SSE broadcast is about: a PTW or an IC."""

    PTW = 'PTW'
    IC = 'IC'


class SSEAction(enum.StrEnum):
    """The human-readable action phrase carried in an SSE broadcast's `action` field.

    Each value is rendered as-is in the client's notification text
    (`f"{object} #{object_id} {action} by {by}"`), so members are the exact
    phrases shown to the user rather than internal codes.
    """

    CREATED = 'created'
    UPDATED = 'updated'
    DELETED = 'deleted'
    APPROVED = 'approved'
    RETURNED = 'returned'
    ARCHIVED = 'archived'
    RUN_REQUESTED = 'run requested'
    RUN_ACCEPTED = 'run accepted'
    RUN_REJECTED = 'run rejected'
    HOLD_REQUESTED = 'hold requested'
    HELD = 'held'
    HOLD_REJECTED = 'hold rejected'
    CLOSE_REQUESTED = 'close requested'
    CLOSED = 'closed'
    CLOSE_REJECTED = 'close rejected'
    ISOLATE_REQUESTED = 'isolate requested'
    ISOLATE_CONFIRMED = 'isolate confirmed'
    ISOLATE_REJECTED = 'isolate rejected'
    ISOLATED = 'isolated'
    DEISOLATE_REQUESTED = 'deisolate requested'
    DEISOLATE_CONFIRMED = 'deisolate confirmed'
    DEISOLATE_REJECTED = 'deisolate rejected'
    DEISOLATED = 'deisolated'
    LINKED = 'linked'
    UNLINKED = 'unlinked'
