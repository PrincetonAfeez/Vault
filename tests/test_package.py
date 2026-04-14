from __future__ import annotations

import importlib


def test_vault_public_exports_match_domain() -> None:
    vault_pkg = importlib.import_module("vault")
    domain = importlib.import_module("vault.domain")
    for name in vault_pkg.__all__:
        assert hasattr(domain, name), f"missing domain symbol: {name}"
        assert getattr(vault_pkg, name) is getattr(domain, name)


def test_vault_cli_not_reexported() -> None:
    import vault

    assert "VaultCLI" not in vault.__all__
