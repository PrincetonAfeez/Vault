from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from vault.domain import (
    AccessDeniedError,
    AccessLevel,
    AuditAction,
    CustodyRecord,
    DuplicateItemError,
    Item,
    ItemCondition,
    ItemNotFoundError,
    ItemSnapshot,
    ItemStateError,
    ItemStatus,
    ReconciliationReport,
    Vault,
    VaultSummary,
    seed_demo_vault,
)


class TestEnumsAndParsing:
    def test_access_level_parse_instance_and_string(self) -> None:
        assert AccessLevel.parse(AccessLevel.STAFF) is AccessLevel.STAFF
        assert AccessLevel.parse("  manager ") is AccessLevel.MANAGER

    def test_item_status_parse_variants(self) -> None:
        assert ItemStatus.parse("checked out") is ItemStatus.CHECKED_OUT
        assert ItemStatus.parse(ItemStatus.AVAILABLE) is ItemStatus.AVAILABLE

    def test_item_status_parse_hyphenated(self) -> None:
        assert ItemStatus.parse("checked-out") is ItemStatus.CHECKED_OUT

    def test_item_condition_parse_whitespace(self) -> None:
        assert ItemCondition.parse("  MINT  ") is ItemCondition.MINT

    def test_item_condition_parse_invalid(self) -> None:
        with pytest.raises(ValueError, match="Unsupported ItemCondition"):
            ItemCondition.parse("nope")

    def test_audit_action_values(self) -> None:
        assert AuditAction.CHECKED_IN.value == "checked_in"


class TestDataclassesAndHelpers:
    def test_custody_record_render_with_notes(self) -> None:
        ts = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        rec = CustodyRecord(
            timestamp=ts,
            item_id="ITM-0001",
            action=AuditAction.CHECKED_OUT,
            actor_name="Pat",
            actor_access_level=AccessLevel.STAFF,
            notes="Handoff",
        )
        out = rec.render()
        assert "checked_out" in out
        assert "Pat (STAFF)" in out
        assert "| Handoff" in out

    def test_custody_record_render_no_notes(self) -> None:
        ts = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        rec = CustodyRecord(
            timestamp=ts,
            item_id="ITM-0001",
            action=AuditAction.CHECKED_IN,
            actor_name="Pat",
            actor_access_level=AccessLevel.STAFF,
        )
        assert "|" not in rec.render().split("Pat (STAFF)")[-1]

    def test_item_snapshot_render_row(self) -> None:
        snap = ItemSnapshot(
            item_id="ITM-0001",
            name="Coin",
            category="artifact",
            monetary_value=Decimal("1234.56"),
            status=ItemStatus.AVAILABLE,
            condition=ItemCondition.GOOD,
            current_holder=None,
        )
        row = snap.render_row()
        assert "ITM-0001" in row
        assert "$1,234.56" in row
        assert "-" in row

    def test_reconciliation_report_balanced(self) -> None:
        r = ReconciliationReport(observed_ids=("a",), missing_ids=(), unexpected_ids=())
        assert r.is_balanced
        text = r.format_report()
        assert "matches expected" in text

    def test_reconciliation_report_discrepancies(self) -> None:
        r = ReconciliationReport(
            observed_ids=("x",),
            missing_ids=("m",),
            unexpected_ids=("u",),
        )
        assert not r.is_balanced
        assert "Missing from count" in r.format_report()
        assert "Unexpected in count" in r.format_report()

    def test_vault_summary_format_lists_statuses(self) -> None:
        s = VaultSummary(
            total_items=1,
            items_by_status={ItemStatus.AVAILABLE: 1},
            total_value_in_vault=Decimal("10.00"),
            total_value_checked_out=Decimal("0.00"),
        )
        report = s.format_report()
        assert "Vault Summary" in report
        assert "available: 1" in report
        assert "$10.00" in report


class TestItemModel:
    def test_item_custody_chain_and_record(self) -> None:
        item = Item(
            item_id="ITM-0001",
            name="X",
            category="doc",
            monetary_value=Decimal("1.00"),
        )
        assert item.custody_chain == ()
        rec = CustodyRecord(
            timestamp=datetime.now(timezone.utc),
            item_id=item.item_id,
            action=AuditAction.CHECKED_IN,
            actor_name="A",
            actor_access_level=AccessLevel.STAFF,
        )
        item.record(rec)
        assert len(item.custody_chain) == 1


class TestVaultAddItem:
    def test_add_item_creates_initial_audit_record(self, vault: Vault) -> None:
        item = vault.add_item(
            "Museum Coin",
            "artifact",
            "250000",
            actor_name="Riley",
            actor_access_level=AccessLevel.MANAGER,
        )
        report = vault.audit_item(item.item_id)
        assert "Audit Report for" in report
        assert "checked_in" in report
        assert "Riley (MANAGER)" in report

    def test_add_item_duplicate_id(self, vault: Vault) -> None:
        vault.add_item("A", "document", "1", item_id="CUSTOM-1")
        with pytest.raises(DuplicateItemError):
            vault.add_item("B", "document", "2", item_id="CUSTOM-1")

    def test_add_item_checked_out_requires_holder(self, vault: Vault) -> None:
        with pytest.raises(ItemStateError, match="holder"):
            vault.add_item(
                "X",
                "document",
                "10",
                status=ItemStatus.CHECKED_OUT,
                current_holder=None,
            )

    def test_add_item_checked_out_with_holder(self, vault: Vault) -> None:
        snap = vault.add_item(
            "X",
            "document",
            "10",
            status=ItemStatus.CHECKED_OUT,
            current_holder="  Quinn  ",
        )
        assert snap.status is ItemStatus.CHECKED_OUT
        assert snap.current_holder == "Quinn"

    def test_add_item_normalizes_category(self, vault: Vault) -> None:
        snap = vault.add_item("Y", "  Fine Art  ", "5")
        assert snap.category == "fine_art"

    def test_add_item_money_types(self, vault: Vault) -> None:
        v1 = vault.add_item("I1", "document", 100)
        v2 = vault.add_item("I2", "document", 12.345)
        assert v1.monetary_value == Decimal("100.00")
        assert v2.monetary_value == Decimal("12.35")

    @pytest.fixture
    def vault(self) -> Vault:
        return Vault()


class TestVaultCheckOutAccess:
    def test_high_value_checkout_requires_manager(self) -> None:
        vault = Vault()
        item = vault.add_item("Ruby Scepter", "artifact", "150000")
        with pytest.raises(AccessDeniedError):
            vault.check_out(
                item.item_id,
                actor_name="Taylor",
                actor_access_level=AccessLevel.SUPERVISOR,
            )
        checked_out = vault.check_out(
            item.item_id,
            actor_name="Morgan",
            actor_access_level=AccessLevel.MANAGER,
        )
        assert checked_out.status is ItemStatus.CHECKED_OUT
        assert checked_out.current_holder == "Morgan"

    def test_classified_requires_director(self) -> None:
        vault = Vault()
        item = vault.add_item("Secret", "classified", "100")
        with pytest.raises(AccessDeniedError):
            vault.check_out(
                item.item_id,
                actor_name="M",
                actor_access_level=AccessLevel.MANAGER,
            )
        out = vault.check_out(
            item.item_id,
            actor_name="D",
            actor_access_level=AccessLevel.DIRECTOR,
        )
        assert out.status is ItemStatus.CHECKED_OUT

    def test_jewelry_requires_supervisor(self) -> None:
        vault = Vault()
        item = vault.add_item("Ring", "jewelry", "1000")
        with pytest.raises(AccessDeniedError):
            vault.check_out(
                item.item_id,
                actor_name="S",
                actor_access_level=AccessLevel.STAFF,
            )
        vault.check_out(item.item_id, actor_name="S", actor_access_level=AccessLevel.SUPERVISOR)

    def test_value_tier_25k_supervisor(self) -> None:
        vault = Vault()
        item = vault.add_item("Thing", "electronics", "25000")
        with pytest.raises(AccessDeniedError):
            vault.check_out(
                item.item_id,
                actor_name="S",
                actor_access_level=AccessLevel.STAFF,
            )
        vault.check_out(item.item_id, actor_name="S", actor_access_level=AccessLevel.SUPERVISOR)

    def test_value_tier_500k_director(self) -> None:
        vault = Vault()
        item = vault.add_item("Mega", "electronics", "500000")
        with pytest.raises(AccessDeniedError):
            vault.check_out(
                item.item_id,
                actor_name="M",
                actor_access_level=AccessLevel.MANAGER,
            )
        vault.check_out(item.item_id, actor_name="D", actor_access_level=AccessLevel.DIRECTOR)


class TestVaultCheckOutStates:
    def test_reserved_cannot_check_out(self) -> None:
        vault = Vault()
        item = vault.add_item(
            "Inspection Packet",
            "document",
            "50",
            status=ItemStatus.RESERVED,
        )
        with pytest.raises(ItemStateError, match="reserved"):
            vault.check_out(
                item.item_id,
                actor_name="Casey",
                actor_access_level=AccessLevel.STAFF,
            )

    def test_already_checked_out(self) -> None:
        vault = Vault()
        item = vault.add_item("A", "document", "10")
        vault.check_out(item.item_id, actor_name="A", actor_access_level=AccessLevel.STAFF)
        with pytest.raises(ItemStateError, match="already checked out"):
            vault.check_out(item.item_id, actor_name="B", actor_access_level=AccessLevel.STAFF)

    def test_retired_cannot_check_out(self) -> None:
        vault = Vault()
        item = vault.add_item("A", "document", "10")
        vault.retire_item(item.item_id, actor_name="M", actor_access_level=AccessLevel.MANAGER)
        with pytest.raises(ItemStateError, match="retired"):
            vault.check_out(item.item_id, actor_name="A", actor_access_level=AccessLevel.MANAGER)

    def test_item_not_found(self) -> None:
        vault = Vault()
        with pytest.raises(ItemNotFoundError):
            vault.check_out("missing", actor_name="A", actor_access_level=AccessLevel.STAFF)


class TestVaultCheckIn:
    def test_check_out_and_check_in_update_summary_totals(self) -> None:
        vault = Vault()
        item = vault.add_item("Server Blade", "electronics", "5000")
        vault.check_out(item.item_id, actor_name="Alex", actor_access_level=AccessLevel.STAFF)
        summary = vault.summary()
        assert summary.total_value_checked_out == Decimal("5000.00")
        assert summary.total_value_in_vault == Decimal("0.00")

        vault.check_in(item.item_id, actor_name="Alex", actor_access_level=AccessLevel.STAFF)
        summary = vault.summary()
        assert summary.total_value_checked_out == Decimal("0.00")
        assert summary.total_value_in_vault == Decimal("5000.00")

    def test_check_in_requires_checked_out(self) -> None:
        vault = Vault()
        item = vault.add_item("A", "document", "1")
        with pytest.raises(ItemStateError, match="not currently checked out"):
            vault.check_in(item.item_id, actor_name="A", actor_access_level=AccessLevel.STAFF)

    def test_check_in_visitor_denied(self) -> None:
        vault = Vault()
        item = vault.add_item("A", "document", "10")
        vault.check_out(item.item_id, actor_name="A", actor_access_level=AccessLevel.STAFF)
        with pytest.raises(AccessDeniedError, match="STAFF"):
            vault.check_in(item.item_id, actor_name="V", actor_access_level=AccessLevel.VISITOR)


class TestVaultUpdateCondition:
    def test_update_condition_success(self) -> None:
        vault = Vault()
        item = vault.add_item("A", "document", "10", condition=ItemCondition.GOOD)
        snap = vault.update_condition(
            item.item_id,
            ItemCondition.MINT,
            actor_name="A",
            actor_access_level=AccessLevel.STAFF,
            notes="Polished",
        )
        assert snap.condition is ItemCondition.MINT
        audit = vault.audit_item(item.item_id)
        assert "condition_changed" in audit

    def test_same_condition_rejected(self) -> None:
        vault = Vault()
        item = vault.add_item("A", "document", "10", condition=ItemCondition.GOOD)
        with pytest.raises(ItemStateError, match="already marked"):
            vault.update_condition(
                item.item_id,
                ItemCondition.GOOD,
                actor_name="A",
                actor_access_level=AccessLevel.STAFF,
            )

    def test_retired_cannot_update_condition(self) -> None:
        vault = Vault()
        item = vault.add_item("A", "document", "10")
        vault.retire_item(item.item_id, actor_name="M", actor_access_level=AccessLevel.MANAGER)
        with pytest.raises(ItemStateError, match="retired"):
            vault.update_condition(
                item.item_id,
                ItemCondition.DAMAGED,
                actor_name="A",
                actor_access_level=AccessLevel.STAFF,
            )

    def test_condition_visitor_denied(self) -> None:
        vault = Vault()
        item = vault.add_item("A", "document", "10")
        with pytest.raises(AccessDeniedError):
            vault.update_condition(
                item.item_id,
                ItemCondition.FAIR,
                actor_name="V",
                actor_access_level=AccessLevel.VISITOR,
            )


class TestVaultRetire:
    def test_retire_success(self) -> None:
        vault = Vault()
        item = vault.add_item("A", "document", "10")
        snap = vault.retire_item(
            item.item_id,
            actor_name="M",
            actor_access_level=AccessLevel.MANAGER,
        )
        assert snap.status is ItemStatus.RETIRED

    def test_retire_checked_out_blocked(self) -> None:
        vault = Vault()
        item = vault.add_item("A", "document", "10")
        vault.check_out(item.item_id, actor_name="A", actor_access_level=AccessLevel.STAFF)
        with pytest.raises(ItemStateError, match="checked in"):
            vault.retire_item(item.item_id, actor_name="M", actor_access_level=AccessLevel.MANAGER)

    def test_retire_already_retired(self) -> None:
        vault = Vault()
        item = vault.add_item("A", "document", "10")
        vault.retire_item(item.item_id, actor_name="M", actor_access_level=AccessLevel.MANAGER)
        with pytest.raises(ItemStateError, match="already retired"):
            vault.retire_item(item.item_id, actor_name="M", actor_access_level=AccessLevel.MANAGER)

    def test_retire_below_manager_denied(self) -> None:
        vault = Vault()
        item = vault.add_item("A", "document", "10")
        with pytest.raises(AccessDeniedError, match="MANAGER"):
            vault.retire_item(
                item.item_id,
                actor_name="S",
                actor_access_level=AccessLevel.SUPERVISOR,
            )


class TestVaultSearch:
    def test_search_filters_by_status_condition_and_value(self) -> None:
        vault = Vault()
        first = vault.add_item("Keycard", "document", "8000", condition=ItemCondition.GOOD)
        vault.add_item("Gold Seal", "artifact", "95000", condition=ItemCondition.MINT)
        vault.check_out(first.item_id, actor_name="Jordan", actor_access_level=AccessLevel.STAFF)
        results = vault.search(
            status=ItemStatus.CHECKED_OUT,
            condition=ItemCondition.GOOD,
            max_value="10000",
        )
        assert [i.item_id for i in results] == [first.item_id]

    def test_search_min_max_category(self) -> None:
        vault = Vault()
        a = vault.add_item("Low", "document", "5")
        vault.add_item("High", "document", "500")
        ids = [i.item_id for i in vault.search(category="document", min_value="1", max_value="100")]
        assert ids == [a.item_id]

    def test_search_empty_returns_all_sorted(self) -> None:
        vault = Vault()
        vault.add_item("B", "document", "1")
        vault.add_item("A", "document", "1")
        ids = [i.item_id for i in vault.search()]
        assert ids == sorted(ids)


class TestVaultReconcile:
    def test_reconcile_flags_missing_and_unexpected(self) -> None:
        vault = Vault()
        first = vault.add_item("Archive Box", "document", "900")
        second = vault.add_item("Badge Printer", "electronics", "1800")
        vault.check_out(second.item_id, actor_name="Jamie", actor_access_level=AccessLevel.STAFF)
        report = vault.reconcile([second.item_id, "UNKNOWN-1"])
        assert report.missing_ids == (first.item_id,)
        assert report.unexpected_ids == (second.item_id, "UNKNOWN-1")

    def test_reconcile_strips_and_dedupes(self) -> None:
        vault = Vault()
        i = vault.add_item("A", "document", "1")
        r = vault.reconcile([f"  {i.item_id}  ", i.item_id, "  ", ""])
        assert r.observed_ids == (i.item_id,)


class TestSeedDemoVault:
    def test_seed_demo_vault_has_expected_items(self) -> None:
        v = seed_demo_vault()
        ids = {snap.item_id for snap in v.search()}
        assert len(ids) == 3
        names = {snap.name for snap in v.search()}
        assert "Bronze Ledger" in names
        assert "Aurora Necklace" in names
        assert "Prototype Keycard" in names
        reserved = next(s for s in v.search() if s.name == "Prototype Keycard")
        assert reserved.status is ItemStatus.RESERVED
