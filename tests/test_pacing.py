from tor_session_manager import pacing as pacing_mod
from tor_session_manager.pacing import RateLimiter


class _Clock:
    """Controllable monotonic clock + sleep recorder."""

    def __init__(self):
        self.now = 100.0
        self.slept = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds  # advance time as if we slept


def _patch_clock(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(pacing_mod.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(pacing_mod.time, "sleep", clock.sleep)
    return clock


def test_first_acquire_does_not_sleep(monkeypatch):
    clock = _patch_clock(monkeypatch)
    rl = RateLimiter(min_interval=2.0)
    rl.acquire("example.com")
    assert clock.slept == []


def test_second_acquire_waits_remaining(monkeypatch):
    clock = _patch_clock(monkeypatch)
    rl = RateLimiter(min_interval=2.0)
    rl.acquire("example.com")  # t=100, last=100
    clock.now = 100.5  # only 0.5s elapsed
    rl.acquire("example.com")
    assert clock.slept == [1.5]  # 2.0 - 0.5


def test_no_wait_when_interval_elapsed(monkeypatch):
    clock = _patch_clock(monkeypatch)
    rl = RateLimiter(min_interval=1.0)
    rl.acquire("example.com")
    clock.now = 105.0  # plenty elapsed
    rl.acquire("example.com")
    assert clock.slept == []


def test_record_backs_off_on_429(monkeypatch):
    _patch_clock(monkeypatch)
    rl = RateLimiter(min_interval=1.0, backoff_factor=2.0, max_interval=10.0)
    rl.record("h", 429)
    assert rl.interval_for("h") == 2.0
    rl.record("h", 429)
    assert rl.interval_for("h") == 4.0


def test_record_caps_at_max(monkeypatch):
    _patch_clock(monkeypatch)
    rl = RateLimiter(min_interval=1.0, backoff_factor=10.0, max_interval=5.0)
    rl.record("h", 503)
    assert rl.interval_for("h") == 5.0  # capped


def test_record_decays_on_ok(monkeypatch):
    _patch_clock(monkeypatch)
    rl = RateLimiter(min_interval=1.0, backoff_factor=2.0, decay=0.5)
    rl.record("h", 429)  # -> 2.0
    rl.record("h", 429)  # -> 4.0
    rl.record("h", 200)  # -> max(1.0, 4.0*0.5) = 2.0
    assert rl.interval_for("h") == 2.0
    rl.record("h", 200)  # -> max(1.0, 1.0) = 1.0
    assert rl.interval_for("h") == 1.0


def test_hosts_are_independent(monkeypatch):
    _patch_clock(monkeypatch)
    rl = RateLimiter(min_interval=1.0)
    rl.record("a", 429)
    assert rl.interval_for("a") == 2.0
    assert rl.interval_for("b") == 1.0
