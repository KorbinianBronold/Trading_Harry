"""Tests fuer die Container-Konfiguration.

Hintergrund: `main.py` verlangt zwingend `--run-type`. Wird das Image ohne
angehaengte Argumente gestartet — Run-Button in Docker Desktop, `docker run
<image>`, `docker compose up` — laeuft der ENTRYPOINT ohne Parameter und
argparse bricht mit Exit 2 ab. Ein `CMD`-Default faengt genau diesen Fall ab.

Die Tests laufen ohne Docker: geprueft werden die Dockerfile-Deklaration und
das Verhalten, auf das sie sich stuetzt."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = (ROOT / "Dockerfile").read_text()


def test_entrypoint_is_main_py():
    """Argumente an `docker run` werden an main.py durchgereicht."""
    assert 'ENTRYPOINT ["python", "main.py"]' in DOCKERFILE


def test_dockerfile_defaults_to_help_without_arguments():
    """Ohne CMD endet ein argumentloser Start in einer Usage-Fehlermeldung mit
    Exit 2, was in Docker Desktop wie ein Absturz aussieht. Der Default macht
    das Image stattdessen selbsterklaerend."""
    assert 'CMD ["--help"]' in DOCKERFILE


def test_dockerfile_has_no_default_run_type():
    """Bewusst KEIN echter Run-Type als Default: ein Klick auf Run wuerde sonst
    eine Pipeline gegen die gemountete tracking.db starten. Gleiches Muster wie
    beim historical_loader, wo der stillschweigende Default entfernt wurde."""
    for run_type in ("pre_market", "midday", "close", "evaluate",
                     "weekly", "position_check"):
        assert f'CMD ["--run-type", "{run_type}"]' not in DOCKERFILE


def test_main_help_exits_zero():
    """Verhalten, auf das sich der CMD-Default stuetzt: --help ist Exit 0 und
    listet die Run-Types auf."""
    proc = subprocess.run(
        [sys.executable, "main.py", "--help"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=60,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    assert "--run-type" in proc.stdout
    assert "pre_market" in proc.stdout


def test_main_without_run_type_is_a_usage_error():
    """Der Fall, der den Report ausgeloest hat — bleibt bewusst ein Fehler,
    wenn jemand das Flag vergisst statt gar keins zu uebergeben."""
    proc = subprocess.run(
        [sys.executable, "main.py"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=60,
    )
    assert proc.returncode == 2
    assert "--run-type" in proc.stderr
