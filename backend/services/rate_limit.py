import time
import threading

RATE_LIMIT_PER_MINUTE = 30

rate_limit = {}
rate_limit_lock = threading.Lock()


def check_rate_limit(client_ip: str) -> bool:
    """Dakikada max RATE_LIMIT_PER_MINUTE istek."""
    with rate_limit_lock:
        now = time.time()

        # Eski kayıtları temizle
        for ip in list(rate_limit.keys()):
            rate_limit[ip] = [t for t in rate_limit[ip] if now - t < 60]
            if not rate_limit[ip]:
                del rate_limit[ip]

        if client_ip not in rate_limit:
            rate_limit[client_ip] = []

        if len(rate_limit[client_ip]) >= RATE_LIMIT_PER_MINUTE:
            return False

        rate_limit[client_ip].append(now)
        return True
