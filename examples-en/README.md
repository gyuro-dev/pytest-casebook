# Examples

Each directory is a ready-to-run example for one thing you may want to do. The top of each YAML explains what the example checks and how to run it.

These are the English versions of the samples in [examples](../examples). The case names and file names are the same; the Python modules end in `_en` so they do not clash with the Japanese samples.

| Directory | What you want to do | What you write |
|---|---|---|
| [01_cli](01_cli) | Run a CLI and check its output | YAML |
| [02_function](02_function) | Call a Python function and check its return value | YAML |
| [03_exception](03_exception) | Check that an exception is raised (also by parent class name or message) | YAML |
| [04_expect](04_expect) | Write the expected results directly in YAML (exact match, contains, regex, only the keys you write) | YAML |
| [05_groups](05_groups) | Organize cases into categories, subcategories and items, and view them as an HTML table | YAML |
| [06_files](06_files) | Put input files in place, run, and check the files that were created | YAML |
| [07_states](07_states) | Check the same operation under states such as "normal" and "maintenance" | YAML + conftest.py |
| [08_db](08_db) | Insert rows into a DB, run, and check the DB afterwards | YAML + conftest.py |
| [09_in_process](09_in_process) | Run a CLI in-process and pass it a mock | YAML + conftest.py |
| [10_normalize](10_normalize) | Normalize IDs, date-times and UUIDs that change on every run | YAML |
| [11_meta_load](11_meta_load) | Attach your own information to cases, and use the same YAML outside pytest | YAML + Python |
| [12_handwritten_golden](12_handwritten_golden) | Write golden files by hand (no headers) | YAML + golden files |
| [13_skip_xfail](13_skip_xfail) | Stop a case with a reason / record a known bug | YAML |
| [14_http_hook](14_http_hook) | Check an HTTP API (the smallest example, without a framework) | YAML + conftest.py |
| [15_fastapi](15_fastapi) | Check a FastAPI API and its DB | YAML + conftest.py |
| [16_flask](16_flask) | Check a Flask API and its DB | YAML + conftest.py |
| [17_targets](17_targets) | Run the same cases against different environments, with golden files per environment | YAML + conftest.py |
| [shop](shop) | An example that combines what 01–13 show | YAML + conftest.py |

## Running

Run from the repository root.

```bash
uv run pytest examples-en
```

To run a single example, pass its directory.

```bash
uv run pytest examples-en/08_db
```

To see the results as an HTML table, add `--casebook-html`.

```bash
uv run pytest examples-en --casebook-html=reports/examples-en.html
```

To regenerate the golden files (`golden/`), add `--casebook-update`.

```bash
uv run pytest examples-en --casebook-update
```

Run `examples-en` and `examples` in separate pytest sessions, not together in one run (17_targets defines the `--target` option in both).

15_fastapi and 16_flask only run when FastAPI / Flask is installed (otherwise they are not collected). In this repository they are part of the development dependencies (installed by `uv sync`). They are not dependencies of pytest-casebook itself.

## Using them in your own project

Copy an example directory under your project's `tests/`, then rewrite the YAML cases and the names of the modules you want to check. Delete `golden/` and recreate it with `--casebook-update`.
