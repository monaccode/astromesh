"""Los scripts de nfpm (.deb y .rpm) no deben parar ni deshabilitar el servicio en un upgrade.

Argumentos nativos: deb prerm `remove|upgrade|...`, postinst `configure <versión-vieja>`;
rpm %preun/%post reciben la cantidad de instancias que quedan (0 = borrado, 1+ = upgrade).
"""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "packaging" / "scripts"


@pytest.fixture
def shims(tmp_path):
    """systemctl/chown/chmod/mkdir falsos que anotan su invocación en calls.log."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    for name in ("systemctl", "chown", "chmod", "mkdir"):
        shim = bin_dir / name
        shim.write_text(f'#!/bin/sh\necho "{name} $*" >> "{log}"\nexit 0\n')
        shim.chmod(0o755)
    return bin_dir, log


def _run(script, args, shims):
    bin_dir, log = shims
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    subprocess.run(["bash", str(SCRIPTS / script), *args], check=True, env=env, capture_output=True)
    return log.read_text().splitlines() if log.exists() else []


def _service_calls(calls):
    return [c for c in calls if c.startswith("systemctl") and "astromeshd" in c]


@pytest.mark.parametrize("args", [["upgrade", "0.1.6"], ["1"]], ids=["deb", "rpm"])
def test_prerm_on_upgrade_leaves_the_service_alone(args, shims):
    assert _service_calls(_run("preremove.sh", args, shims)) == []


@pytest.mark.parametrize("args", [["remove"], ["0"]], ids=["deb", "rpm"])
def test_prerm_on_removal_stops_and_disables(args, shims):
    calls = " ".join(_service_calls(_run("preremove.sh", args, shims)))
    assert "stop" in calls or "is-active" in calls
    assert "disable" in calls or "is-enabled" in calls


@pytest.mark.parametrize("args", [["configure", ""], ["1"]], ids=["deb", "rpm"])
def test_fresh_install_enables_without_starting(args, shims):
    calls = _service_calls(_run("postinstall.sh", args, shims))
    assert "systemctl enable astromeshd.service" in calls
    assert not any("restart" in c or " start" in c for c in calls)


@pytest.mark.parametrize("args", [["configure", "0.1.6"], ["2"]], ids=["deb", "rpm"])
def test_upgrade_restarts_if_running_and_keeps_the_enabled_state(args, shims):
    calls = _service_calls(_run("postinstall.sh", args, shims))
    assert "systemctl try-restart astromeshd.service" in calls
    assert "systemctl enable astromeshd.service" not in calls


@pytest.mark.parametrize(
    "script,args",
    [
        ("postinstall.sh", ["configure", ""]),
        ("postinstall.sh", ["2"]),
        ("preremove.sh", ["remove"]),
        ("postremove.sh", ["remove"]),
    ],
)
def test_scripts_succeed_without_systemctl(script, args, tmp_path):
    """Containers and build chroots have no systemctl: installing must not fail there."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("chown", "chmod", "mkdir"):
        (bin_dir / name).write_text("#!/bin/sh\nexit 0\n")
        (bin_dir / name).chmod(0o755)
    # A PATH with the shims and the shell basics, but no systemctl.
    for tool in ("bash", "sh", "echo", "cat", "getent", "rm"):
        real = subprocess.run(["which", tool], capture_output=True, text=True).stdout.strip()
        if real:
            (bin_dir / tool).symlink_to(real)
    env = {"PATH": str(bin_dir), "HOME": str(tmp_path)}
    result = subprocess.run(
        [str(bin_dir / "bash"), str(SCRIPTS / script), *args], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
