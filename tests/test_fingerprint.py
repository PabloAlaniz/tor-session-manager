import random

import pytest

from tor_session_manager.fingerprint import (
    BROWSER_PROFILES,
    HeaderProfile,
    HeaderRotator,
)


def test_all_profiles_have_user_agent():
    assert BROWSER_PROFILES
    for profile in BROWSER_PROFILES:
        assert "User-Agent" in profile.headers
        assert profile.headers["User-Agent"]


def test_rotator_round_robins():
    profiles = [
        HeaderProfile("a", {"User-Agent": "A"}),
        HeaderProfile("b", {"User-Agent": "B"}),
    ]
    r = HeaderRotator(profiles=profiles)
    assert r.next()["User-Agent"] == "A"
    assert r.next()["User-Agent"] == "B"
    assert r.next()["User-Agent"] == "A"  # wraps around


def test_next_returns_copy():
    profiles = [HeaderProfile("a", {"User-Agent": "A"})]
    r = HeaderRotator(profiles=profiles)
    headers = r.next()
    headers["User-Agent"] = "MUTATED"
    # The underlying profile must be untouched.
    assert profiles[0].headers["User-Agent"] == "A"


def test_current_name_tracks_last():
    r = HeaderRotator(profiles=[HeaderProfile("only", {"User-Agent": "X"})])
    assert r.current_name is None
    r.next()
    assert r.current_name == "only"


def test_shuffle_is_deterministic_with_seeded_rng():
    profiles = [
        HeaderProfile("a", {"User-Agent": "A"}),
        HeaderProfile("b", {"User-Agent": "B"}),
        HeaderProfile("c", {"User-Agent": "C"}),
    ]
    order1 = [
        p.name
        for p in HeaderRotator(
            profiles=list(profiles), shuffle=True, rng=random.Random(42)
        ).profiles
    ]
    order2 = [
        p.name
        for p in HeaderRotator(
            profiles=list(profiles), shuffle=True, rng=random.Random(42)
        ).profiles
    ]
    assert order1 == order2


def test_empty_profiles_raises():
    with pytest.raises(ValueError):
        HeaderRotator(profiles=[])
