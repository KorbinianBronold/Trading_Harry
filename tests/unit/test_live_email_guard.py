"""Schutz um den Live-Mailtest herum.

Der Live-Test in tests/live/ verschickt echte Post. Diese Tests stellen sicher,
dass ein normaler `pytest tests/`-Lauf das niemals ungefragt tut und dass die
Actions-Verdrahtung vorhanden bleibt."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFTEST = (ROOT / "tests" / "conftest.py").read_text()
LIVE_TEST = (ROOT / "tests" / "live" / "test_email_delivery.py").read_text()
WORKFLOW = (ROOT / ".github" / "workflows" / "test.yml").read_text()


def test_live_test_is_skipped_without_the_flag(pytester_or_none=None):
    """Der Standardlauf darf keine Mail verschicken."""
    import subprocess
    import sys
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/live", "-q", "--no-header",
         "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=120,
    )
    assert proc.returncode == 0, f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    assert "skipped" in proc.stdout, (
        f"Live-Test wurde nicht uebersprungen — Standardlauf koennte Mail "
        f"verschicken.\n{proc.stdout}"
    )


def test_flag_and_marker_are_wired_in_conftest():
    assert "--run-live-email" in CONFTEST
    assert "live_email" in CONFTEST
    assert "pytest_collection_modifyitems" in CONFTEST


def test_live_test_carries_the_marker():
    assert "@pytest.mark.live_email" in LIVE_TEST


def test_body_text_is_exactly_what_was_asked_for():
    assert 'BODY = "Test Versand erfolgreich"' in LIVE_TEST


def test_workflow_runs_the_live_email_job_on_every_push():
    """'Bei jeder Aenderung' heisst: an jedem Push, nicht nur auf main."""
    assert "email-delivery:" in WORKFLOW
    assert "--run-live-email" in WORKFLOW
    assert 'branches: ["**"]' in WORKFLOW


def test_workflow_passes_the_sendgrid_secret():
    """Der Job muss den Secret-Wert bekommen — nur der zaehlt fuer Produktion."""
    for name in ("SENDGRID_API_KEY", "EMAIL_FROM", "EMAIL_TO"):
        assert f"secrets.{name}" in WORKFLOW


def test_default_test_job_does_not_enable_live_email():
    """Der Coverage-Job darf den Live-Versand nicht mitziehen."""
    job = WORKFLOW.split("email-delivery:")[0]
    assert "--run-live-email" not in job
