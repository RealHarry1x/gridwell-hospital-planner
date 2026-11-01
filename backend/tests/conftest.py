import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.assistant import AssistantService
from app.ai_config import AssistantConfig
from app import weather


@pytest.fixture(autouse=True)
def no_weather_network(monkeypatch):
    # Includes direct planner tests and startup seeding. Individual weather
    # tests replace this with an explicit mock response; no test uses internet.
    def offline(*args, **kwargs):
        raise RuntimeError('Weather HTTP must be mocked in tests.')
    monkeypatch.setattr(weather.httpx, 'get', offline)
    weather.clear_cache()
    yield
    weather.clear_cache()


@pytest.fixture
def client(tmp_path):
    # Tests never read a developer's real .env or make billable Gemini calls.
    service = AssistantService(config=AssistantConfig())
    with TestClient(create_app(tmp_path / "demo.sqlite3", assistant_service=service)) as test_client:
        yield test_client
