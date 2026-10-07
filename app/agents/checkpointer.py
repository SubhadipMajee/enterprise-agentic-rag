from langgraph.checkpoint.memory import MemorySaver

from app.config import settings

_checkpointer = None
_postgres_pool = None


def build_checkpointer():
    """
    Durable checkpointer for Cloud Run (multi-instance). MemorySaver is local-only.
    """
    global _checkpointer, _postgres_pool
    if _checkpointer is not None:
        return _checkpointer

    backend = settings.CHECKPOINT_BACKEND
    if backend == "redis":
        from langgraph.checkpoint.redis import RedisSaver

        saver = RedisSaver(redis_url=settings.REDIS_URL)
        saver.setup()
        _checkpointer = saver
        return _checkpointer

    if backend == "postgres":
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
        from langgraph.checkpoint.postgres import PostgresSaver

        _postgres_pool = ConnectionPool(
            conninfo=settings.DATABASE_URL,
            max_size=10,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
        )
        saver = PostgresSaver(_postgres_pool)
        saver.setup()
        _checkpointer = saver
        return _checkpointer

    if backend != "memory":
        raise RuntimeError(
            f"Unknown CHECKPOINT_BACKEND={backend!r}. Use memory, redis, or postgres."
        )

    _checkpointer = MemorySaver()
    return _checkpointer
