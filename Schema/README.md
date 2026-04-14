# Schema

This folder contains JSON Schema files for the current Vault OS domain model.

## What these files map to

The schemas were designed to mirror the repository's core Python types in `vault/domain.py`:

- `CustodyRecord` → `custody_record.schema.json`
- `Item` → `item.schema.json`
- `ItemSnapshot` → `item_snapshot.schema.json`
- `ReconciliationReport` → `reconciliation_report.schema.json`
- `VaultSummary` → `vault_summary.schema.json`
- Full persisted vault export/state → `vault_state.schema.json`
- Shared enum/value definitions → `_shared.schema.json`

## Design choices

- **Decimal money values are strings** such as `"87500.00"` so precision is not lost during JSON serialization.
- **Enum values match the Python domain layer**:
  - `AccessLevel` uses enum names like `MANAGER`
  - `ItemStatus`, `ItemCondition`, and `AuditAction` use the lower-snake-case values used in the app
- **Categories are normalized** to lower snake case, matching `vault.domain._normalize_category()`.
- `vault_state.schema.json` is included as a practical export/import contract for future persistence features because the codebase already exposes inventory and custody-restore helpers.

## Suggested usage

Validate a full export with any Draft 2020-12 compatible validator:

```bash
python -m jsonschema -i vault_state.json Schema/vault_state.schema.json
```

Or validate an individual item:

```bash
python -m jsonschema -i item.json Schema/item.schema.json
```

## Folder contents

- `_shared.schema.json`
- `custody_record.schema.json`
- `item.schema.json`
- `item_snapshot.schema.json`
- `reconciliation_report.schema.json`
- `vault_summary.schema.json`
- `vault_state.schema.json`
