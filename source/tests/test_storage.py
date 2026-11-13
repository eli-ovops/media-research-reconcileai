from src.storage import JobStore


def test_job_store_persists_result(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    store.create("job-1", "invoice.pdf", "po.pdf")
    store.update("job-1", status="completed", result={
        "ok": True,
        "invoice": {"provider_metadata": {"estimated_cost_usd": 0.12}},
        "purchase_order": {"provider_metadata": {"estimated_cost_usd": 0.08}},
    })

    job = store.get("job-1")
    assert job["status"] == "completed"
    assert job["result"]["ok"] is True
    assert store.estimated_spend_usd() == 0.2
    assert store.list_recent()[0]["job_id"] == "job-1"


def test_incomplete_jobs_are_available_for_restart_recovery(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    store.create("queued", "invoice.pdf", "po.pdf")
    assert [job["job_id"] for job in store.incomplete_jobs()] == ["queued"]
