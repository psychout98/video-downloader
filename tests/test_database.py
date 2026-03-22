"""
Unit tests for database.py

Tests core database operations: create_job, get_job, update_job, delete_job, etc.
"""
from __future__ import annotations

import pytest
from server.database import (
    JobStatus,
    create_job,
    get_job,
    update_job,
    delete_job,
    append_log,
    get_all_jobs,
    get_pending_jobs,
)


@pytest.mark.unit
class TestDatabaseOperations:
    """Database operation tests."""

    @pytest.mark.asyncio
    async def test_create_job_returns_dict_with_all_fields(self, mock_database):
        """Create a job and verify it has all expected fields."""
        job = await create_job("Test Movie")
        assert isinstance(job, dict)
        assert job["id"]
        assert job["query"] == "Test Movie"
        assert job["status"] == "pending"
        assert job["progress"] == 0.0
        assert job["downloaded_bytes"] == 0
        assert job["log"] == ""
        assert job["created_at"]
        assert job["updated_at"]

    @pytest.mark.asyncio
    async def test_get_job_returns_none_for_missing_id(self, mock_database):
        """Get a non-existent job should return None."""
        result = await get_job("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_job_returns_created_job(self, mock_database):
        """Create a job, retrieve it, and verify all fields."""
        created = await create_job("Test Query")
        job_id = created["id"]
        retrieved = await get_job(job_id)
        assert retrieved is not None
        assert retrieved["id"] == job_id
        assert retrieved["query"] == "Test Query"
        assert retrieved["status"] == "pending"

    @pytest.mark.asyncio
    async def test_update_job_changes_fields(self, mock_database):
        """Update a job and verify the changes."""
        job = await create_job("Test Job")
        job_id = job["id"]

        await update_job(
            job_id,
            status="downloading",
            progress=0.5,
            downloaded_bytes=2500000,
            title="Updated Title",
            year=2024,
        )

        updated = await get_job(job_id)
        assert updated["status"] == "downloading"
        assert updated["progress"] == 0.5
        assert updated["downloaded_bytes"] == 2500000
        assert updated["title"] == "Updated Title"
        assert updated["year"] == 2024

    @pytest.mark.asyncio
    async def test_append_log_adds_lines(self, mock_database):
        """Append log messages to a job."""
        job = await create_job("Test Job")
        job_id = job["id"]

        await append_log(job_id, "First message")
        await append_log(job_id, "Second message")

        updated = await get_job(job_id)
        assert "First message\n" in updated["log"]
        assert "Second message\n" in updated["log"]
        assert updated["log"].startswith("First message")

    @pytest.mark.asyncio
    async def test_delete_job_removes_row(self, mock_database):
        """Delete a job and verify it's gone."""
        job = await create_job("Test Job to Delete")
        job_id = job["id"]

        # Verify it exists
        assert await get_job(job_id) is not None

        # Delete it
        deleted = await delete_job(job_id)
        assert deleted is True

        # Verify it's gone
        assert await get_job(job_id) is None

    @pytest.mark.asyncio
    async def test_delete_job_returns_false_for_missing(self, mock_database):
        """Delete a non-existent job should return False."""
        result = await delete_job("nonexistent-id")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_all_jobs_returns_list_ordered_by_created_at(self, mock_database):
        """Get all jobs returns them ordered by created_at DESC."""
        # Create multiple jobs
        job1 = await create_job("First Job")
        job2 = await create_job("Second Job")
        job3 = await create_job("Third Job")

        all_jobs = await get_all_jobs(limit=100)
        assert len(all_jobs) >= 3

        # Most recent should be first
        assert all_jobs[0]["id"] == job3["id"]
        assert all_jobs[1]["id"] == job2["id"]
        assert all_jobs[2]["id"] == job1["id"]

    @pytest.mark.asyncio
    async def test_get_all_jobs_respects_limit(self, mock_database):
        """Get all jobs respects the limit parameter."""
        # Create 5 jobs
        for i in range(5):
            await create_job(f"Job {i}")

        # Get only 2
        jobs = await get_all_jobs(limit=2)
        assert len(jobs) == 2

    @pytest.mark.asyncio
    async def test_get_pending_jobs_only_returns_pending_status(self, mock_database):
        """Get pending jobs only returns jobs with pending status."""
        # Create jobs with different statuses
        pending1 = await create_job("Pending 1")
        pending2 = await create_job("Pending 2")
        completed = await create_job("Completed")

        # Update one to completed
        await update_job(completed["id"], status="complete")

        pending = await get_pending_jobs()

        # Should only have the 2 pending jobs
        pending_ids = [j["id"] for j in pending]
        assert pending1["id"] in pending_ids
        assert pending2["id"] in pending_ids
        assert completed["id"] not in pending_ids

    @pytest.mark.asyncio
    async def test_get_pending_jobs_ordered_by_created_at(self, mock_database):
        """Pending jobs are ordered by created_at ASC."""
        job1 = await create_job("First")
        job2 = await create_job("Second")
        job3 = await create_job("Third")

        pending = await get_pending_jobs()
        pending_ids = [j["id"] for j in pending if j["id"] in [job1["id"], job2["id"], job3["id"]]]

        # Oldest first
        assert pending_ids[0] == job1["id"]
        assert pending_ids[1] == job2["id"]
        assert pending_ids[2] == job3["id"]

    @pytest.mark.asyncio
    async def test_create_job_with_stream_data(self, mock_database):
        """Create a job with stream_data JSON."""
        stream_data = '{"media": {"title": "Test"}, "stream": {"name": "Test Stream"}}'
        job = await create_job("Test Query", stream_data=stream_data)
        assert job["stream_data"] == stream_data

    @pytest.mark.asyncio
    async def test_job_status_enum(self):
        """Verify JobStatus enum has expected values."""
        assert JobStatus.PENDING == "pending"
        assert JobStatus.SEARCHING == "searching"
        assert JobStatus.FOUND == "found"
        assert JobStatus.DOWNLOADING == "downloading"
        assert JobStatus.COMPLETE == "complete"
        assert JobStatus.FAILED == "failed"
        assert JobStatus.CANCELLED == "cancelled"
