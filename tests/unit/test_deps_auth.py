"""require_api_key extracted to backend.api.deps — reusable + unit-testable."""
import pytest
from fastapi import HTTPException

from backend.api.deps import require_api_key


def test_dev_mode_no_key_allows(monkeypatch):
    monkeypatch.delenv("PLAYAIDES_API_KEY", raising=False)
    assert require_api_key(authorization=None) is None  # dev convenience: no gate


def test_missing_bearer_rejected(monkeypatch):
    monkeypatch.setenv("PLAYAIDES_API_KEY", "k")
    with pytest.raises(HTTPException) as e:
        require_api_key(authorization=None)
    assert e.value.status_code == 401


def test_wrong_token_rejected(monkeypatch):
    monkeypatch.setenv("PLAYAIDES_API_KEY", "k")
    with pytest.raises(HTTPException) as e:
        require_api_key(authorization="Bearer nope")
    assert e.value.status_code == 401
    assert e.value.detail == "invalid bearer token"


def test_correct_token_passes(monkeypatch):
    monkeypatch.setenv("PLAYAIDES_API_KEY", "k")
    assert require_api_key(authorization="Bearer k") is None
