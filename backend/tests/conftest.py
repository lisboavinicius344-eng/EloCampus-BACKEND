import pytest

from services import limite_tentativas


@pytest.fixture(autouse=True)
def zerar_limites_de_tentativas():
    """Cada teste começa sem tentativas contadas."""
    for limite in limite_tentativas.TODOS:
        limite.zerar_tudo()
    yield
