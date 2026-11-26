"""Covers FAILURE_SCENARIOS.md "Failed deployment" and "Failed migration":
deploy.sh must never restart the service when an earlier step fails.

Runs the real scripts against a throwaway copy of the repo layout, with
pip/alembic/npm/sudo/curl replaced by stubs that log their calls."""
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# FAIL_ON is a prefix of the call to fail, e.g. "alembic" or "alembic upgrade".
STUB = """#!/usr/bin/env bash
call="$(basename "$0") $*"
echo "$call" >> "$CALL_LOG"
if [[ -n "${FAIL_ON:-}" && "$call" == "$FAIL_ON"* ]]; then exit 1; fi
exit 0
"""


@pytest.fixture
def sandbox(tmp_path: Path):
    shutil.copytree(REPO_ROOT / "scripts", tmp_path / "scripts")
    (tmp_path / "backend" / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / "backend" / ".venv" / "bin" / "activate").write_text("")
    (tmp_path / "frontend").mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("pip", "alembic", "npm", "sudo", "curl", "sleep"):
        path = bin_dir / name
        path.write_text(STUB)
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return tmp_path


def _run_deploy(sandbox: Path, fail_on: str = "") -> tuple[int, list[str], str]:
    log = sandbox / "calls.log"
    log.write_text("")
    env = {
        **os.environ,
        "PATH": f"{sandbox / 'bin'}:{os.environ['PATH']}",
        "CALL_LOG": str(log),
        "FAIL_ON": fail_on,
    }
    result = subprocess.run(
        ["bash", str(sandbox / "scripts" / "deploy.sh")], env=env, capture_output=True, text=True, timeout=30
    )
    return result.returncode, log.read_text().splitlines(), result.stderr


def _restarted(calls: list[str]) -> bool:
    return any(call.startswith("sudo systemctl restart") for call in calls)


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_successful_deploy_restarts_and_health_checks(sandbox: Path):
    code, calls, _ = _run_deploy(sandbox)

    assert code == 0
    assert _restarted(calls)
    assert any(call.startswith("curl") for call in calls)


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
@pytest.mark.parametrize("failing_step", ["pip", "alembic current", "alembic upgrade", "npm ci", "npm run build"])
def test_failed_step_never_restarts_service(sandbox: Path, failing_step: str):
    code, calls, _ = _run_deploy(sandbox, fail_on=failing_step)

    assert code != 0
    assert not _restarted(calls)


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_failed_migration_prints_recovery_steps(sandbox: Path):
    code, _, stderr = _run_deploy(sandbox, fail_on="alembic upgrade")

    assert code != 0
    assert "MIGRATION FAILED" in stderr
    assert "alembic downgrade -1" in stderr


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_failed_health_check_exits_with_rollback_hint(sandbox: Path):
    code, calls, stderr = _run_deploy(sandbox, fail_on="curl")

    assert code == 1
    assert _restarted(calls)
    assert sum(call.startswith("curl") for call in calls) == 10
    assert "DEPLOYMENT FAILED HEALTH CHECK" in stderr
