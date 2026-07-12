from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]


def test_centinela_sync_workflow_parses():
    wf = yaml.safe_load((_ROOT / ".github/workflows/centinela-sync.yml").read_text())
    # PyYAML parses the bare key `on:` as the boolean True (YAML 1.1), not "on".
    on = wf.get("on", wf.get(True))
    assert "catalog-lock-updated" in on["repository_dispatch"]["types"]
    steps = wf["jobs"]["sync"]["steps"]
    # the command is invoked as a Python function (astromeshctl can't compose the plugin in CI)
    assert any("plan_promotion_command" in str(s.get("run", "")) for s in steps)
