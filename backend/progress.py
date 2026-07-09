import asyncio


class ProgressBroadcaster:
    """Broadcast event progress per job_id ke semua client WebSocket yang subscribe.

    publish() sinkron dan thread-safe: pipeline yang berjalan di worker thread
    bisa memanggilnya langsung tanpa menyentuh event loop.
    """

    def __init__(self):
        self._subscribers: dict[str, list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}

    def subscribe(self, job_id: str) -> asyncio.Queue:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(job_id, []).append((loop, queue))
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(job_id, [])
        self._subscribers[job_id] = [(lp, q) for lp, q in subs if q is not queue]
        if not self._subscribers[job_id]:
            del self._subscribers[job_id]

    def publish(self, job_id: str, event: dict) -> None:
        for loop, queue in self._subscribers.get(job_id, []):
            loop.call_soon_threadsafe(queue.put_nowait, event)
