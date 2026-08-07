# scripts/

Headless alternatives to the notebook, for when a Colab Enterprise runtime is slow or
unavailable.

`load.sh` reaches the same end state as `notebooks/01_load_explore.ipynb` — the same tables, in
the same dataset, in your project. Use the notebook if you can: it explains what it's doing and
why, and the explanations matter. Use this if you can't.

## Running it

From the **root of the repo**, in Cloud Shell:

```bash
bash scripts/load.sh              # loads the default city
bash scripts/load.sh --list       # show every available city
bash scripts/load.sh --help       # usage
```

Invoke it with `bash` rather than `./scripts/load.sh`. That way it works whether or not the
file's executable bit survived however your copy of this repo was created.

## It is safe to run more than once

Every table is fully replaced, never appended to. So if you cancel it halfway through, or you
aren't sure whether it finished, just run it again — the end state is the same either way.
