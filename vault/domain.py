from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum, IntEnum
from typing import Iterable


MoneyLike = Decimal | int | float | str


class VaultError(Exception):
    """Base exception for vault operations."""


class DuplicateItemError(VaultError):
    """Raised when a new item collides with an existing identifier."""


class ItemNotFoundError(VaultError):
    """Raised when an item cannot be found in the vault."""


class ItemStateError(VaultError):
    """Raised when an item's status blocks a requested operation."""


class AccessDeniedError(VaultError):
    """Raised when the actor's access level is not sufficient."""


class AccessLevel(IntEnum):
    VISITOR = 1
    STAFF = 2
    SUPERVISOR = 3
    MANAGER = 4
    DIRECTOR = 5

    @classmethod
    def parse(cls, value: "AccessLevel | str") -> "AccessLevel":
        if isinstance(value, cls):
            return value
        normalized = str(value).strip().upper()
        return cls[normalized]


class _TextEnum(str, Enum):
    @classmethod
    def parse(cls, value: "_TextEnum | str") -> "_TextEnum":
        if isinstance(value, cls):
            return value
        normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
        for member in cls:
            if member.value == normalized:
                return member
        raise ValueError(f"Unsupported {cls.__name__}: {value}")


class ItemStatus(_TextEnum):
    AVAILABLE = "available"
    CHECKED_OUT = "checked_out"
    RESERVED = "reserved"
    RETIRED = "retired"


class ItemCondition(_TextEnum):
    MINT = "mint"
    GOOD = "good"
    FAIR = "fair"
    DAMAGED = "damaged"


class AuditAction(_TextEnum):
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"
    CONDITION_CHANGED = "condition_changed"
    RETIRED = "retired"


def _to_money(value: MoneyLike) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _format_money(value: Decimal) -> str:
    return f"${value:,.2f}"


def _normalize_category(category: str) -> str:
    return category.strip().lower().replace(" ", "_")


@dataclass(frozen=True, slots=True)
class CustodyRecord:
    timestamp: datetime
    item_id: str
    action: AuditAction
    actor_name: str
    actor_access_level: AccessLevel
    notes: str = ""

    def render(self) -> str:
        note = f" | {self.notes}" if self.notes else ""
        return (
            f"{self.timestamp.astimezone(timezone.utc).isoformat()} | "
            f"{self.action.value} | {self.actor_name} ({self.actor_access_level.name}){note}"
        )


@dataclass(frozen=True, slots=True)
class ItemSnapshot:
    item_id: str
    name: str
    category: str
    monetary_value: Decimal
    status: ItemStatus
    condition: ItemCondition
    current_holder: str | None

    def render_row(self) -> str:
        holder = self.current_holder or "-"
        return (
            f"{self.item_id:<10} {self.name:<22} {self.category:<14} "
            f"{_format_money(self.monetary_value):>12} {self.status.value:<12} "
            f"{self.condition.value:<8} {holder}"
        )


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    observed_ids: tuple[str, ...]
    missing_ids: tuple[str, ...]
    unexpected_ids: tuple[str, ...]

    @property
    def is_balanced(self) -> bool:
        return not self.missing_ids and not self.unexpected_ids

    def format_report(self) -> str:
        lines = ["Reconciliation Report", f"Observed IDs: {', '.join(self.observed_ids) or 'none'}"]
        if self.is_balanced:
            lines.append("Result: inventory matches expected physical count.")
            return "\n".join(lines)
        lines.append(f"Missing from count: {', '.join(self.missing_ids) or 'none'}")
        lines.append(f"Unexpected in count: {', '.join(self.unexpected_ids) or 'none'}")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class VaultSummary:
    total_items: int
    items_by_status: dict[ItemStatus, int]
    total_value_in_vault: Decimal
    total_value_checked_out: Decimal

    def format_report(self) -> str:
        lines = [
            "Vault Summary",
            f"Total items: {self.total_items}",
            "Items by status:",
        ]
        for status in ItemStatus:
            lines.append(f"  - {status.value}: {self.items_by_status.get(status, 0)}")
        lines.append(f"Total value in vault: {_format_money(self.total_value_in_vault)}")
        lines.append(f"Total value checked out: {_format_money(self.total_value_checked_out)}")
        return "\n".join(lines)


@dataclass(slots=True)
class Item:
    item_id: str
    name: str
    category: str
    monetary_value: Decimal
    status: ItemStatus = ItemStatus.AVAILABLE
    condition: ItemCondition = ItemCondition.GOOD
    current_holder: str | None = None
    _custody_chain: list[CustodyRecord] = field(default_factory=list, repr=False)

    @property
    def custody_chain(self) -> tuple[CustodyRecord, ...]:
        return tuple(self._custody_chain)

    def record(self, entry: CustodyRecord) -> None:
        self._custody_chain.append(entry)

    def apply_restored_custody_chain(self, records: list[CustodyRecord]) -> None:
        """Replace custody history (integration persistence restore only)."""
        self._custody_chain = list(records)


class Vault:
    """Encapsulated inventory controller for all vault operations."""

    _CATEGORY_ACCESS_RULES = {
        "artifact": AccessLevel.MANAGER,
        "bullion": AccessLevel.MANAGER,
        "classified": AccessLevel.DIRECTOR,
        "jewelry": AccessLevel.SUPERVISOR,
        "prototype": AccessLevel.SUPERVISOR,
    }

    def __init__(self) -> None:
        self._items: dict[str, Item] = {}
        self._sequence = 0

    def add_item(
        self,
        name: str,
        category: str,
        monetary_value: MoneyLike,
        *,
        item_id: str | None = None,
        status: ItemStatus | str = ItemStatus.AVAILABLE,
        condition: ItemCondition | str = ItemCondition.GOOD,
        current_holder: str | None = None,
        actor_name: str = "SYSTEM",
        actor_access_level: AccessLevel | str = AccessLevel.MANAGER,
        notes: str = "Item registered in vault.",
    ) -> ItemSnapshot:
        resolved_status = ItemStatus.parse(status)
        resolved_condition = ItemCondition.parse(condition)
        resolved_access = AccessLevel.parse(actor_access_level)
        normalized_category = _normalize_category(category)
        new_item_id = item_id or self._next_item_id()
        if new_item_id in self._items:
            raise DuplicateItemError(f"Item {new_item_id} already exists.")
        if resolved_status == ItemStatus.CHECKED_OUT and not current_holder:
            raise ItemStateError("Checked-out items require a current holder.")

        item = Item(
            item_id=new_item_id,
            name=name.strip(),
            category=normalized_category,
            monetary_value=_to_money(monetary_value),
            status=resolved_status,
            condition=resolved_condition,
            current_holder=current_holder.strip() if current_holder else None,
        )
        self._items[new_item_id] = item
        self._append_record(
            item,
            action=AuditAction.CHECKED_IN,
            actor_name=actor_name,
            actor_access_level=resolved_access,
            notes=notes,
        )
        return self._snapshot(item)

    def check_out(
        self,
        item_id: str,
        *,
        actor_name: str,
        actor_access_level: AccessLevel | str,
        notes: str = "",
    ) -> ItemSnapshot:
        item = self._require_item(item_id)
        if item.status == ItemStatus.CHECKED_OUT:
            raise ItemStateError(f"Item {item_id} is already checked out.")
        if item.status == ItemStatus.RESERVED:
            raise ItemStateError(f"Item {item_id} is reserved and cannot be checked out.")
        if item.status == ItemStatus.RETIRED:
            raise ItemStateError(f"Item {item_id} is retired and cannot be checked out.")

        resolved_access = AccessLevel.parse(actor_access_level)
        required_access = self._required_access(item)
        if resolved_access < required_access:
            raise AccessDeniedError(
                f"{item.item_id} requires {required_access.name} access to check out."
            )

        item.status = ItemStatus.CHECKED_OUT
        item.current_holder = actor_name.strip()
        self._append_record(
            item,
            action=AuditAction.CHECKED_OUT,
            actor_name=actor_name,
            actor_access_level=resolved_access,
            notes=notes,
        )
        return self._snapshot(item)

    def check_in(
        self,
        item_id: str,
        *,
        actor_name: str,
        actor_access_level: AccessLevel | str,
        notes: str = "",
    ) -> ItemSnapshot:
        item = self._require_item(item_id)
        if item.status != ItemStatus.CHECKED_OUT:
            raise ItemStateError(f"Item {item_id} is not currently checked out.")

        resolved_access = AccessLevel.parse(actor_access_level)
        if resolved_access < AccessLevel.STAFF:
            raise AccessDeniedError("Check-in requires at least STAFF access.")

        item.status = ItemStatus.AVAILABLE
        item.current_holder = None
        self._append_record(
            item,
            action=AuditAction.CHECKED_IN,
            actor_name=actor_name,
            actor_access_level=resolved_access,
            notes=notes,
        )
        return self._snapshot(item)

    def update_condition(
        self,
        item_id: str,
        new_condition: ItemCondition | str,
        *,
        actor_name: str,
        actor_access_level: AccessLevel | str,
        notes: str = "",
    ) -> ItemSnapshot:
        item = self._require_item(item_id)
        if item.status == ItemStatus.RETIRED:
            raise ItemStateError(f"Item {item_id} is retired and its condition cannot be updated.")

        resolved_access = AccessLevel.parse(actor_access_level)
        if resolved_access < AccessLevel.STAFF:
            raise AccessDeniedError("Condition updates require at least STAFF access.")

        resolved_condition = ItemCondition.parse(new_condition)
        if item.condition == resolved_condition:
            raise ItemStateError(f"Item {item_id} is already marked {resolved_condition.value}.")

        item.condition = resolved_condition
        combined_notes = f"Condition set to {resolved_condition.value}."
        if notes:
            combined_notes = f"{combined_notes} {notes}"
        self._append_record(
            item,
            action=AuditAction.CONDITION_CHANGED,
            actor_name=actor_name,
            actor_access_level=resolved_access,
            notes=combined_notes,
        )
        return self._snapshot(item)

    def retire_item(
        self,
        item_id: str,
        *,
        actor_name: str,
        actor_access_level: AccessLevel | str,
        notes: str = "",
    ) -> ItemSnapshot:
        item = self._require_item(item_id)
        if item.status == ItemStatus.RETIRED:
            raise ItemStateError(f"Item {item_id} is already retired.")
        if item.status == ItemStatus.CHECKED_OUT:
            raise ItemStateError(f"Item {item_id} must be checked in before retirement.")

        resolved_access = AccessLevel.parse(actor_access_level)
        if resolved_access < AccessLevel.MANAGER:
            raise AccessDeniedError("Retirement requires MANAGER access.")

        item.status = ItemStatus.RETIRED
        item.current_holder = None
        self._append_record(
            item,
            action=AuditAction.RETIRED,
            actor_name=actor_name,
            actor_access_level=resolved_access,
            notes=notes or "Item retired from service.",
        )
        return self._snapshot(item)

    def audit_item(self, item_id: str) -> str:
        item = self._require_item(item_id)
        lines = [
            f"Audit Report for {item.item_id} - {item.name}",
            f"Category: {item.category}",
            f"Value: {_format_money(item.monetary_value)}",
            f"Status: {item.status.value}",
            f"Condition: {item.condition.value}",
            f"Current holder: {item.current_holder or 'none'}",
            "Custody chain:",
        ]
        if not item.custody_chain:
            lines.append("  (no custody records)")
            return "\n".join(lines)
        for index, record in enumerate(item.custody_chain, start=1):
            lines.append(f"  {index}. {record.render()}")
        return "\n".join(lines)

    def search(
        self,
        *,
        category: str | None = None,
        status: ItemStatus | str | None = None,
        condition: ItemCondition | str | None = None,
        min_value: MoneyLike | None = None,
        max_value: MoneyLike | None = None,
    ) -> list[ItemSnapshot]:
        resolved_category = _normalize_category(category) if category else None
        resolved_status = ItemStatus.parse(status) if status else None
        resolved_condition = ItemCondition.parse(condition) if condition else None
        resolved_min = _to_money(min_value) if min_value is not None else None
        resolved_max = _to_money(max_value) if max_value is not None else None

        results: list[ItemSnapshot] = []
        for item in self._items.values():
            if resolved_category and item.category != resolved_category:
                continue
            if resolved_status and item.status != resolved_status:
                continue
            if resolved_condition and item.condition != resolved_condition:
                continue
            if resolved_min is not None and item.monetary_value < resolved_min:
                continue
            if resolved_max is not None and item.monetary_value > resolved_max:
                continue
            results.append(self._snapshot(item))
        return sorted(results, key=lambda snapshot: snapshot.item_id)

    def reconcile(self, observed_item_ids: Iterable[str]) -> ReconciliationReport:
        observed = tuple(sorted({item_id.strip() for item_id in observed_item_ids if item_id.strip()}))
        expected_present = {
            item_id for item_id, item in self._items.items() if item.status != ItemStatus.CHECKED_OUT
        }
        missing = tuple(sorted(expected_present - set(observed)))
        unexpected = tuple(sorted(set(observed) - expected_present))
        return ReconciliationReport(
            observed_ids=observed,
            missing_ids=missing,
            unexpected_ids=unexpected,
        )

    def apply_restored_inventory(self, *, sequence: int, items: dict[str, Item]) -> None:
        """Replace inventory and issuing counter (integration persistence restore only)."""
        self._sequence = sequence
        self._items = dict(items)

    def iter_items_sorted_by_id(self) -> list[Item]:
        """Inventory items sorted by ``item_id`` (stable export order)."""
        return sorted(self._items.values(), key=lambda item: item.item_id)

    @property
    def persisted_issue_sequence(self) -> int:
        """High-water counter backing ``ITM-####`` ids (for persistence)."""
        return self._sequence

    def summary(self) -> VaultSummary:
        counts = Counter(item.status for item in self._items.values())
        total_value_in_vault = sum(
            (
                item.monetary_value
                for item in self._items.values()
                if item.status != ItemStatus.CHECKED_OUT
            ),
            start=Decimal("0.00"),
        )
        total_value_checked_out = sum(
            (
                item.monetary_value
                for item in self._items.values()
                if item.status == ItemStatus.CHECKED_OUT
            ),
            start=Decimal("0.00"),
        )
        return VaultSummary(
            total_items=len(self._items),
            items_by_status=dict(counts),
            total_value_in_vault=total_value_in_vault,
            total_value_checked_out=total_value_checked_out,
        )

    def _next_item_id(self) -> str:
        self._sequence += 1
        return f"ITM-{self._sequence:04d}"

    def _require_item(self, item_id: str) -> Item:
        try:
            return self._items[item_id]
        except KeyError as exc:
            raise ItemNotFoundError(f"Item {item_id} was not found.") from exc

    def _required_access(self, item: Item) -> AccessLevel:
        category_level = self._CATEGORY_ACCESS_RULES.get(item.category, AccessLevel.STAFF)
        if item.monetary_value >= Decimal("500000.00"):
            value_level = AccessLevel.DIRECTOR
        elif item.monetary_value >= Decimal("100000.00"):
            value_level = AccessLevel.MANAGER
        elif item.monetary_value >= Decimal("25000.00"):
            value_level = AccessLevel.SUPERVISOR
        else:
            value_level = AccessLevel.STAFF
        return max(category_level, value_level)

    def _append_record(
        self,
        item: Item,
        *,
        action: AuditAction,
        actor_name: str,
        actor_access_level: AccessLevel,
        notes: str = "",
    ) -> None:
        item.record(
            CustodyRecord(
                timestamp=datetime.now(timezone.utc),
                item_id=item.item_id,
                action=action,
                actor_name=actor_name.strip(),
                actor_access_level=actor_access_level,
                notes=notes.strip(),
            )
        )

    @staticmethod
    def _snapshot(item: Item) -> ItemSnapshot:
        return ItemSnapshot(
            item_id=item.item_id,
            name=item.name,
            category=item.category,
            monetary_value=item.monetary_value,
            status=item.status,
            condition=item.condition,
            current_holder=item.current_holder,
        )


def seed_demo_vault() -> Vault:
    vault = Vault()
    vault.add_item(
        "Bronze Ledger",
        "document",
        "1200",
        condition=ItemCondition.GOOD,
        actor_name="SYSTEM",
    )
    vault.add_item(
        "Aurora Necklace",
        "jewelry",
        "87500",
        condition=ItemCondition.MINT,
        actor_name="SYSTEM",
    )
    vault.add_item(
        "Prototype Keycard",
        "prototype",
        "15000",
        status=ItemStatus.RESERVED,
        condition=ItemCondition.GOOD,
        actor_name="SYSTEM",
        notes="Reserved for engineering validation.",
    )
    return vault
