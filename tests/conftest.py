import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture(scope="function")
def test_db():
    """Create a test database session."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()


@pytest.fixture
def client(test_db):
    """Provide a FastAPI test client with test database."""
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_webhook_verify_whatsapp_invalid(client):
    """Test WhatsApp webhook verification with invalid token."""
    response = client.get(
        "/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=invalid&hub.challenge=test"
    )
    assert response.status_code == 403


def test_webhook_verify_whatsapp_valid(client):
    """Test WhatsApp webhook verification with valid token."""
    from app.core.config import get_settings

    settings = get_settings()
    response = client.get(
        f"/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token={settings.whatsapp_verify_token}&hub.challenge=test_challenge"
    )
    assert response.status_code == 200
    assert response.text == "test_challenge"
