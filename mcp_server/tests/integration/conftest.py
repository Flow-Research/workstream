from collections.abc import Iterator

import pytest
from integration.oauth_fixture import IdentityFixture


@pytest.fixture(scope="session")
def identity() -> Iterator[IdentityFixture]:
    provider = IdentityFixture()
    try:
        yield provider
    finally:
        provider.close()
