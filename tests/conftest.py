import pytest

from helpers import make_site


@pytest.fixture
def site(tmp_path):
    return make_site(tmp_path / "site")
