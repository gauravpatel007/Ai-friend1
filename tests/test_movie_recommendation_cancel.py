"""Unit tests for AI movie recommendations cancellation."""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.api.server import create_app
from app.ai.movie_recommendation_engine import MovieRecommendationEngine
from app.api.movie_models import ParsedRecommendationIntent, RecommendationResponse


def test_engine_cancel_flag():
    engine = MovieRecommendationEngine(
        tmdb_client=MagicMock(),
        storage_repo=MagicMock(),
        ollama_client=MagicMock(),
    )
    assert engine._is_cancelled is False

    engine.cancel()
    assert engine._is_cancelled is True

    # Simulate cancellation during generation
    def trigger_cancel(*args, **kwargs):
        engine.cancel()
        return MagicMock()

    engine.parse_intent_deterministic = MagicMock(side_effect=trigger_cancel)
    with pytest.raises(RuntimeError, match="cancelled"):
        engine.recommend("test movie")


def test_fastapi_recommendations_cancel_endpoint():
    app = create_app()
    mock_engine = MagicMock(spec=MovieRecommendationEngine)
    app.state.movie_rec_engine = mock_engine

    client = TestClient(app)
    res = client.post("/api/movies/recommendations/cancel")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "cancelled": True}
    mock_engine.cancel.assert_called_once()
