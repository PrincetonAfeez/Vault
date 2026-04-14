from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation

from .domain import (
    AccessLevel,
    ItemCondition,
    ItemStatus,
    Vault,
    VaultError,
    seed_demo_vault,
)


class VaultCLI:
    def __init__(self, vault: Vault | None = None) -> None:
        self.vault = vault or Vault()

    def run(self) -> int:
        print("Vault OS - Secure Inventory Manager")
        print("Every action is routed through the vault and captured in the audit chain.")
        while True:
            print()
            print("1. Add item")
            print("2. Check out item")
            print("3. Check in item")
            print("4. Update condition")
            print("5. Retire item")
            print("6. Audit item")
            print("7. Search inventory")
            print("8. Run reconciliation")
            print("9. View summary")
            print("10. List all items")
            print("0. Exit")
            choice = input("Select an option: ").strip().lower()
            if choice in {"0", "q", "quit", "exit"}:
                print("Closing Vault OS.")
                return 0
            try:
                if choice in {"1", "add"}:
                    self._handle_add()
                elif choice in {"2", "checkout", "check_out"}:
                    self._handle_checkout()
                elif choice in {"3", "checkin", "check_in"}:
                    self._handle_checkin()
                elif choice in {"4", "condition", "update_condition"}:
                    self._handle_condition()
                elif choice in {"5", "retire"}:
                    self._handle_retire()
                elif choice in {"6", "audit"}:
                    self._handle_audit()
                elif choice in {"7", "search"}:
                    self._handle_search()
                elif choice in {"8", "reconcile"}:
                    self._handle_reconcile()
                elif choice in {"9", "summary"}:
                    self._handle_summary()
                elif choice in {"10", "list"}:
                    self._render_items(self.vault.search())
                else:
                    print("Unknown option. Choose a menu number or type exit.")
            except VaultError as exc:
                print(f"Operation blocked: {exc}")
        return 0

    def _handle_add(self) -> None:
        name = self._prompt("Item name")
        category = self._prompt("Category")
        value = self._prompt_money("Monetary value")
        condition = self._prompt_enum(ItemCondition, "Condition", default=ItemCondition.GOOD)
        status = self._prompt_enum(ItemStatus, "Initial status", default=ItemStatus.AVAILABLE)
        current_holder = None
        if status == ItemStatus.CHECKED_OUT:
            current_holder = self._prompt("Current holder")
        actor_name = self._prompt("Operator name", default="SYSTEM")
        actor_access = self._prompt_enum(
            AccessLevel,
            "Operator access level",
            default=AccessLevel.MANAGER,
        )
        item = self.vault.add_item(
            name,
            category,
            value,
            condition=condition,
            status=status,
            current_holder=current_holder,
            actor_name=actor_name,
            actor_access_level=actor_access,
        )
        print(f"Added {item.item_id}: {item.name} ({item.status.value})")

    def _handle_checkout(self) -> None:
        item_id = self._prompt("Item ID")
        actor_name = self._prompt("Actor name")
        access = self._prompt_enum(AccessLevel, "Actor access level")
        notes = self._prompt("Notes", allow_blank=True)
        item = self.vault.check_out(
            item_id,
            actor_name=actor_name,
            actor_access_level=access,
            notes=notes,
        )
        print(f"{item.item_id} checked out to {item.current_holder}.")

    def _handle_checkin(self) -> None:
        item_id = self._prompt("Item ID")
        actor_name = self._prompt("Actor name")
        access = self._prompt_enum(AccessLevel, "Actor access level")
        notes = self._prompt("Notes", allow_blank=True)
        item = self.vault.check_in(
            item_id,
            actor_name=actor_name,
            actor_access_level=access,
            notes=notes,
        )
        print(f"{item.item_id} checked back into the vault.")

    def _handle_condition(self) -> None:
        item_id = self._prompt("Item ID")
        new_condition = self._prompt_enum(ItemCondition, "New condition")
        actor_name = self._prompt("Actor name")
        access = self._prompt_enum(AccessLevel, "Actor access level")
        notes = self._prompt("Notes", allow_blank=True)
        item = self.vault.update_condition(
            item_id,
            new_condition,
            actor_name=actor_name,
            actor_access_level=access,
            notes=notes,
        )
        print(f"{item.item_id} condition updated to {item.condition.value}.")

    def _handle_retire(self) -> None:
        item_id = self._prompt("Item ID")
        actor_name = self._prompt("Actor name")
        access = self._prompt_enum(AccessLevel, "Actor access level", default=AccessLevel.MANAGER)
        notes = self._prompt("Notes", allow_blank=True)
        item = self.vault.retire_item(
            item_id,
            actor_name=actor_name,
            actor_access_level=access,
            notes=notes,
        )
        print(f"{item.item_id} retired from service.")

    def _handle_audit(self) -> None:
        item_id = self._prompt("Item ID")
        print(self.vault.audit_item(item_id))

    def _handle_search(self) -> None:
        category = self._prompt("Category filter", allow_blank=True) or None
        status_input = self._prompt("Status filter", allow_blank=True) or None
        condition_input = self._prompt("Condition filter", allow_blank=True) or None
        min_value = self._prompt("Minimum value", allow_blank=True) or None
        max_value = self._prompt("Maximum value", allow_blank=True) or None
        results = self.vault.search(
            category=category,
            status=status_input,
            condition=condition_input,
            min_value=min_value,
            max_value=max_value,
        )
        self._render_items(results)

    def _handle_reconcile(self) -> None:
        raw_ids = self._prompt("Observed item IDs (comma separated)", allow_blank=True)
        observed_ids = [item_id.strip() for item_id in raw_ids.split(",")] if raw_ids else []
        print(self.vault.reconcile(observed_ids).format_report())

    def _handle_summary(self) -> None:
        print(self.vault.summary().format_report())

    def _render_items(self, items) -> None:
        if not items:
            print("No items matched the current query.")
            return
        print(
            f"{'ID':<10} {'Name':<22} {'Category':<14} {'Value':>12} "
            f"{'Status':<12} {'Condition':<8} Holder"
        )
        print("-" * 95)
        for item in items:
            print(item.render_row())

    @staticmethod
    def _prompt(label: str, *, allow_blank: bool = False, default: str | None = None) -> str:
        suffix = f" [{default}]" if default is not None else ""
        while True:
            value = input(f"{label}{suffix}: ").strip()
            if value:
                return value
            if default is not None:
                return default
            if allow_blank:
                return ""
            print("A value is required.")

    @staticmethod
    def _prompt_money(label: str) -> Decimal:
        while True:
            raw = input(f"{label}: ").strip().replace("$", "").replace(",", "")
            try:
                return Decimal(raw).quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError):
                print("Enter a valid monetary amount, for example 1200.00")

    @staticmethod
    def _prompt_enum(enum_cls, label: str, default=None):
        choices = ", ".join(member.name for member in enum_cls)
        suffix = f" [{default.name}]" if default is not None else ""
        while True:
            raw = input(f"{label} ({choices}){suffix}: ").strip()
            if not raw and default is not None:
                return default
            try:
                return enum_cls.parse(raw)
            except (KeyError, ValueError):
                print(f"Choose one of: {choices}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vault",
        description="Launch the Vault OS secure inventory manager.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Start with a small preloaded inventory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cli = VaultCLI(seed_demo_vault() if args.demo else None)
    return cli.run()
