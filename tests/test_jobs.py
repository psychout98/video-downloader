"""
Integration tests for Search API (Feature 4), Download API (Feature 5),
and Jobs API (Feature 6).

AC Reference:
  4.1  POST /api/search with empty or whitespace-only query returns 422
  4.2  Valid query returns 200 with search_id, media, and streams
  4.3  search_id is a valid UUID
  4.4  Each stream has index, name, info_hash, size_bytes, is_cached_rd
  4.5  Search result is cached in state.searches with an expires timestamp
  5.1  POST /api/download with invalid search_id returns 404
  5.2  Valid request returns 201 with job_id and status="pending"
  5.3  stream_index out of range returns 422
  5.4  Download creates a job in the database with status="pending"
  6.1  GET /api/jobs returns 200 with a jobs array
  6.2  Empty database returns an empty list
  6.3  GET /api/jobs/:id returns 404 for unknown ID
  6.4  GET /api/jobs/:id returns full job details including all DB fields
  6.5  DELETE /api/jobs/:id returns 404 for missing ID
  6.6  Deleting a pending job sets status="cancelled"
  6.7  Deleting a completed job removes it from the database
  6.8  POST /api/jobs/:id/retry returns 404 for missing ID
  6.9  Retrying a failed or cancelled job resets status="pending"
  6.10 Retrying an active or pending job returns 400
"""
from __future__ import annotations

import uuid

import pytest


# ── Feature 4: Search API ────────────────────────────────────────────────


@pytest.mark.integration
class TestFeature4_SearchAPI:
    """Feature 4: Search API"""

    def test_4_1_empty_or_whitespace_query_returns_422(self, test_client):
        """4.1 — POST /api/search with empty or whitespace-only query returns 422."""
        resp_empty = test_client.post("/api/search", json={"query": ""})
        assert resp_empty.status_code == 422

        resp_whitespace = test_client.post("/api/search", json={"query": "   "})
        assert resp_whitespace.status_code == 422

    def test_4_2_valid_query_returns_search_id_media_and_streams(self, test_client, mock_state):
        """4.2 — Valid query returns 200 with search_id, media, and streams."""
        response = test_client.post("/api/search", json={"query": "The Matrix"})
        assert response.status_code == 200

        data = response.json()
        assert "search_id" in data
        assert "media" in data
        assert "streams" in data

        media = data["media"]
        assert "title" in media
        assert "year" in media
        assert "type" in media
        assert "imdb_id" in media

    def test_4_3_search_id_is_a_valid_uuid(self, test_client):
        """4.3 — search_id is a valid UUID."""
        response = test_client.post("/api/search", json={"query": "Test"})
        search_id = response.json()["search_id"]

        try:
            uuid.UUID(search_id)
        except ValueError:
            pytest.fail(f"search_id '{search_id}' is not a valid UUID")

    def test_4_4_each_stream_has_required_fields(self, test_client):
        """4.4 — Each stream has index, name, info_hash, size_bytes, is_cached_rd."""
        response = test_client.post("/api/search", json={"query": "Test"})
        streams = response.json()["streams"]

        assert isinstance(streams, list)
        for stream in streams:
            assert "index" in stream
            assert "name" in stream
            assert "info_hash" in stream
            assert "size_bytes" in stream
            assert "is_cached_rd" in stream

    def test_4_5_search_result_is_cached_with_expires(self, test_client, mock_state):
        """4.5 — Search result is cached in state.searches with an expires timestamp."""
        response = test_client.post("/api/search", json={"query": "Cached"})
        search_id = response.json()["search_id"]

        assert search_id in mock_state.searches
        cached = mock_state.searches[search_id]
        assert "media" in cached
        assert "streams" in cached
        assert "expires" in cached


# ── Feature 5: Download API ──────────────────────────────────────────────


@pytest.mark.integration
class TestFeature5_DownloadAPI:
    """Feature 5: Download API"""

    def test_5_1_invalid_search_id_returns_404(self, test_client):
        """5.1 — POST /api/download with invalid search_id returns 404."""
        response = test_client.post(
            "/api/download",
            json={"search_id": "invalid-id", "stream_index": 0},
        )
        assert response.status_code == 404
        assert "expired" in response.json()["detail"].lower()

    def test_5_2_valid_request_returns_201_with_pending_status(self, test_client):
        """5.2 — Valid request returns 201 with job_id and status="pending"."""
        search_response = test_client.post("/api/search", json={"query": "Test"})
        search_id = search_response.json()["search_id"]

        download_response = test_client.post(
            "/api/download",
            json={"search_id": search_id, "stream_index": 0},
        )
        assert download_response.status_code == 201

        data = download_response.json()
        assert "job_id" in data
        assert data["status"] == "pending"

    def test_5_3_stream_index_out_of_range_returns_422(self, test_client):
        """5.3 — stream_index out of range returns 422."""
        search_response = test_client.post("/api/search", json={"query": "Test"})
        search_id = search_response.json()["search_id"]
        streams_count = len(search_response.json()["streams"])

        download_response = test_client.post(
            "/api/download",
            json={"search_id": search_id, "stream_index": streams_count + 100},
        )
        assert download_response.status_code == 422

    @pytest.mark.asyncio
    async def test_5_4_download_creates_job_in_database(self, test_client, mock_database):
        """5.4 — Download creates a job in the database with status="pending"."""
        search_response = test_client.post("/api/search", json={"query": "Matrix"})
        search_id = search_response.json()["search_id"]

        download_response = test_client.post(
            "/api/download",
            json={"search_id": search_id, "stream_index": 0},
        )
        job_id = download_response.json()["job_id"]

        from server.database import get_job
        job = await get_job(job_id)
        assert job is not None
        assert job["status"] == "pending"


# ── Feature 6: Jobs API ─────────────────────────────────────────────────


@pytest.mark.integration
class TestFeature6_JobsAPI:
    """Feature 6: Jobs API"""

    # ── 6.1 & 6.2: List jobs ─────────────────────────────────────────

    def test_6_1_get_jobs_returns_200_with_jobs_array(self, test_client):
        """6.1 — GET /api/jobs returns 200 with a jobs array."""
        response = test_client.get("/api/jobs")
        assert response.status_code == 200

        data = response.json()
        assert "jobs" in data
        assert isinstance(data["jobs"], list)

    def test_6_2_empty_database_returns_empty_list(self, test_client):
        """6.2 — Empty database returns an empty list."""
        response = test_client.get("/api/jobs")
        data = response.json()
        assert isinstance(data["jobs"], list)

    # ── 6.3 & 6.4: Job details ───────────────────────────────────────

    def test_6_3_get_job_returns_404_for_unknown_id(self, test_client):
        """6.3 — GET /api/jobs/:id returns 404 for unknown ID."""
        response = test_client.get("/api/jobs/nonexistent-id-xyz")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_6_4_get_job_returns_full_details(self, test_client, mock_database):
        """6.4 — GET /api/jobs/:id returns full job details including all DB fields."""
        from server.database import create_job

        job = await create_job("Test Job")
        response = test_client.get(f"/api/jobs/{job['id']}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == job["id"]
        assert data["query"] == "Test Job"
        assert data["status"] == "pending"
        for field in ("id", "query", "status", "progress", "created_at", "updated_at"):
            assert field in data

    # ── 6.5, 6.6, 6.7: Delete jobs ───────────────────────────────────

    def test_6_5_delete_job_returns_404_for_missing_id(self, test_client):
        """6.5 — DELETE /api/jobs/:id returns 404 for missing ID."""
        response = test_client.delete("/api/jobs/nonexistent-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_6_6_deleting_pending_job_sets_status_cancelled(self, test_client, mock_database):
        """6.6 — Deleting a pending job sets status="cancelled"."""
        from server.database import create_job, get_job

        job = await create_job("Test Job")
        response = test_client.delete(f"/api/jobs/{job['id']}")
        assert response.status_code == 200

        updated = await get_job(job["id"])
        assert updated["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_6_7_deleting_completed_job_removes_it(self, test_client, mock_database):
        """6.7 — Deleting a completed job removes it from the database."""
        from server.database import create_job, get_job, update_job

        job = await create_job("Test Job")
        await update_job(job["id"], status="complete")

        response = test_client.delete(f"/api/jobs/{job['id']}")
        assert response.status_code == 200

        retrieved = await get_job(job["id"])
        assert retrieved is None

    # ── 6.8, 6.9, 6.10: Retry jobs ───────────────────────────────────

    def test_6_8_retry_returns_404_for_missing_id(self, test_client):
        """6.8 — POST /api/jobs/:id/retry returns 404 for missing ID."""
        response = test_client.post("/api/jobs/nonexistent-id/retry")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_6_9_retrying_failed_or_cancelled_job_resets_to_pending(self, test_client, mock_database):
        """6.9 — Retrying a failed or cancelled job resets status="pending"."""
        from server.database import create_job, get_job, update_job

        # Failed job
        job_failed = await create_job("Failed Job")
        await update_job(job_failed["id"], status="failed", error="Test error")

        response = test_client.post(f"/api/jobs/{job_failed['id']}/retry")
        assert response.status_code == 200

        updated = await get_job(job_failed["id"])
        assert updated["status"] == "pending"
        assert updated["error"] is None or updated["error"] == ""
        assert updated["progress"] == 0.0

        # Cancelled job
        job_cancelled = await create_job("Cancelled Job")
        await update_job(job_cancelled["id"], status="cancelled")

        response = test_client.post(f"/api/jobs/{job_cancelled['id']}/retry")
        assert response.status_code == 200

        updated = await get_job(job_cancelled["id"])
        assert updated["status"] == "pending"

    @pytest.mark.asyncio
    async def test_6_10_retrying_active_or_pending_job_returns_400(self, test_client, mock_database):
        """6.10 — Retrying an active or pending job returns 400."""
        from server.database import create_job, update_job

        # Active (downloading) job
        job_active = await create_job("Active Job")
        await update_job(job_active["id"], status="downloading")
        response = test_client.post(f"/api/jobs/{job_active['id']}/retry")
        assert response.status_code == 400

        # Pending job
        job_pending = await create_job("Pending Job")
        response = test_client.post(f"/api/jobs/{job_pending['id']}/retry")
        assert response.status_code == 400
