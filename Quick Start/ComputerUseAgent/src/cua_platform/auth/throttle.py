from collections import OrderedDict, deque
from datetime import datetime, timedelta
from math import ceil
from threading import Lock


class LoginThrottle:
    def __init__(
        self,
        *,
        max_attempts: int = 5,
        window: timedelta = timedelta(seconds=60),
        max_clients: int = 10_000,
    ) -> None:
        self.max_attempts = max_attempts
        self.window = window
        self.max_clients = max_clients
        self._attempts: OrderedDict[str, deque[datetime]] = OrderedDict()
        self._lock = Lock()

    def begin(self, client_key: str, now: datetime) -> int | None:
        with self._lock:
            attempts = self._attempts.get(client_key)
            if attempts is None:
                if len(self._attempts) >= self.max_clients:
                    self._attempts.popitem(last=False)
                attempts = deque()
                self._attempts[client_key] = attempts
            else:
                self._attempts.move_to_end(client_key)

            cutoff = now - self.window
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= self.max_attempts:
                return max(1, ceil((attempts[0] + self.window - now).total_seconds()))
            attempts.append(now)
            return None

    def clear(self, client_key: str) -> None:
        with self._lock:
            self._attempts.pop(client_key, None)
