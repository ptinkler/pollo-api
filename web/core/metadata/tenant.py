"""Multi-tenant row scoping, enforced at the ORM layer.

Every tenant-owned row carries a user_id. A context variable holds the current
tenant; while it is set, ORM SELECTs are automatically filtered to that user
and new rows are stamped with it. Enforcing this in the ORM (not per query)
means no endpoint can forget to scope and leak another user's data. When the
tenant is unset (startup, migrations, system tasks) there is no filter — those
contexts are not user-facing.
"""

from collections.abc import Iterable, Sequence
from contextvars import ContextVar, Token
from typing import cast

from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria
from sqlalchemy.orm.unitofwork import UOWTransaction

from web.core.metadata.models import (
    Base,
    Character,
    ChatConversation,
    ChatImportSkip,
    ChatInstruction,
    ChatInstructionGroup,
    ChatLibraryItem,
    ChatMessage,
    ChatSettings,
    ChatSpace,
)

TENANT_MODELS = (
    ChatConversation,
    Character,
    ChatInstruction,
    ChatInstructionGroup,
    ChatSpace,
    ChatSettings,
    ChatMessage,
    ChatLibraryItem,
    ChatImportSkip,
)

_tenant: ContextVar[str | None] = ContextVar("tenant_user_id", default=None)


def set_tenant(user_id: str | None) -> Token[str | None]:
    """Bind the current tenant (user id); returns a token for reset_tenant."""
    return _tenant.set(user_id)


def reset_tenant(token: Token[str | None]) -> None:
    """Restore the tenant context using a token from ``set_tenant``."""
    _tenant.reset(token)


def current_tenant() -> str | None:
    """Return the tenant id bound to the current context, if any."""
    return _tenant.get()


@event.listens_for(Session, "do_orm_execute")
def _scope_selects_to_tenant(execute_state: ORMExecuteState) -> None:
    uid = _tenant.get()
    if uid is None or not execute_state.is_select:
        return
    for model in TENANT_MODELS:
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(model, model.user_id == uid, include_aliases=True)
        )


@event.listens_for(Session, "before_flush")
def _stamp_new_rows_with_tenant(
    session: Session, _flush_context: UOWTransaction, _instances: Sequence[Base] | None
) -> None:
    uid = _tenant.get()
    if uid is None:
        return
    for obj in cast("Iterable[Base]", session.new):
        if isinstance(obj, TENANT_MODELS) and getattr(obj, "user_id", None) is None:
            obj.user_id = uid
