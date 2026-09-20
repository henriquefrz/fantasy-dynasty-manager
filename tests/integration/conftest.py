"""
Shared fixtures for integration tests that hit real Sleeper/KTC/FantasyPros
APIs over the network. Excluded from the default `pytest -m "not integration"`
run; run explicitly with `pytest -m integration`.
"""
import pytest

from src.sleeper_api import get_nfl_state, get_user, get_user_leagues

SLEEPER_USER_HANDLE = "henriquefrz"


@pytest.fixture(scope="session")
def real_user():
    return get_user(SLEEPER_USER_HANDLE)


@pytest.fixture(scope="session")
def real_nfl_state():
    return get_nfl_state()


@pytest.fixture(scope="session")
def real_user_leagues(real_user, real_nfl_state):
    return get_user_leagues(real_user["user_id"], real_nfl_state["season"])
