
Vault OS
Secure Facility Management Simulator
App Scope & Feature Specifications
The Pillar: OOP & State (Classes, Inheritance, Encapsulation)
Language: Python

Student Level: 6 months of Python & system architecture

Repository layout
Application code lives in the **`vault/`** package (`vault/domain.py`, `vault/cli.py`, etc.). Automated tests live under **`tests/`**. The project name on PyPI is `vault-os`; the importable package name is `vault`.

Development
From the repository root:

1. `python -m venv .venv` then activate (`.venv\Scripts\activate` on Windows, `source .venv/bin/activate` on Unix).
2. Install the project:
   - **`pip install -r requirements.txt`** — editable install plus dev dependencies (pytest), as declared in `pyproject.toml`; or
   - **`pip install -e ".[dev]"`** — same result using only `pyproject.toml`.
3. **`pytest`** — run the full test suite. With the repo root as the working directory, `vault/` is on `sys.path` so this often works before step 2; CI always installs from the repo first.
4. **`python -m vault --demo`** — launch the CLI with sample inventory (exit with `0`).

**Production-style install** (CLI and library only, no pytest): `pip install -e .`

Dependency files: **`requirements.txt`** references the local package with the **`dev`** extra. Canonical version ranges stay in **`pyproject.toml`** (`[project]` / `[project.optional-dependencies]`).

CI runs **`pip install -r requirements.txt`** then **`pytest`** on every push and pull request (see `.github/workflows/ci.yml`).

 
Overview
Vault OS is a class-based simulation of a secure facility — think a museum, data center, or bank vault. Across seven days (Days 15–21), each app introduces a new subsystem: devices, access control, inventory, personnel, events, invite codes, and finally a full integration layer that wires everything into an interactive CLI simulation.

Each app is scoped to be achievable in a focused day of work by a student with six months of Python and system architecture experience. The apps must demonstrate real command of OOP principles — not toys, but not over-engineered production systems either. The student should be making deliberate design choices and be able to explain why.

Day 17 — Secure Inventory Manager 
A CLI application that simulates a vault for managing valuable items with full custody tracking. The student builds an Item class, a CustodyRecord dataclass, and a Vault class that mediates all interactions with the inventory. Nothing in the vault can be modified directly — every state change goes through vault methods, and every change produces an immutable audit record.
The core design lesson is encapsulation and composition. The vault owns the items. External code requests actions, and the vault validates, executes, and logs them. The custody chain is a first-class data structure, not an afterthought.
Features:
•	Item class with unique ID, name, category, monetary value, current status (available, checked_out, reserved, retired), and a condition field (mint, good, fair, damaged)
•	CustodyRecord as a frozen dataclass: timestamp, item ID, action (checked_in, checked_out, condition_changed, retired), actor name, actor access level, and an optional notes field
•	Each item maintains its own list of CustodyRecord objects, forming the complete custody chain
•	Vault class that holds all items and exposes methods: add_item(), check_out(), check_in(), update_condition(), retire_item(), audit_item(), and search() — no direct access to the item list from outside
•	Access level validation on check-out: the vault takes an access level parameter and enforces minimum requirements based on item category or value (e.g., items above a certain value require MANAGER level)
•	Check-out validation: cannot check out an item that is already checked out, reserved, or retired
•	audit_item() returns the full custody chain for a given item as a formatted report
•	search() supports filtering by category, status, condition, and value range
•	reconcile() method that checks expected state against a provided list of item IDs (simulating a physical count) and reports discrepancies — items missing from the count, items in the count that aren’t in the vault
•	VaultSummary that reports total items, items by status, total value in vault, and total value checked out
•	CLI interface: add items, check out, check in, audit an item, search, run reconciliation, view summary
