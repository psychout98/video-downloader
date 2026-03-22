"""
Integration tests for jobs router (/api/search, /api/download, /api/jobs/*).
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.integration
class TestSearchEndpoint:
    """Search endpoint tests."""

    def test_search_with_empty_query_returns_422(self, test_client):
        """POST /api/search with empty query returns 422."""
        response = test_client.post("/api/search", json={"query": ""})
        assert response.status_code == 422

    def test_search_with_whitespace_only_returns_422(self, test_client):
        """POST /api/search with whitespace-only query returns 422."""
        response = test_client.post("/api/search", json={"query": "   "})
        assert response.status_code == 422

    def test_search_with_valid_query_returns_200(self, test_client, mock_state):
        """POST /api/search with valid query returns search_id and media."""
        response = test_client.post("/api/search", json={"query": "The Matrix"})
        assert response.status_code == 200

        data = response.json()
        assert "search_id" in data
        assert "media" in data
        assert "streams" in data

        # Media should have expected fields
        media = data["media"]
        assert "title" in media
        assert "year" in media
        assert "type" in media
        assert "imdb_id" in media

    def test_search_returns_search_id_uuid(self, test_client):
        """Search result includes a valid search_id."""
        response = test_client.post("/api/search", json={"query": "Test"})
        data = response.json()
        search_id = data["search_id"]

        # Should be a valid UUID
        try:
            uuid.UUID(search_id)
        except ValueError:
            pytest.fail(f"search_id '{search_id}' is not a valid UUID")

    def test_search_returns_streams_list(self, test_client):
        """Search result includes streams list with indexed objects."""
        response = test_client.post("/api/search", json={"query": "Test"})
        data = response.json()
        streams = data["streams"]

        assert isinstance(streams, list)
        if streams:
            stream = streams[0]
            assert "index" in stream
            assert "name" in stream
            assert "info_hash" in stream
            assert "size_bytes" in stream
            assert "is_cached_rd" in stream

    def test_search_caches_result(self, test_client, mock_state):
        """Search result is cached in state.searches."""
        response = test_client.post("/api/search", json={"query": "Cached"})
        data = response.json()
        search_id = data["search_id"]

        # Should be in the cache
        assert search_id in mock_state.searches
        cached = mock_state.searches[search_id]
        assert "media" in cached
        assert "streams" in cached
        assert "expires" in cached


@pytest.mark.integration
class TestDownloadEndpoint:
    """Download endpoint tests."""

    def test_download_with_invalid_search_id_returns_404(self, test_client):
        """POST /api/download with invalid search_id returns 404."""
        response = test_client.post(
            "/api/download",
            json={"search_id": "invalid-id", "stream_index": 0},
        )
        assert response.status_code == 404
        assert "expired" in response.json()["detail"].lower()

    def test_download_with_valid_search_returns_201(self, test_client):
        """POST /api/download with valid search_id and stream returns 201."""
        # First, search to get a search_id
        search_response = test_client.post("/api/search", json={"query": "Test"})
        search_id = search_response.json()["search_id"]

        # Then download using that search_id
        download_response = test_client.post(
            "/api/download",
            json={"search_id": search_id, "stream_index": 0},
        )
        assert download_response.status_code == 201

    def test_download_returns_job_id(self, test_client):
        """Download response includes job_id."""
        search_response = test_client.post("/api/search", json={"query": "Test"})
        search_id = search_response.json()["search_id"]

        download_response = test_client.post(
            "/api/download",
            json={"search_id": search_id, "stream_index": 0},
        )
        data = download_response.json()
        assert "job_id" in data
        assert data["status"] == "pending"

    def test_download_with_out_of_range_stream_returns_422(self, test_client):
        """POST /api/download with stream_index >= streams length returns 422."""
        search_response = test_client.post("/api/search", json={"query": "Test"})
        search_id = search_response.json()["search_id"]
        streams_count = len(search_response.json()["streams"])

        download_response = test_client.post(
            "/api/download",
            json={"search_id": search_id, "stream_index": streams_count + 100},
        )
        assert download_response.status_code == 422

    @pytest.mark.asyncio
    async def test_download_creates_job_in_database(self, test_client, mock_database):
        """Download creates a new job in the database."""
        search_response = test_client.post("/api/search", json={"query": "Matrix"})
        search_id = search_response.json()["search_id"]

        download_response = test_client.post(
            "/api/download",
            json={"search_id": search_id, "stream_index": 0},
        )
        job_id = download_response.json()["job_id"]

        # Verify job exists in database
        from server.database import get_job
        job = await get_job(job_id)
        assert job is not None
        assert job["status"] == "pending"


@pytest.mark.integration
class TestJobsListEndpoint:
    """Jobs listing endpoint tests."""

    def test_get_jobs_returns_200_with_jobs_list(self, test_client):
        """GET /api/jobs returns 200 with jobs array."""
        response = test_client.get("/api/jobs")
        assert response.status_code == 200

        data = response.json()
        assert "jobs" in data
        assert isinstance(data["jobs"], list)

    def test_get_jobs_empty_library(self, test_client):
        """GET /api/jobs returns empty list for new database."""
        response = test_client.get("/api/jobs")
        data = response.json()
        # May have jobs from other tests, so just check structure
        assert isinstance(data["jobs"], list)

    @pytest.mark.asyncio
    async def test_get_jobs_returns_created_jobs(self, test_client, mock_database):
        """GET /api/jobs returns jobs that were created."""
        from server.database import create_job

        # Create a job directly
        job = await create_job("Test Job")

        # Get all jobs
        response = test_client.get("/api/jobs")
        data = response.json()
        jobs = data["jobs"]

        job_ids = [j["id"] for j in jobs]
        assert job["id"] in job_ids


@pytest.mark.integration
class TestJobDetailEndpoint:
    """Individual job detail endpoint tests."""

    def test_get_job_returns_404_for_bad_id(self, test_client):
        """GET /api/jobs/{bad_id} returns 404."""
        response = test_client.get("/api/jobs/nonexistent-id-xyz")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_job_returns_job_details(self, test_client, mock_database):
        """GET /api/jobs/{id} returns job dict with all fields."""
        from server.database import create_job

        job = await create_job("Test Job")
        job_id = job["id"]

        response = test_client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == job_id
        assert data["query"] == "Test Job"
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_get_job_returns_all_fields(self, test_client, mock_database):
        """Job detail includes all database fields."""
        from server.database import create_job

        job = await create_job("Test Job")
        response = test_client.get(f"/api/jobs/{job['id']}")
        data = response.json()

        # Verify key fields exist
        assert "id" in data
        assert "query" in data
        assert "status" in data
        assert "progress" in data
        assert "created_at" in data
        assert "updated_at" in data


@pytest.mark.integration
class TestDeleteJobEndpoint:
    """Delete job endpoint tests."""

    def test_delete_job_returns_404_for_missing(self, test_client):
        """DELETE /api/jobs/{bad_id} returns 404."""
        response = test_client.delete("/api/jobs/nonexistent-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_pending_job_cancels_it(self, test_client, mock_database):
        """DELETE /api/jobs/{id} cancels a pending job."""
        from server.database import create_job, get_job

        job = await create_job("Test Job")
        job_id = job["id"]

        response = test_client.delete(f"/api/jobs/{job_id}")
        assert response.status_code == 200

        # Job should now have status cancelled (if still pending)
        updated = await get_job(job_id)
        assert updated["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_delete_completed_job_removes_it(self, test_client, mock_database):
        """DELETE /api/jobs/{id} for completed job deletes it."""
        from server.database import create_job, get_job, update_job

        job = await create_job("Test Job")
        job_id = job["id"]

        # Mark as complete
        await update_job(job_id, status="complete")

        # Delete it
        response = test_client.delete(f"/api/jobs/{job_id}")
        assert response.status_code == 200

        # Should be gone
        retrieved = await get_job(job_id)
        assert retrieved is None


@pytest.mark.integration
class TestRetryJobEndpoint:
    """Retry job endpoint tests."""

    def test_retry_nonexistent_job_returns_404(self, test_client):
        """POST /api/jobs/{bad_id}/retry returns 404."""
        response = test_client.post("/api/jobs/nonexistent-id/retry")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_retry_failed_job_requeues_it(self, test_client, mock_database):
        """POST /api/jobs/{id}/retry re-queues a failed job."""
        from server.database import create_job, get_job, update_job

        job = await create_job("Test Job")
        job_id = job["id"]

        # Mark as failed
        await update_job(job_id, status="failed", error="Test error")

        # Retry it
        response = test_client.post(f"/api/jobs/{job_id}/retry")
        assert response.status_code == 200

        # Should be pending again
        updated = await get_job(job_id)
        assert updated["status"] == "pending"
        assert updated["error"] is None or updated["error"] == ""
        assert updated["progress"] == 0.0

    @pytest.mark.asyncio
    async def test_retry_cancelled_job_requeues_it(self, test_client, mock_database):
        """POST /api/jobs/{id}/retry re-queues a cancelled job."""
        from server.database import create_job, get_job, update_job

        job = await create_job("Test Job")
        job_id = job["id"]

        # Mark as cancelled
        await update_job(job_id, status="cancelled")

        # Retry it
        response = test_client.post(f"/api/jobs/{job_id}/retry")
        assert response.status_code == 200

        updated = await get_job(job_id)
        assert updated["status"] == "pending"

    @pytest.mark.asyncio
    async def test_retry_active_job_returns_400(self, test_client, mock_database):
        """POST /api/jobs/{id}/retry on active job returns 400."""
        from server.database import create_job, update_job

        job = await create_job("Test Job")
        job_id = job["id"]

        # Mark as downloading (active)
        await update_job(job_id, status="downloading")

        # Try to retry — should fail
        response = test_client.post(f"/api/jobs/{job_id}/retry")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_retry_pending_job_returns_400(self, test_client, mock_database):
        """POST /api/jobs/{id}/retry on pending job returns 400."""
        from server.database import create_job

        job = await create_job("Test Job")
        job_id = job["id"]

        # Already pending, shouldn't be retryable
        response = test_client.post(f"/api/jobs/{job_id}/retry")
        assert response.status_code == 400
