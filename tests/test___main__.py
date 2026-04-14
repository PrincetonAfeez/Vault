from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_python_m_vault_help() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "vault", "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    combined = f"{result.stdout}\n{result.stderr}".lower()
    assert "vault" in combined


def test___main___reexports_cli_main() -> None:
    from vault.__main__ import main as entry_main
    from vault.cli import main as cli_main

    assert entry_main is cli_main
