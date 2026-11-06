"""Tests for AI Search History Database Storage and REST Endpoints.

Verifies:
- ACID persistence of AI search queries in SQLite database.
- Deduplication and timestamp updates.
- Chronological ordering (newest first).
- Single item deletion and full history clear.
- REST endpoints (/api/movies/storage/history).
- Automatic database recording when /api/movies/recommendations is called.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from app.api.server import create_app
from app.memory.database import DatabaseManager
from app.memory.movie_storage_repository import MovieStorageRepository
from app.api.movie_routes import get_recommendation_engine, get_movie_storage
from app.api.movie_models import RecommendationResponse, ParsedRecommendationIntent


@pytest.fixture
def temp_db_manager() -> DatabaseManager:
    """Provide an isolated, temporary SQLite database for testing."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "test_ai_history.db"
        manager = DatabaseManager(db_path=db_path)
        try:
            yield manager
        finally:
            manager.close()


@pytest.fixture
def movie_repo(temp_db_manager: DatabaseManager) -> MovieStorageRepository:
    """Provide a MovieStorageRepository backed by the temporary database."""
    return MovieStorageRepository(db_manager=temp_db_manager)


def test_ai_search_history_db_crud(movie_repo: MovieStorageRepository):
    """Test repository CRUD operations for AI search history."""
    # 1. Initial history is empty
    history = movie_repo.get_ai_search_history()
    assert len(history) == 0

    # 2. Add queries
    item1 = movie_repo.add_ai_search_history("Suggest South Indian Movies like Premalu")
    assert item1["id"] is not None
    assert item1["query"] == "Suggest South Indian Movies like Premalu"
    assert item1["timestamp"] > 0
    assert item1["created_at"] is not None

    item2 = movie_repo.add_ai_search_history("Underrated Malayalam thriller")
    item3 = movie_repo.add_ai_search_history("90s Hollywood action classic")

    history = movie_repo.get_ai_search_history()
    assert len(history) == 3
    # Newest query should be first
    assert history[0]["query"] == "90s Hollywood action classic"
    assert history[1]["query"] == "Underrated Malayalam thriller"
    assert history[2]["query"] == "Suggest South Indian Movies like Premalu"

    # 3. Deduplication: Re-adding an existing query updates timestamp and moves it to top
    item1_again = movie_repo.add_ai_search_history("suggest south indian movies like premalu")
    history_after_dedup = movie_repo.get_ai_search_history()
    assert len(history_after_dedup) == 3
    assert history_after_dedup[0]["query"] == "suggest south indian movies like premalu"

    # 4. Delete single query
    deleted = movie_repo.delete_ai_search_history_item(item2["id"])
    assert deleted is True
    history_after_del = movie_repo.get_ai_search_history()
    assert len(history_after_del) == 2
    queries = [h["query"] for h in history_after_del]
    assert "Underrated Malayalam thriller" not in queries

    # 5. Clear all history
    cleared = movie_repo.clear_ai_search_history()
    assert cleared is True
    assert len(movie_repo.get_ai_search_history()) == 0


def test_ai_search_history_fastapi_endpoints(temp_db_manager: DatabaseManager):
    """Test FastAPI REST endpoints for /api/movies/storage/history."""
    app = create_app()
    repo = MovieStorageRepository(db_manager=temp_db_manager)
    app.dependency_overrides[get_movie_storage] = lambda: repo

    client = TestClient(app)

    # 1. GET empty history
    res_get = client.get("/api/movies/storage/history")
    assert res_get.status_code == 200
    assert res_get.json() == []

    # 2. POST add query
    res_post1 = client.post("/api/movies/storage/history", json={"query": "Mind-bending sci-fi series"})
    assert res_post1.status_code == 200
    data1 = res_post1.json()
    assert data1["query"] == "Mind-bending sci-fi series"
    assert "id" in data1
    assert "timestamp" in data1

    res_post2 = client.post("/api/movies/storage/history", json={"query": "Feel-good Hindi comedy"})
    assert res_post2.status_code == 200

    # 3. GET populated history
    res_get2 = client.get("/api/movies/storage/history")
    assert res_get2.status_code == 200
    items = res_get2.json()
    assert len(items) == 2
    assert items[0]["query"] == "Feel-good Hindi comedy"
    assert items[1]["query"] == "Mind-bending sci-fi series"

    # 4. DELETE single item
    res_del_item = client.delete(f"/api/movies/storage/history/{data1['id']}")
    assert res_del_item.status_code == 200
    assert res_del_item.json()["deleted"] is True

    res_get3 = client.get("/api/movies/storage/history")
    assert len(res_get3.json()) == 1

    # 5. DELETE clear all
    res_clear = client.delete("/api/movies/storage/history")
    assert res_clear.status_code == 200
    assert res_clear.json()["cleared"] is True

    res_get4 = client.get("/api/movies/storage/history")
    assert res_get4.json() == []


def test_generate_recommendations_records_to_database(temp_db_manager: DatabaseManager):
    """Test that executing a recommendation automatically records the query in the SQLite database."""
    app = create_app()
    repo = MovieStorageRepository(db_manager=temp_db_manager)
    app.dependency_overrides[get_movie_storage] = lambda: repo

    # Mock engine to return dummy response
    mock_engine = MagicMock()
    mock_engine.recommend.return_value = RecommendationResponse(
        query="Movies like Interstellar",
        interpreted_intent=ParsedRecommendationIntent(),
        recommendations=[],
        total_candidates_analyzed=5,
    )
    app.dependency_overrides[get_recommendation_engine] = lambda: mock_engine

    client = TestClient(app)

    # Database initially has no search history
    assert len(repo.get_ai_search_history()) == 0

    # Call recommendations endpoint
    res = client.post("/api/movies/recommendations", json={"query": "Movies like Interstellar", "limit": 6})
    assert res.status_code == 200
    res_data = res.json()

    # Verify query was automatically stored in database and canonical history_id returned
    history = repo.get_ai_search_history()
    assert len(history) == 1
    assert history[0]["query"] == "Movies like Interstellar"
    assert res_data.get("history_id") == history[0]["id"]
    assert res_data["history_id"] is not None

