# scripts/

## `load.sh`

A headless fallback that reaches the same end state as `notebooks/c2_01_load_explore.ipynb`,
rebuilding all four BigQuery tables from a pre-staged snapshot in Cloud Storage.

```bash
bash scripts/load.sh                # defaults to seattle
bash scripts/load.sh philadelphia
bash scripts/load.sh --list         # show available metros
```

Invoke it with `bash`, not `./scripts/load.sh`—that way it works regardless of whether the
file arrived with its executable bit set, which depends on how your repo was created.

Safe to run repeatedly. Every table load uses `--replace`, so the script is idempotent and
interrupting it breaks nothing.

**Use the notebook if you can.** This script gets you the tables without the teaching, and one
piece of that teaching—which half of the recipient data is real and which half is generated—is
something judges will ask you about directly.
