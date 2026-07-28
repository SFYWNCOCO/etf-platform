import pytest

def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as fast unit tests")

@pytest.fixture
def etf_code_chip():
    return "159995"

@pytest.fixture
def etf_code_broad():
    return "510300"

@pytest.fixture
def etf_sector_chip():
    return "半导体"

@pytest.fixture
def etf_code_qdii():
    return "159941"  # 纳指100ETF

@pytest.fixture
def etf_code_bond():
    return "511010"  # 国债ETF

@pytest.fixture
def etf_code_military():
    return "512660"  # 军工ETF

@pytest.fixture
def etf_code_new_energy():
    return "159566"  # 储能电池ETF

@pytest.fixture
def etf_code_consumer():
    return "159928"  # 消费ETF

@pytest.fixture
def etf_sector_qdii():
    return "跨境QDII"

@pytest.fixture
def etf_sector_bond():
    return "债券"

@pytest.fixture
def etf_sector_military():
    return "军工"
