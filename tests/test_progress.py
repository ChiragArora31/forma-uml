import asyncio

from app.main import progress_events


async def test_heartbeats_do_not_cancel_pending_work():
    class Graph:
        async def astream(self, state, stream_mode):
            await asyncio.sleep(0.02)
            yield {"design": {"complete": True}}

    events = [e async for e in progress_events(Graph(), {}, heartbeat_seconds=0.003)]
    assert None in events
    assert events[-1] == {"design": {"complete": True}}


async def test_closing_progress_cancels_underlying_graph():
    closed = asyncio.Event()

    class Graph:
        async def astream(self, state, stream_mode):
            try:
                await asyncio.sleep(30)
                yield {}
            finally:
                closed.set()

    stream = progress_events(Graph(), {}, heartbeat_seconds=0.003)
    assert await anext(stream) is None
    await stream.aclose()
    assert closed.is_set()
