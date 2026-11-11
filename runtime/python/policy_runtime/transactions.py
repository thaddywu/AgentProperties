"""Local SQLite serialization, with explicit rollback certification."""

from contextlib import contextmanager

from .contracts import EffectNotAppliedError


def sqlite_transaction(connection):
    @contextmanager
    def transaction(_):
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException as error:
            connection.rollback()
            raise EffectNotAppliedError("All effects in this SQLite transaction were rolled back.") from error
        else:
            connection.commit()
    return transaction
