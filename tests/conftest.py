import pytest

import custom_components  # noqa: F401  (must be imported before Home Assistant's loader runs)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
