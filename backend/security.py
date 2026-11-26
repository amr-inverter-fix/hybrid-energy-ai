import hashlib, hmac, os, secrets, time, threading


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_key() -> str:
    return secrets.token_urlsafe(32)


def eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


class RateLimiter:
    """Token bucket per identity (api key hash or client ip). In-memory, single process."""
    def __init__(self, rate_per_s=5.0, burst=20, clock=time.monotonic):
        self.rate, self.burst, self.clock = rate_per_s, burst, clock
        self.b, self.lock = {}, threading.Lock()

    def allow(self, ident: str) -> bool:
        now = self.clock()
        with self.lock:
            tok, last = self.b.get(ident, (self.burst, now))
            tok = min(self.burst, tok + (now - last) * self.rate)
            ok = tok >= 1
            self.b[ident] = (tok - 1 if ok else tok, now)
            if len(self.b) > 10000:
                self.b.clear()
            return ok
