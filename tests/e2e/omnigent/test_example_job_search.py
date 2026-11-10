"""Happy-path E2E coverage for the job-search example."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import yaml

from tests.e2e.omnigent._example_helpers import run_one_shot_at_path
from tests.e2e.omnigent.conftest import configure_mock_llm

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_job_search_tailors_resume_and_tracks_application(
    tmp_path: Path,
    omnigent_python: Path,
    omnigent_repo_root: Path,
    mock_credentials_env: dict[str, str],
    mock_llm_server_url: str,
) -> None:
    """Tailor a resume and create a tracker row without changing the source resume."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    master_resume = (
        "# Jordan Lee\n\n"
        "Data analyst with experience using SQL and Python for reporting.\n"
    )
    (workspace / "resume.md").write_text(master_resume, encoding="utf-8")

    tailored_resume = (
        "# Jordan Lee — Data Analyst\n\n"
        "Data analyst experienced in SQL and Python reporting.\n"
    )
    tracker = (
        "company,role,url,status,applied_on,next_step,notes\n"
        "Acme,Data Analyst,https://example.test/jobs/123,draft,,,Resume tailored\n"
    )
    model = f"mock-job-search-{uuid.uuid4().hex[:8]}"
    configure_mock_llm(
        mock_llm_server_url,
        [
            {
                "tool_calls": [
                    {
                        "call_id": "read-master-resume",
                        "name": "sys_os_read",
                        "arguments": json.dumps({"path": "resume.md"}),
                    }
                ]
            },
            {
                "tool_calls": [
                    {
                        "call_id": "write-tailored-resume",
                        "name": "sys_os_write",
                        "arguments": json.dumps(
                            {
                                "path": "applications/acme-data-analyst/resume.md",
                                "content": tailored_resume,
                            }
                        ),
                    }
                ]
            },
            {
                "tool_calls": [
                    {
                        "call_id": "write-application-tracker",
                        "name": "sys_os_write",
                        "arguments": json.dumps(
                            {"path": "applications.csv", "content": tracker}
                        ),
                    }
                ]
            },
            {"text": "TAILORED_OUTPUT_OK\nResume and application tracker are ready."},
        ],
        key=model,
    )

    config = yaml.safe_load(
        (_REPO_ROOT / "examples" / "job-search" / "config.yaml").read_text(
            encoding="utf-8"
        )
    )
    config["os_env"] = {
        "type": "caller_process",
        "cwd": str(workspace),
        "sandbox": {"type": "none"},
    }
    test_config = tmp_path / "job-search.yaml"
    test_config.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = run_one_shot_at_path(
        omnigent_python=omnigent_python,
        omnigent_repo_root=omnigent_repo_root,
        omnigent_credentials_env=mock_credentials_env,
        yaml_path=test_config,
        prompt=(
            "Tailor my resume for the Acme Data Analyst role using this job "
            "description: requires SQL and Python reporting. Save the tailored "
            "resume and add the application to the tracker."
        ),
        harness="openai-agents",
        model=model,
    )

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "TAILORED_OUTPUT_OK" in result.stdout
    assert (workspace / "applications" / "acme-data-analyst" / "resume.md").read_text(
        encoding="utf-8"
    ) == tailored_resume
    assert (workspace / "applications.csv").read_text(encoding="utf-8") == tracker
    assert (workspace / "resume.md").read_text(encoding="utf-8") == master_resume
