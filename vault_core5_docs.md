# Architecture Decision Record
## App 17 — Secure Inventory Manager
**Vault OS Group | Document 1 of 5**
**Status: Accepted**

---

## Context

Vault OS App 17 is the Secure Inventory Manager for the larger Vault OS roadmap. The app simulates a vault that stores valuable physical items, controls check-out and check-in workflows, enforces access rules, and preserves a custody chain for every item. The core learning goal is OOP and state management: the inventory must not be treated as a loose list of dictionaries that any caller can mutate. Instead, the vault object owns the item collection, validates every state transition, and writes an audit record whenever the state changes.

The repository is implemented as an importable `vault` package rather than a single flat script. Runtime code lives in `vault/domain.py`, `vault/cli.py`, `vault/__main__.py`, and `vault/__init__.py`. Tests live under `tests/`, and packaging metadata is declared in `pyproject.toml`.

The major design constraint was to keep the project appropriate for a one-day roadmap app while still making the domain model feel real enough to support audits, custody tracking, reconciliation, and access-sensitive operations.

---

## Decisions

### Decision 1 — Package structure over a single-file CLI

**Chosen:** Use a small package layout:

- `vault/domain.py` for inventory objects, value objects, enums, exceptions, and business rules
- `vault/cli.py` for interactive prompts and `argparse`
- `vault/__main__.py` for `python -m vault`
- `vault/__init__.py` for public package exports

**Rejected:** A single `main.py` containing domain classes, CLI input handling, and test helpers.

**Reason:** The app is no longer just a basic CLI exercise. It has enough domain rules — custody records, access tiers, money normalization, reconciliation, and summaries — that combining UI and domain logic would make the code difficult to test. The package structure keeps the public domain model usable by both the CLI and unit tests while still staying small enough for the learning stage.

---

### Decision 2 — `Vault` as the only mutation boundary

**Chosen:** The `Vault` class owns the item dictionary and exposes controlled methods: `add_item()`, `check_out()`, `check_in()`, `update_condition()`, `retire_item()`, `audit_item()`, `search()`, `reconcile()`, and `summary()`.

**Rejected:** Exposing a public list or dictionary of `Item` objects for callers to modify directly.

**Reason:** The entire design depends on custody integrity. If external code could directly set `item.status = "checked_out"` or change `item.condition`, the audit chain would no longer be trustworthy. By forcing state changes through `Vault`, the system can validate the transition, enforce access rules, update holder state, and append a `CustodyRecord` every time.

---

### Decision 3 — Frozen audit records and immutable read models

**Chosen:** `CustodyRecord`, `ItemSnapshot`, `ReconciliationReport`, and `VaultSummary` are dataclasses intended for stable reporting. `CustodyRecord` is frozen, and snapshots are returned to callers instead of raw internal `Item` objects.

**Rejected:** Returning the mutable `Item` object from every vault operation as the main read model.

**Reason:** The vault needs mutable internal state, but callers should not receive an easy path to mutate that state outside the approved methods. Returning snapshots gives the CLI and tests enough information to display the result of an operation without handing out the internal object itself. Frozen custody records also make the audit trail more credible: once an audit entry exists, it is not supposed to be edited.

---

### Decision 4 — Enums for status, condition, access, and audit actions

**Chosen:** Use `AccessLevel`, `ItemStatus`, `ItemCondition`, and `AuditAction` enums. Access levels use `IntEnum` so levels can be compared with standard ordering. Text enums include parsing helpers that accept reasonable user-facing variants such as `"checked out"` and `"checked-out"`.

**Rejected:** Plain strings for statuses and conditions, and ad hoc integer constants for access levels.

**Reason:** Plain strings make typos easy and validation scattered. Enums create a compact vocabulary for the domain and make tests more precise. `IntEnum` is especially useful for access decisions because checkout rules can compare actor clearance against required clearance directly.

---

### Decision 5 — `Decimal` for monetary values

**Chosen:** Normalize all monetary values to `Decimal("0.01")` using `ROUND_HALF_UP`.

**Rejected:** Floating-point values for inventory value calculations.

**Reason:** The vault calculates total value in vault and total value checked out. Using floats for money creates avoidable rounding artifacts. `Decimal` is a standard-library type and fits the learning goal without adding dependencies.

---

### Decision 6 — Category and value based access policy

**Chosen:** Access requirements are computed from two sources:

1. Category-specific rules in `_CATEGORY_ACCESS_RULES`
2. Value tiers based on `monetary_value`

The final required access level is the maximum of category requirement and value requirement.

**Rejected:** Hardcoding one global minimum level for all checkouts, or storing a custom required level on every item.

**Reason:** A single global rule would be too weak for a vault simulator. Per-item policy would be more flexible but would also add another configuration surface. The chosen design is a middle ground: valuable or sensitive categories automatically require stronger clearance while ordinary inventory still only requires `STAFF`.

---

### Decision 7 — Reconciliation compares physical count against present inventory

**Chosen:** `reconcile(observed_item_ids)` treats all non-checked-out items as expected to be physically present. Checked-out items are not counted as missing from the vault, because they have a known holder and are intentionally outside the vault.

**Rejected:** Treating every registered item as expected in the physical count, including checked-out items.

**Reason:** Reconciliation simulates a physical inventory count. If an item is legitimately checked out, it should not appear in the vault count. However, if a checked-out ID appears in the observed physical list, it is unexpected because the system believes it is outside the vault.

---

### Decision 8 — Interactive menu with `--demo` instead of a full subcommand CLI

**Chosen:** The CLI launches an interactive menu. `argparse` only handles the `--demo` startup flag.

**Rejected:** A full command tree such as `vault add`, `vault checkout`, `vault audit`, and `vault reconcile`.

**Reason:** The roadmap app is focused on OOP and state transitions, not command-line parser design. A menu-driven CLI makes it easy to exercise the full stateful flow in one process: add an item, check it out, check it in, audit it, and inspect summary totals. `--demo` provides a small preloaded inventory for fast manual testing.

---

## Consequences

**Positive:**

- Domain rules are testable without running the CLI.
- The vault remains the trusted state owner.
- Every meaningful state change creates a custody record.
- `Decimal` keeps value summaries stable and appropriate for money.
- Snapshots reduce accidental mutation from the CLI layer.
- `python -m vault`, the `vault` console script, and direct imports are all supported.
- Tests can cover parsing, checkout access tiers, state transitions, reconciliation, and CLI flows separately.

**Negative / Trade-offs:**

- State is in memory only. Closing the CLI loses all items and custody history unless another layer calls the restore hooks.
- The interactive CLI is not automation-friendly compared to subcommands.
- `Item` itself is still mutable inside the domain layer, so full immutability is not attempted.
- The access policy is hardcoded in `_CATEGORY_ACCESS_RULES` and value thresholds.
- There is no separate actor registry, so actor names and access levels are trusted input.
- `RESERVED` exists as a status, but there is no first-class `reserve_item()` or `unreserve_item()` workflow.
- Search filters are free-text prompts; invalid filter values can raise a parsing error rather than being guided through enum prompts.

---

## Alternatives Not Explored

- **SQLite or JSON persistence:** Rejected for scope. The persistence restore hooks suggest future integration, but the Day 17 project is an in-memory simulator.
- **Third-party CLI framework:** Rejected because `argparse` and `input()` are sufficient for the learning target.
- **Policy objects:** A separate checkout policy class would make rules more extensible, but the current rule table is easier to read at this stage.
- **Dataclass-only immutable item model:** Rejected because operations such as check-out and check-in require state changes, and replacing whole items would increase complexity.

---

*Constitution reference: Article 1 (Python fundamentals and architectural thinking), Article 3 (scope discipline), Article 4 (engineering quality), Article 5 (trade-offs), and Article 6 (verification).*

-e 

---


# Technical Design Document
## App 17 — Secure Inventory Manager
**Vault OS Group | Document 2 of 5**

---

## Overview

Secure Inventory Manager is a package-based Python CLI application for managing valuable vault inventory. The app models items, access levels, custody records, state transitions, audit reports, search filters, reconciliation reports, and inventory summaries.

**Package:** `vault`  
**Primary domain module:** `vault/domain.py`  
**CLI module:** `vault/cli.py`  
**Module entry point:** `vault/__main__.py`  
**Console script:** `vault`  
**Runtime dependencies:** Python standard library only  
**Development dependency:** `pytest>=8`

The central object is `Vault`. It stores internal `Item` objects in a private dictionary, validates every operation, mutates item state, and appends immutable custody records.

---

## Purpose & Scope

This document covers the internal implementation of the Day 17 inventory subsystem: how inventory data is represented, how item state changes are controlled, how audit records are produced, how access rules are enforced, and how the CLI drives the domain layer.

This document does not cover the other Vault OS roadmap apps except as context. It also does not describe a persistent database, external API, user authentication service, or real cryptographic vault.

---

## System Context

```
User
 │
 ▼
CLI menu / argparse
 │
 ▼
VaultCLI
 │
 ▼
Vault domain object
 │
 ├── Item objects
 ├── CustodyRecord chains
 ├── Access policy rules
 ├── Search / reconciliation / summary reports
 │
 ▼
stdout reports and in-memory state
```

The application runs as a local process. It does not call the network, write files, or modify OS-level state. All inventory state exists in memory for the lifetime of the process.

---

## Component Breakdown

### `vault/domain.py`

#### Exceptions

| Class | Responsibility |
|---|---|
| `VaultError` | Base exception for expected vault operation failures |
| `DuplicateItemError` | Raised when a caller attempts to add an item with an existing ID |
| `ItemNotFoundError` | Raised when an item ID cannot be found |
| `ItemStateError` | Raised when an item status blocks a requested transition |
| `AccessDeniedError` | Raised when actor clearance is below the required level |

#### Type aliases and helpers

| Name | Responsibility |
|---|---|
| `MoneyLike` | Acceptable inputs for monetary values: `Decimal`, `int`, `float`, `str` |
| `_to_money()` | Converts money-like input to a two-decimal `Decimal` |
| `_format_money()` | Produces display strings such as `$1,234.56` |
| `_normalize_category()` | Converts category text to normalized lowercase underscore form |

#### Enums

| Enum | Responsibility |
|---|---|
| `AccessLevel` | Ordered clearance hierarchy: `VISITOR`, `STAFF`, `SUPERVISOR`, `MANAGER`, `DIRECTOR` |
| `ItemStatus` | Item lifecycle state: `available`, `checked_out`, `reserved`, `retired` |
| `ItemCondition` | Item condition state: `mint`, `good`, `fair`, `damaged` |
| `AuditAction` | Audit event vocabulary: `checked_in`, `checked_out`, `condition_changed`, `retired` |

#### Dataclasses

| Class | Responsibility |
|---|---|
| `CustodyRecord` | Immutable audit entry for a single item event |
| `ItemSnapshot` | Immutable read model returned to callers and rendered in tables |
| `ReconciliationReport` | Result object for physical count comparison |
| `VaultSummary` | Aggregated inventory totals by status and value |
| `Item` | Internal mutable inventory entity with a custody chain |

#### `Vault`

The orchestrator and mutation boundary. It owns:

```python
_items: dict[str, Item]
_sequence: int
```

It exposes operation methods for adding items, checking out, checking in, updating condition, retiring, auditing, searching, reconciling, and summarizing.

---

### `vault/cli.py`

#### `VaultCLI`

Interactive menu wrapper around a `Vault` instance.

Responsibilities:

- render the menu
- collect user input
- parse money and enums
- call vault methods
- catch expected `VaultError` failures
- render item rows, audit reports, reconciliation reports, and summaries

#### `build_parser()`

Creates the `argparse.ArgumentParser` with one flag:

```bash
--demo
```

#### `main(argv=None)`

Parses CLI arguments, creates either an empty vault or a seeded demo vault, and starts `VaultCLI.run()`.

---

### `vault/__main__.py`

Allows the app to run with:

```bash
python -m vault
python -m vault --demo
```

It calls `vault.cli.main()` and passes the result to `SystemExit`.

---

### `vault/__init__.py`

Re-exports the public domain classes and exceptions so callers can import from `vault` instead of reaching into `vault.domain`.

---

## Module Dependency Graph

```
vault/__main__.py
    imports vault.cli.main

vault/cli.py
    imports argparse
    imports Decimal, InvalidOperation
    imports vault.domain:
        AccessLevel
        ItemCondition
        ItemStatus
        Vault
        VaultError
        seed_demo_vault

vault/__init__.py
    imports selected names from vault.domain

vault/domain.py
    imports collections.Counter
    imports dataclasses
    imports datetime
    imports decimal
    imports enum
    imports typing.Iterable

tests/test_domain.py
    imports vault.domain

tests/test_cli.py
    imports vault.cli and vault.domain
    imports tests.helpers.scripted_input
```

`domain.py` does not import the CLI. This is the correct direction: UI depends on the domain, not the other way around.

---

## Core Workflows

### Add Item

```
Vault.add_item(...)
 │
 ├── parse status, condition, access level
 ├── normalize category
 ├── choose provided item_id or generate ITM-####
 ├── reject duplicate IDs
 ├── reject checked_out status without current_holder
 ├── construct Item
 ├── store Item in _items
 ├── append initial CHECKED_IN custody record
 └── return ItemSnapshot
```

The initial audit record establishes that the item entered the vault inventory.

---

### Check Out

```
Vault.check_out(item_id, actor_name, actor_access_level, notes)
 │
 ├── require item exists
 ├── reject already checked_out
 ├── reject reserved
 ├── reject retired
 ├── parse actor access level
 ├── compute required access:
 │     ├── category rule
 │     └── value tier rule
 ├── reject insufficient access
 ├── set status = CHECKED_OUT
 ├── set current_holder = actor_name
 ├── append CHECKED_OUT custody record
 └── return ItemSnapshot
```

This is the most important business path because it combines state validation, access policy, mutation, and audit logging.

---

### Check In

```
Vault.check_in(...)
 │
 ├── require item exists
 ├── require status == CHECKED_OUT
 ├── require actor access >= STAFF
 ├── set status = AVAILABLE
 ├── clear current_holder
 ├── append CHECKED_IN custody record
 └── return ItemSnapshot
```

Check-in does not re-run the original checkout policy. It only requires staff-level authority because returning an item is less sensitive than removing it.

---

### Update Condition

```
Vault.update_condition(...)
 │
 ├── require item exists
 ├── reject retired item
 ├── require actor access >= STAFF
 ├── parse new condition
 ├── reject no-op condition update
 ├── set condition
 ├── append CONDITION_CHANGED custody record
 └── return ItemSnapshot
```

Condition changes are auditable because they affect inventory value and trustworthiness.

---

### Retire Item

```
Vault.retire_item(...)
 │
 ├── require item exists
 ├── reject already retired
 ├── reject checked_out item
 ├── require actor access >= MANAGER
 ├── set status = RETIRED
 ├── clear current_holder
 ├── append RETIRED custody record
 └── return ItemSnapshot
```

Retirement is irreversible in the current interface.

---

### Audit Item

```
Vault.audit_item(item_id)
 │
 ├── require item exists
 ├── render current item metadata
 ├── render each custody record in order
 └── return multiline string report
```

The audit report is a string because the CLI needs directly printable output.

---

### Search

```
Vault.search(filters...)
 │
 ├── normalize category if provided
 ├── parse status if provided
 ├── parse condition if provided
 ├── normalize min/max money if provided
 ├── iterate internal items
 ├── apply filters
 ├── convert matching items to snapshots
 └── return snapshots sorted by item_id
```

Search is read-only and returns snapshots.

---

### Reconcile

```
Vault.reconcile(observed_item_ids)
 │
 ├── strip blanks
 ├── dedupe observed IDs
 ├── sort observed IDs
 ├── expected_present = all items not checked_out
 ├── missing = expected_present - observed
 ├── unexpected = observed - expected_present
 └── return ReconciliationReport
```

Checked-out items are excluded from expected physical inventory.

---

### Summary

```
Vault.summary()
 │
 ├── count items by ItemStatus
 ├── sum values for items not checked_out
 ├── sum values for checked_out items
 └── return VaultSummary
```

The summary separates value still in the vault from value currently in custody outside the vault.

---

## Significant Data Structures

### `Vault._items`

```python
dict[str, Item]
```

Maps item IDs to internal item objects.

Purpose:

- O(1) lookup by ID
- central state store
- prevents callers from owning inventory data directly

---

### `Vault._sequence`

```python
int
```

High-water counter for generating IDs like:

```python
ITM-0001
ITM-0002
```

---

### `Item`

```python
@dataclass(slots=True)
class Item:
    item_id: str
    name: str
    category: str
    monetary_value: Decimal
    status: ItemStatus
    condition: ItemCondition
    current_holder: str | None
    _custody_chain: list[CustodyRecord]
```

`Item` is internal and mutable. Public reads should happen through `ItemSnapshot`.

---

### `CustodyRecord`

```python
@dataclass(frozen=True, slots=True)
class CustodyRecord:
    timestamp: datetime
    item_id: str
    action: AuditAction
    actor_name: str
    actor_access_level: AccessLevel
    notes: str = ""
```

Represents one immutable custody event.

---

### `ItemSnapshot`

```python
@dataclass(frozen=True, slots=True)
class ItemSnapshot:
    item_id: str
    name: str
    category: str
    monetary_value: Decimal
    status: ItemStatus
    condition: ItemCondition
    current_holder: str | None
```

Used for operation results, search results, and table rendering.

---

### `ReconciliationReport`

```python
observed_ids: tuple[str, ...]
missing_ids: tuple[str, ...]
unexpected_ids: tuple[str, ...]
```

Used to compare physical count against system state.

---

### `VaultSummary`

```python
total_items: int
items_by_status: dict[ItemStatus, int]
total_value_in_vault: Decimal
total_value_checked_out: Decimal
```

Used for management-level reporting.

---

## State Management

All state is in memory:

- inventory items live in `Vault._items`
- ID generation lives in `Vault._sequence`
- custody records live inside each `Item`
- CLI state is limited to the current `VaultCLI.vault` reference

There is no automatic file persistence, database, or environment-backed configuration.

The domain includes integration-oriented restore helpers:

- `Vault.apply_restored_inventory()`
- `Item.apply_restored_custody_chain()`
- `Vault.iter_items_sorted_by_id()`
- `Vault.persisted_issue_sequence`

These are not exposed through the CLI but signal a future persistence boundary.

---

## Error Handling Strategy

Expected domain failures use `VaultError` subclasses:

| Error | Trigger |
|---|---|
| `DuplicateItemError` | duplicate item ID |
| `ItemNotFoundError` | missing item ID |
| `ItemStateError` | invalid lifecycle transition |
| `AccessDeniedError` | insufficient actor access |

`VaultCLI.run()` catches `VaultError` and prints:

```text
Operation blocked: <message>
```

Prompt helpers handle invalid money and enum input by retrying.

Known gap: search filters are collected as raw text and passed into `Vault.search()`. Invalid status, condition, or money search filters can raise non-`VaultError` parsing exceptions instead of being handled with the same friendly prompt loop.

---

## External Dependencies

### Runtime

No third-party runtime packages. The app uses standard library modules:

- `argparse`
- `collections`
- `dataclasses`
- `datetime`
- `decimal`
- `enum`
- `typing`

### Development

- `pytest>=8`

### Packaging

- `setuptools>=68`
- package name: `vault-os`
- import package: `vault`
- console script: `vault = vault.cli:main`

---

## Concurrency Model

The app is synchronous and single-process.

There are no threads, async tasks, locks, or background workers. This is appropriate because all state is in memory and all operations are initiated by a single interactive CLI loop.

If the app later became a service or multi-user tool, the current in-memory state design would need a persistence layer and concurrency controls.

---

## Known Limitations

- Inventory disappears when the process exits.
- No file import/export command exists.
- No actor database exists; actor name and access level are trusted.
- No method exists to reserve or unreserve an item even though `RESERVED` is a valid status.
- Access policy is hardcoded in `Vault._CATEGORY_ACCESS_RULES` and value thresholds.
- Audit timestamps always use current UTC time; tests do not inject a clock for deterministic domain timestamps.
- CLI is interactive and not ideal for automation.
- Invalid search filter values are not as gracefully handled as enum prompts in other workflows.

---

## Design Patterns Used

### Facade / Service Object

`Vault` acts as a facade over inventory state, access rules, and audit logging. Callers do not need to know how custody records are stored.

### Value Object / DTO

`ItemSnapshot`, `ReconciliationReport`, and `VaultSummary` are read models designed for safe transfer and display.

### Policy Table

`_CATEGORY_ACCESS_RULES` is a simple policy table mapping categories to minimum clearance.

### Encapsulation

Items are stored privately and returned as snapshots. State transitions are performed through domain methods.

### Factory

`seed_demo_vault()` builds a preloaded vault used by `--demo`.

---

*Constitution reference: Article 1 and Article 4. The package structure, value objects, and mutation boundary demonstrate architectural thinking proportional to the app size.*

-e 

---


# Interface Design Specification
## App 17 — Secure Inventory Manager
**Vault OS Group | Document 3 of 5**

---

## Invocation Syntax

### Console script

```bash
vault [--demo]
```

### Module execution

```bash
python -m vault [--demo]
```

### Development run from repo root

```bash
python -m vault --demo
```

---

## CLI Argument Reference

| Name | Type | Required | Default | Accepted Values | Description |
|---|---:|---:|---|---|---|
| `--demo` | bool flag | No | `False` | present / absent | Starts the CLI with a preloaded demo inventory |
| `-h`, `--help` | bool flag | No | — | present / absent | Shows argparse help and exits |

There are no file path arguments, config flags, environment flags, or subcommands.

---

## Interactive Menu Contract

When the CLI starts, it prints the title and menu:

```text
Vault OS - Secure Inventory Manager
Every action is routed through the vault and captured in the audit chain.

1. Add item
2. Check out item
3. Check in item
4. Update condition
5. Retire item
6. Audit item
7. Search inventory
8. Run reconciliation
9. View summary
10. List all items
0. Exit
```

The menu accepts both numeric choices and selected text aliases:

| Menu Choice | Alias Examples | Operation |
|---|---|---|
| `1` | `add` | Add item |
| `2` | `checkout`, `check_out` | Check out item |
| `3` | `checkin`, `check_in` | Check in item |
| `4` | `condition`, `update_condition` | Update condition |
| `5` | `retire` | Retire item |
| `6` | `audit` | Audit item |
| `7` | `search` | Search inventory |
| `8` | `reconcile` | Run reconciliation |
| `9` | `summary` | View summary |
| `10` | `list` | List all items |
| `0` | `q`, `quit`, `exit` | Exit |

---

## Domain API

### `Vault.add_item(...) -> ItemSnapshot`

```python
add_item(
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
) -> ItemSnapshot
```

Creates an item, adds it to the vault, appends an initial custody record, and returns a snapshot.

---

### `Vault.check_out(...) -> ItemSnapshot`

```python
check_out(
    item_id: str,
    *,
    actor_name: str,
    actor_access_level: AccessLevel | str,
    notes: str = "",
) -> ItemSnapshot
```

Checks an available item out to the actor after validating status and access level.

---

### `Vault.check_in(...) -> ItemSnapshot`

```python
check_in(
    item_id: str,
    *,
    actor_name: str,
    actor_access_level: AccessLevel | str,
    notes: str = "",
) -> ItemSnapshot
```

Checks a currently checked-out item back into the vault.

---

### `Vault.update_condition(...) -> ItemSnapshot`

```python
update_condition(
    item_id: str,
    new_condition: ItemCondition | str,
    *,
    actor_name: str,
    actor_access_level: AccessLevel | str,
    notes: str = "",
) -> ItemSnapshot
```

Changes an item's condition and appends a condition-change custody record.

---

### `Vault.retire_item(...) -> ItemSnapshot`

```python
retire_item(
    item_id: str,
    *,
    actor_name: str,
    actor_access_level: AccessLevel | str,
    notes: str = "",
) -> ItemSnapshot
```

Marks an item as retired. Checked-out items must be checked in before retirement.

---

### `Vault.audit_item(item_id: str) -> str`

Returns a multiline audit report for the item.

---

### `Vault.search(...) -> list[ItemSnapshot]`

```python
search(
    *,
    category: str | None = None,
    status: ItemStatus | str | None = None,
    condition: ItemCondition | str | None = None,
    min_value: MoneyLike | None = None,
    max_value: MoneyLike | None = None,
) -> list[ItemSnapshot]
```

Returns snapshots matching the provided filters, sorted by item ID.

---

### `Vault.reconcile(observed_item_ids: Iterable[str]) -> ReconciliationReport`

Compares a physical count against expected present inventory.

---

### `Vault.summary() -> VaultSummary`

Returns aggregate item counts and value totals.

---

## Accepted Enum Values

### `AccessLevel`

| Name | Rank |
|---|---:|
| `VISITOR` | 1 |
| `STAFF` | 2 |
| `SUPERVISOR` | 3 |
| `MANAGER` | 4 |
| `DIRECTOR` | 5 |

### `ItemStatus`

| Name | Value |
|---|---|
| `AVAILABLE` | `available` |
| `CHECKED_OUT` | `checked_out` |
| `RESERVED` | `reserved` |
| `RETIRED` | `retired` |

Text parsing accepts lowercase, spaces, and hyphens for text enums. Examples:

```text
checked_out
checked out
checked-out
```

### `ItemCondition`

| Name | Value |
|---|---|
| `MINT` | `mint` |
| `GOOD` | `good` |
| `FAIR` | `fair` |
| `DAMAGED` | `damaged` |

### `AuditAction`

| Name | Value |
|---|---|
| `CHECKED_IN` | `checked_in` |
| `CHECKED_OUT` | `checked_out` |
| `CONDITION_CHANGED` | `condition_changed` |
| `RETIRED` | `retired` |

---

## Input Contract

### Item names

- Entered interactively as strings.
- Blank values are rejected by the CLI prompt.
- Domain layer stores `name.strip()`.

### Categories

- Entered as strings.
- Normalized by lowercasing and replacing spaces with underscores.
- Example: `"Fine Art"` becomes `"fine_art"`.

### Monetary values

Accepted in domain:

```python
Decimal | int | float | str
```

CLI accepts values such as:

```text
1200
1200.00
$1,200.50
```

All values are normalized to two-decimal `Decimal`.

### Actor names

- Required for checkout, check-in, condition update, and retirement.
- Stored after `strip()` in custody records and current-holder fields.

### Access levels

- CLI prompts enforce enum values for workflows except search filters.
- Domain accepts `AccessLevel` instances or strings parsable by `AccessLevel.parse()`.

### Reconciliation observed IDs

- Entered as comma-separated text.
- Blank values are ignored.
- Duplicate IDs are deduplicated.
- Final report sorts IDs.

---

## Output Contract

### Item table output

List and search results render as a fixed-width table:

```text
ID         Name                   Category              Value Status       Condition Holder
-----------------------------------------------------------------------------------------------
ITM-0001   Bronze Ledger          document          $1,200.00 available    good     -
```

### Audit output

`audit_item()` returns a report shaped like:

```text
Audit Report for ITM-0001 - Bronze Ledger
Category: document
Value: $1,200.00
Status: available
Condition: good
Current holder: none
Custody chain:
  1. 2026-05-08T12:00:00+00:00 | checked_in | SYSTEM (MANAGER) | Item registered in vault.
```

### Reconciliation output

Balanced:

```text
Reconciliation Report
Observed IDs: ITM-0001, ITM-0002
Result: inventory matches expected physical count.
```

Discrepancy:

```text
Reconciliation Report
Observed IDs: ITM-0002, UNKNOWN-1
Missing from count: ITM-0001
Unexpected in count: ITM-0002, UNKNOWN-1
```

### Summary output

```text
Vault Summary
Total items: 3
Items by status:
  - available: 2
  - checked_out: 0
  - reserved: 1
  - retired: 0
Total value in vault: $103,700.00
Total value checked out: $0.00
```

---

## Exit Code Reference

| Exit Code | Condition |
|---:|---|
| `0` | Normal menu exit using `0`, `q`, `quit`, or `exit` |
| `0` | Successful `python -m vault --demo` session after user exits |
| `2` | `argparse` error, such as an unknown startup flag |
| `1` | Unhandled Python exception outside the `VaultError` catch path |

The CLI catches expected domain errors (`VaultError`) and continues running. It does not convert every possible parsing error into a controlled exit code.

---

## Error Output Behavior

Expected operation failures are printed to stdout in this shape:

```text
Operation blocked: <reason>
```

Examples:

```text
Operation blocked: ITM-0001 requires MANAGER access to check out.
Operation blocked: Item ITM-0001 is reserved and cannot be checked out.
Operation blocked: Item missing was not found.
```

The app does not use structured JSON error output. It does not intentionally write domain errors to stderr.

`argparse` help and parser errors follow the standard `argparse` behavior.

---

## Environment Variables

The application does not read environment variables.

---

## Configuration Files

The application does not read configuration files.

---

## Side Effects

Runtime side effects:

- prints to stdout
- reads from stdin through `input()`
- mutates in-memory vault state
- appends in-memory custody records

It does not:

- write inventory files
- write logs
- call external services
- open network connections
- change OS state

---

## Usage Examples

### Basic demo launch

```bash
python -m vault --demo
```

Then select:

```text
9
0
```

Expected result: a vault summary prints, then the app exits.

---

### Add an item

```text
1
Item name: Museum Coin
Category: artifact
Monetary value: 250000
Condition (MINT, GOOD, FAIR, DAMAGED) [GOOD]: MINT
Initial status (AVAILABLE, CHECKED_OUT, RESERVED, RETIRED) [AVAILABLE]:
Operator name [SYSTEM]: Riley
Operator access level (VISITOR, STAFF, SUPERVISOR, MANAGER, DIRECTOR) [MANAGER]: MANAGER
```

Expected result:

```text
Added ITM-0001: Museum Coin (available)
```

---

### Check out an item

```text
2
Item ID: ITM-0001
Actor name: Morgan
Actor access level (VISITOR, STAFF, SUPERVISOR, MANAGER, DIRECTOR): MANAGER
Notes:
```

Expected result:

```text
ITM-0001 checked out to Morgan.
```

---

### Intentional failure — insufficient access

Attempt to check out a high-value or restricted-category item with low access:

```text
2
Item ID: ITM-0001
Actor name: Taylor
Actor access level (VISITOR, STAFF, SUPERVISOR, MANAGER, DIRECTOR): STAFF
Notes:
```

Possible result:

```text
Operation blocked: ITM-0001 requires MANAGER access to check out.
```

---

### Audit an item

```text
6
Item ID: ITM-0001
```

Expected result: multiline report showing metadata and custody chain.

---

### Reconcile physical count

```text
8
Observed item IDs (comma separated): ITM-0001, ITM-0003, UNKNOWN-1
```

Expected result: reconciliation report with missing and unexpected IDs.

---

*Constitution reference: Article 6. This interface contract supports repeatable manual checks and maps to the automated tests.*

-e 

---


# Runbook
## App 17 — Secure Inventory Manager
**Vault OS Group | Document 4 of 5**

---

## Requirements

- Python 3.11 or newer
- Standard library runtime only
- `pytest>=8` for development tests
- A terminal capable of interactive stdin/stdout

---

## Installation Procedure

### From a clean clone

```bash
git clone https://github.com/PrincetonAfeez/Vault
cd Vault
python -m venv .venv
```

Activate the virtual environment:

```bash
# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

Install with development dependencies:

```bash
pip install -r requirements.txt
```

This installs the project in editable mode with the `[dev]` extra.

### Production-style editable install

```bash
pip install -e .
```

This installs the app and console script without pytest.

---

## Running the App

### Demo mode

```bash
python -m vault --demo
```

or, after installation:

```bash
vault --demo
```

Demo mode preloads three items:

- Bronze Ledger
- Aurora Necklace
- Prototype Keycard

### Empty vault mode

```bash
python -m vault
```

or:

```bash
vault
```

This starts with no inventory.

---

## Running Tests

From the repository root:

```bash
pytest
```

Expected result: all tests pass.

Useful narrower runs:

```bash
pytest tests/test_domain.py -v
pytest tests/test_cli.py -v
pytest -k checkout -v
pytest -k reconcile -v
```

The repository configures pytest to discover `tests/test_*.py` with the project root on `pythonpath`.

---

## Standard Operating Procedures

### 1. Verify the app starts

```bash
python -m vault --demo
```

Expected:

```text
Vault OS - Secure Inventory Manager
Every action is routed through the vault and captured in the audit chain.
```

Select `0` to exit.

---

### 2. Add a new item

Menu path:

```text
1. Add item
```

Required information:

- item name
- category
- monetary value
- condition
- initial status
- operator name
- operator access level

Expected success message:

```text
Added ITM-0001: <name> (<status>)
```

---

### 3. Check out an item

Menu path:

```text
2. Check out item
```

Required information:

- item ID
- actor name
- actor access level
- optional notes

Expected success message:

```text
ITM-0001 checked out to Morgan.
```

If the actor has insufficient access, the operation is blocked.

---

### 4. Check in an item

Menu path:

```text
3. Check in item
```

Required information:

- item ID
- actor name
- actor access level
- optional notes

Expected success message:

```text
ITM-0001 checked back into the vault.
```

The item must currently be checked out.

---

### 5. Update condition

Menu path:

```text
4. Update condition
```

Required information:

- item ID
- new condition
- actor name
- actor access level
- optional notes

Expected success message:

```text
ITM-0001 condition updated to fair.
```

---

### 6. Retire item

Menu path:

```text
5. Retire item
```

Required information:

- item ID
- actor name
- actor access level
- optional notes

Expected success message:

```text
ITM-0001 retired from service.
```

The item must not be checked out. Actor access must be at least `MANAGER`.

---

### 7. Audit item

Menu path:

```text
6. Audit item
```

Expected output:

- item metadata
- current holder
- full custody chain
- numbered custody records

---

### 8. Search inventory

Menu path:

```text
7. Search inventory
```

Supported filters:

- category
- status
- condition
- minimum value
- maximum value

Blank filters are ignored.

---

### 9. Run reconciliation

Menu path:

```text
8. Run reconciliation
```

Input observed item IDs as comma-separated text:

```text
ITM-0001, ITM-0002, UNKNOWN-1
```

Expected output:

- observed IDs
- missing IDs
- unexpected IDs
- balanced result if no discrepancies

---

### 10. View summary

Menu path:

```text
9. View summary
```

Expected output:

- total items
- item count by status
- total value in vault
- total value checked out

---

## Health Checks

### Startup check

```bash
python -m vault --demo
```

Select `10` to list all demo items, then `0` to exit.

Healthy result: a table with item IDs, names, categories, values, statuses, conditions, and holders.

### Domain smoke check

```bash
pytest tests/test_domain.py -q
```

Healthy result: domain tests pass.

### CLI smoke check

```bash
pytest tests/test_cli.py -q
```

Healthy result: CLI prompt and menu tests pass.

### Packaging check

```bash
pip install -r requirements.txt
vault --demo
```

Healthy result: the console script launches.

---

## Expected Output Samples

### List all items

```text
ID         Name                   Category              Value Status       Condition Holder
-----------------------------------------------------------------------------------------------
ITM-0001   Bronze Ledger          document          $1,200.00 available    good     -
ITM-0002   Aurora Necklace        jewelry          $87,500.00 available    mint     -
ITM-0003   Prototype Keycard      prototype        $15,000.00 reserved     good     -
```

### Blocked checkout

```text
Operation blocked: ITM-0002 requires SUPERVISOR access to check out.
```

### Summary

```text
Vault Summary
Total items: 3
Items by status:
  - available: 2
  - checked_out: 0
  - reserved: 1
  - retired: 0
Total value in vault: $103,700.00
Total value checked out: $0.00
```

---

## Known Failure Modes

| Symptom | Probable Cause | Diagnostic Step | Resolution |
|---|---|---|---|
| `No items matched the current query.` | Empty vault or filters too narrow | List all items with menu option `10` | Clear filters or add items |
| `Operation blocked: Item <id> was not found.` | Wrong item ID | Use menu option `10` | Retry with a valid ID |
| `Operation blocked: ... requires MANAGER/DIRECTOR access` | Actor clearance too low | Check item category and value | Retry with sufficient access |
| `Operation blocked: Item <id> is reserved...` | Item is in `RESERVED` state | Audit the item | Use a different item; no unreserve workflow exists |
| `Operation blocked: Item <id> is not currently checked out.` | Check-in attempted on an available/reserved/retired item | List all items | Only check in checked-out items |
| `Enter a valid monetary amount...` | Invalid money input | Check prompt response | Enter a numeric amount |
| `Choose one of: ...` | Invalid enum input | Review accepted values | Enter an enum name such as `STAFF` or `GOOD` |
| Unexpected crash during search | Invalid free-text search filter | Retry search with blank filters | Use valid status/condition values |

---

## Troubleshooting Decision Tree

```text
App does not start
 ├─ Is Python >= 3.11?
 │   ├─ No → install/use Python 3.11+
 │   └─ Yes
 ├─ Was the package installed?
 │   ├─ No → pip install -r requirements.txt
 │   └─ Yes
 └─ Try python -m vault --demo from repo root

Checkout fails
 ├─ Does the item ID exist?
 │   ├─ No → list items and retry
 │   └─ Yes
 ├─ Is item available?
 │   ├─ checked_out/reserved/retired → cannot check out
 │   └─ available
 └─ Is actor access high enough?
     ├─ No → use a higher access level
     └─ Yes → inspect error message

Reconciliation looks wrong
 ├─ Did you include checked-out items in observed IDs?
 │   ├─ Yes → they will appear unexpected
 │   └─ No
 ├─ Did you omit available/reserved/retired items physically present?
 │   ├─ Yes → they will appear missing
 │   └─ No → audit inventory state
```

---

## Recovery Procedures

### Recover from a mistaken checkout

1. Use menu option `3` to check the item back in.
2. Use menu option `6` to audit the item.
3. Add notes explaining the correction during check-in.

### Recover from incorrect condition update

There is no delete/edit custody record operation. Apply a new condition update with corrective notes.

### Recover from mistaken retirement

There is no unretire workflow in the current CLI. Because retirement is treated as a terminal state, recovery requires restarting from a clean in-memory session or adding a future admin-only unretire method.

### Recover from bad in-memory session

Exit and restart the CLI. There is no persistence, so a restart clears all runtime changes.

---

## Logging Reference

The app does not write application logs to disk.

The audit mechanism is the custody chain stored per item. Every successful state-changing operation appends a `CustodyRecord` with:

- UTC timestamp
- item ID
- action
- actor name
- actor access level
- optional notes

View the chain with menu option `6`.

---

## Maintenance Notes

- Keep `requirements.txt` aligned with `pyproject.toml`.
- Keep public exports in `vault/__init__.py` aligned with domain classes intended for library use.
- Add tests when changing `_CATEGORY_ACCESS_RULES` or value thresholds.
- Consider adding a clock injection point if deterministic custody timestamps become important.
- Consider replacing free-text search filters with enum prompts for better CLI robustness.
- Add persistence before treating this as a long-running operational tool.

---

*Constitution reference: Article 6. The runbook documents setup, operation, verification, failure modes, and recovery paths.*

-e 

---


# Lessons Learned
## App 17 — Secure Inventory Manager
**Vault OS Group | Document 5 of 5**

---

## Project Summary

Secure Inventory Manager is a package-based CLI application that simulates a vault inventory system. It manages valuable items, enforces checkout rules based on access level, tracks item condition and status, records custody history, supports search and reconciliation, and reports summary totals. The project was built to practice encapsulation, composition, state transitions, dataclasses, enums, and CLI-driven workflows in a realistic but still academic scope.

---

## Original Goals vs. Actual Outcome

The original goal was to build a vault that controls item lifecycle operations and preserves a complete custody chain. The delivered app meets that goal: items can be added, checked out, checked in, audited, searched, reconciled, summarized, and retired through controlled `Vault` methods.

The implementation also goes beyond a minimal version by adding:

- package structure
- console script support
- `python -m vault`
- demo mode
- formatted reports
- `Decimal` money handling
- value-tiered access policy
- pytest coverage for domain and CLI behavior

The main gap is persistence. The domain has restore/export-oriented hooks, but the CLI does not yet save inventory to disk. That means the app demonstrates the architecture of a vault but not the operational durability of one.

---

## Technical Decisions That Paid Off

### Returning snapshots instead of internal items

Returning `ItemSnapshot` objects from vault operations made the CLI simple while protecting the internal `Item` objects from direct external mutation. This reinforced the idea that a domain object can expose useful state without exposing its private control surface.

### Using `Decimal` early

Money values appear in search filters, row rendering, and summary totals. Choosing `Decimal` avoided float noise and made tests around monetary values predictable.

### Centralizing state transitions in `Vault`

The best architectural choice was making `Vault` the only path for mutation. Checkout, check-in, condition update, and retirement all follow the same pattern: require item, validate status, validate access, mutate state, append audit record, return snapshot.

### Enums for domain vocabulary

`ItemStatus`, `ItemCondition`, and `AuditAction` made the system more reliable than string literals scattered through the code. The parsing helper for text enums also made CLI input more forgiving.

### Formatting reports on report objects

`ReconciliationReport.format_report()` and `VaultSummary.format_report()` keep report formatting close to the data they summarize. That keeps the CLI from needing to understand every detail of the report internals.

---

## Technical Decisions That Created Debt

### No persistence

The biggest debt is in-memory-only state. For a vault simulator, audit records are important, but they disappear when the process exits. The restore hooks show an awareness of future persistence, but there is no complete persistence adapter yet.

### Hardcoded access policy

`_CATEGORY_ACCESS_RULES` and value thresholds are easy to read, but they are embedded inside `Vault`. If the policy changes often, it should move into a separate policy object or configuration layer.

### Search filter validation is weaker than workflow validation

Most CLI workflows use `_prompt_enum()`, which retries on invalid enum input. Search collects raw text filters and passes them directly into `Vault.search()`. That keeps the code shorter but creates a rough edge: invalid search filters can raise parsing errors instead of giving a guided prompt.

### `RESERVED` status lacks workflows

The model supports `RESERVED`, and checkout correctly blocks reserved items. However, there is no method to reserve or unreserve an item after creation. This makes `RESERVED` useful for seeded data and initial item state, but not as a full lifecycle feature.

### Actor identity is trusted input

The app records actor name and access level, but it does not verify that the actor exists or actually holds that clearance. This is acceptable for the Day 17 scope, but it would be a major limitation in a real facility system.

---

## What Was Harder Than Expected

### Custody integrity affects every operation

It is not enough to change an item’s status. Every operation also needs an audit record with the correct action, actor, access level, and notes. This makes simple state transitions more complex because the design must preserve history at the same time it changes current state.

### Access policy has overlapping dimensions

Checkout permission depends on both category and value. A cheap classified item can still require `DIRECTOR`, while an expensive ordinary item can require elevated access based on value alone. The `max(category_level, value_level)` rule made this manageable.

### Reconciliation semantics require domain judgment

The app had to decide whether checked-out items should count as missing during physical reconciliation. Treating checked-out items as not expected in the vault is the more accurate model, but it required explicit logic rather than a simple "all item IDs should be present" comparison.

---

## What Was Easier Than Expected

### Dataclasses made read models straightforward

`CustodyRecord`, `ItemSnapshot`, `ReconciliationReport`, and `VaultSummary` were natural fits for dataclasses. They reduced boilerplate and made tests easy to write.

### The CLI stayed thin

Because the domain layer contains the rules, the CLI mostly prompts, calls methods, and prints results. This separation made it easier to test both layers.

### `argparse` was enough

The app did not need a third-party CLI library. One startup flag, `--demo`, was enough because the rest of the interaction is menu-driven.

---

## Python-Specific Learnings

- `IntEnum` is useful when enum values need ordering.
- `Enum` classes can be extended with parsing helpers to support user input.
- `Decimal(str(value))` is safer than `Decimal(float_value)` for money normalization.
- `dataclass(frozen=True, slots=True)` is a strong pattern for immutable records.
- `Counter` is a concise way to build status summaries.
- `raise ... from exc` preserves the cause chain for domain-specific exceptions.
- `python -m package` requires a `__main__.py`.
- Package exports in `__init__.py` make a cleaner public API.

---

## Architecture Insights

The main architecture insight is that encapsulation is not just "make fields private." In this project, encapsulation means controlling the path through which state can change. `Vault` is the unit that protects invariants:

- checked-out items have a holder
- retired items cannot be checked out
- reserved items cannot be checked out
- condition changes are audited
- access levels are enforced
- money values are normalized
- summaries are derived from current state

This is more meaningful than simply hiding attributes. The object boundary carries business rules.

---

## Testing Gaps

The test suite covers a strong amount of domain behavior and CLI flow, including:

- enum parsing
- custody record rendering
- duplicate item rejection
- checkout state failures
- access level tiers
- check-in
- condition updates
- retirement
- search
- reconciliation
- summary formatting
- demo vault seeding
- CLI prompt behavior
- CLI menu flows

Remaining gaps:

- No persistence tests, because persistence is not implemented.
- No deterministic clock injection for custody timestamps.
- No tests for a future reserve/unreserve lifecycle.
- No property-based tests for money parsing across unusual numeric inputs.
- No tests around extremely large inventories.
- No test asserting that invalid search filter strings are handled gracefully by the CLI.

---

## Reusable Patterns Identified

### Controlled mutation boundary

The `Vault` method pattern can be reused:

```text
require entity
validate current state
validate actor authority
apply mutation
append audit record
return snapshot
```

This pattern applies to personnel systems, event logs, invite codes, and device control.

### Snapshot return model

Returning snapshots instead of mutable domain objects is useful in any CLI app where state integrity matters.

### Report objects with formatting methods

`VaultSummary` and `ReconciliationReport` show a good pattern for separating report construction from CLI menu logic.

### Enum parsing helper

The `_TextEnum.parse()` pattern is reusable for CLI-friendly enum input.

---

## If I Built This Again

The highest-impact change would be adding a persistence adapter. A JSON persistence layer could save:

- current issue sequence
- items
- custody records
- status
- condition
- current holder

The second-highest-impact change would be extracting access policy into a separate object. That would make it easier to test policy changes independently and avoid growing `Vault` into a catch-all class.

---

## Open Questions

- Should `RESERVED` become a full lifecycle with `reserve_item()` and `release_reservation()`?
- Should retired items be permanently immutable, or should a director-level restore workflow exist?
- Should actor identity come from the App 18 personnel system instead of being typed manually?
- Should audit reports be structured data first and formatted strings second?
- Should reconciliation know about expected checked-out holders and produce a "checked out but observed in vault" category separately from generic unexpected IDs?
- Should value thresholds be configurable per facility?
- Should all CLI workflows be replaced by non-interactive subcommands for scripting?

---

## Final Reflection

This app represents a noticeable step up from basic CLI utilities. It uses classes to protect state, dataclasses to represent records, enums to define the domain vocabulary, and tests to validate important rules. It is not production-ready because state is not persistent and actor authority is trusted input, but it is valid learner work: scoped, understandable, verifiable, and reflective.

---

*Constitution v2.0 checklist: This document satisfies Article 5 for App 17 by documenting design choices, omissions, weaknesses, scaling concerns, and next refactors.*

