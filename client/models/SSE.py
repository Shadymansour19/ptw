import enum


class SSEObject(enum.StrEnum):
    PTW = 'PTW'
    IC = 'IC'


class SSEAction(enum.StrEnum):
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
