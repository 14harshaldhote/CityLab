import pytest

from citylab.core.world import World


@pytest.fixture(scope="session")
def small_world_template():
    """Built once; tests that advance time make their own copy via ``fresh_world``."""
    return {"seed": 4, "population": 400}


@pytest.fixture
def fresh_world(small_world_template):
    return World(**small_world_template)
