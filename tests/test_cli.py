from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest

from tests.helpers import scripted_input
from vault.cli import VaultCLI, build_parser, main
from vault.domain import AccessLevel, ItemCondition, Vault, VaultError


class TestBuildParser:
    def test_demo_flag(self) -> None:
        p = build_parser()
        args = p.parse_args(["--demo"])
        assert args.demo is True

    def test_no_demo_default(self) -> None:
        p = build_parser()
        args = p.parse_args([])
        assert args.demo is False


class TestMain:
    def test_main_uses_empty_vault_without_demo(self) -> None:
        with patch("vault.cli.VaultCLI") as vc:
            vc.return_value.run.return_value = 0
            assert main([]) == 0
            passed = vc.call_args[0][0]
            assert passed is None

    def test_main_passes_demo_vault(self) -> None:
        with patch("vault.cli.VaultCLI") as vc:
            vc.return_value.run.return_value = 0
            assert main(["--demo"]) == 0
            passed = vc.call_args[0][0]
            assert isinstance(passed, Vault)
            assert len(list(passed.search())) == 3


class TestVaultCLIPrompts:
    def test_prompt_returns_value(self) -> None:
        cli = VaultCLI(Vault())
        with patch("builtins.input", return_value="hello"):
            assert VaultCLI._prompt("L") == "hello"

    def test_prompt_default_when_blank(self) -> None:
        with patch("builtins.input", return_value=""):
            assert VaultCLI._prompt("L", default="D") == "D"

    def test_prompt_allow_blank(self) -> None:
        with patch("builtins.input", return_value=""):
            assert VaultCLI._prompt("L", allow_blank=True) == ""

    def test_prompt_money_strips_formatting(self) -> None:
        with patch("builtins.input", return_value="$1,234.50"):
            assert VaultCLI._prompt_money("M") == Decimal("1234.50")

    def test_prompt_money_retries_on_invalid(self) -> None:
        replies = iter(["bad", "10.00"])

        def fake_input(_: str = "") -> str:
            return next(replies)

        with patch("builtins.input", fake_input):
            with patch("builtins.print"):
                assert VaultCLI._prompt_money("M") == Decimal("10.00")

    def test_prompt_enum_parses_name(self) -> None:
        with patch("builtins.input", return_value="STAFF"):
            assert VaultCLI._prompt_enum(AccessLevel, "A") is AccessLevel.STAFF

    def test_prompt_enum_default_on_blank(self) -> None:
        with patch("builtins.input", return_value=""):
            assert (
                VaultCLI._prompt_enum(AccessLevel, "A", default=AccessLevel.MANAGER)
                is AccessLevel.MANAGER
            )


class TestVaultCLIRun:
    def test_run_exits_on_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        cli = VaultCLI(Vault())
        with patch("builtins.input", return_value="0"):
            assert cli.run() == 0
        out = capsys.readouterr().out
        assert "Vault OS" in out
        assert "Closing Vault OS" in out

    def test_run_unknown_option(self, capsys: pytest.CaptureFixture[str]) -> None:
        cli = VaultCLI(Vault())
        replies = iter(["nope", "0"])

        def fake_input(_: str = "") -> str:
            return next(replies)

        with patch("builtins.input", fake_input):
            assert cli.run() == 0
        assert "Unknown option" in capsys.readouterr().out

    def test_run_catches_vault_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        cli = VaultCLI(Vault())
        seq = iter(["1", "0"])

        def fake_input(_: str = "") -> str:
            return next(seq)

        def add_raises() -> None:
            raise VaultError("nope")

        with patch("builtins.input", fake_input):
            with patch.object(cli, "_handle_add", side_effect=add_raises):
                assert cli.run() == 0
        out = capsys.readouterr().out
        assert "Operation blocked" in out
        assert "nope" in out


class TestRenderItems:
    def test_render_items_empty(self, capsys: pytest.CaptureFixture[str]) -> None:
        VaultCLI(Vault())._render_items([])
        assert "No items matched" in capsys.readouterr().out

    def test_render_items_table(self, capsys: pytest.CaptureFixture[str]) -> None:
        v = Vault()
        snap = v.add_item("N", "document", "12.34")
        VaultCLI(v)._render_items([snap])
        out = capsys.readouterr().out
        assert "ID" in out and "N" in out


class TestHandleFlows:
    def test_handle_add_minimal(self, capsys: pytest.CaptureFixture[str]) -> None:
        lines = [
            "1",
            "Pen",
            "document",
            "5",
            "",
            "",
            "",
            "",
            "0",
        ]
        with scripted_input(lines):
            cli = VaultCLI(Vault())
            assert cli.run() == 0
        assert "Added ITM-" in capsys.readouterr().out

    def test_handle_checkout_checkin(self, capsys: pytest.CaptureFixture[str]) -> None:
        v = Vault()
        item = v.add_item("Box", "document", "100")
        lines = [
            "2",
            item.item_id,
            "Alex",
            "STAFF",
            "",
            "3",
            item.item_id,
            "Alex",
            "STAFF",
            "",
            "0",
        ]
        with scripted_input(lines):
            assert VaultCLI(v).run() == 0
        out = capsys.readouterr().out
        assert "checked out" in out
        assert "checked back" in out

    def test_handle_audit_search_reconcile_summary_list(self, capsys: pytest.CaptureFixture[str]) -> None:
        v = Vault()
        item = v.add_item("Doc", "document", "50")
        lines = [
            "6",
            item.item_id,
            "7",
            "",
            "",
            "",
            "",
            "",
            "8",
            item.item_id,
            "9",
            "10",
            "0",
        ]
        with scripted_input(lines):
            assert VaultCLI(v).run() == 0
        out = capsys.readouterr().out
        assert "Audit Report" in out
        assert "Reconciliation Report" in out
        assert "Vault Summary" in out

    def test_handle_condition_and_retire(self, capsys: pytest.CaptureFixture[str]) -> None:
        v = Vault()
        item = v.add_item("Old", "document", "10", condition=ItemCondition.GOOD)
        lines = [
            "4",
            item.item_id,
            "FAIR",
            "A",
            "STAFF",
            "",
            "5",
            item.item_id,
            "M",
            "MANAGER",
            "",
            "0",
        ]
        with scripted_input(lines):
            assert VaultCLI(v).run() == 0
        out = capsys.readouterr().out
        assert "condition updated" in out
        assert "retired" in out
