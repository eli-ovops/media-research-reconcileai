"""Deploy an explicit file allowlist. Never copy .env, credentials, uploads or provider code."""

import argparse
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(name: str) -> None:
    from dotenv import load_dotenv
    from huggingface_hub import HfApi

    load_dotenv(ROOT / ".env")
    if not os.getenv("HF_TOKEN"):
        raise SystemExit("Configure HF_TOKEN locally; its value is never printed or uploaded")
    api = HfApi(token=os.environ["HF_TOKEN"])
    owner = api.whoami()["name"]
    repo_id = f"{owner}/{name}"
    api.create_repo(repo_id, repo_type="space", space_sdk="gradio", exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        stage = Path(directory)
        shutil.copyfile(ROOT / "demo_app.py", stage / "app.py")
        shutil.copyfile(ROOT / "requirements-demo.txt", stage / "requirements.txt")
        for filename in ("invoice.pdf", "purchase_order.pdf", "result.json"):
            (stage / "demo").mkdir(exist_ok=True)
            shutil.copyfile(ROOT / "demo" / filename, stage / "demo" / filename)
        report = json.loads((ROOT / "results" / "verification.json").read_text())
        (stage / "README.md").write_text(
            "---\ntitle: ReconcileAI sample review\nemoji: 📄\ncolorFrom: green\ncolorTo: yellow\n"
            "sdk: gradio\napp_file: app.py\n---\n\n# ReconcileAI sample review\n\n"
            "Fictional sample documents and frozen extraction only. "
            "No uploads, provider code, secrets or model calls.\n\n"
            "| Verified fixture result | Value |\n| --- | --- |\n"
            f"| Flagged sample mismatches | {report['sample_findings']} |\n\n"
            "```mermaid\nflowchart LR\n  PDF[Fixed sample PDF] --> Render[PDF renderer]\n"
            "  JSON[Precomputed JSON] --> Fields[Fields and mismatches]\n"
            "  Fields --> Highlight[Source bounding box]\n"
            "  Highlight --> Render\n```\n\n"
            "[Source and rerunnable verification](https://github.com/vi-nayKR/multimodal-document-intelligence).\n",
            encoding="utf-8",
        )
        commit = api.upload_folder(
            repo_id=repo_id,
            repo_type="space",
            folder_path=stage,
            commit_message="Deploy sample-only ReconcileAI review demo",
        )
    import httpx

    deployment = {
        "space_url": f"https://huggingface.co/spaces/{repo_id}",
        "mode": "sample_only",
        "commit": commit.oid,
        "public_ready": False,
        "uploaded_files": [
            "app.py",
            "requirements.txt",
            "README.md",
            "demo/invoice.pdf",
            "demo/purchase_order.pdf",
            "demo/result.json",
        ],
    }
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        runtime = api.get_space_runtime(repo_id)
        deployment["stage"] = str(runtime.stage)
        if runtime.stage == "RUNNING":
            domain = (runtime.raw.get("domains") or [{}])[0].get("domain")
            if domain:
                try:
                    response = httpx.get(f"https://{domain}/config", timeout=15, follow_redirects=True)
                    deployment["public_ready"] = (
                        response.status_code == 200
                        and response.json().get("title") == "ReconcileAI sample review"
                    )
                except (httpx.HTTPError, ValueError):
                    pass
            if deployment["public_ready"]:
                break
        if runtime.stage in {"BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR"}:
            break
        time.sleep(5)
    (ROOT / "results/deployment.json").write_text(json.dumps(deployment, indent=2) + "\n")
    print(deployment["space_url"])
    if not deployment["public_ready"]:
        raise SystemExit("Upload complete, but public readiness was not verified; inspect Space build status")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="reconcileai-samples")
    main(parser.parse_args().name)
