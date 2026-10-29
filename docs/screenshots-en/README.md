# Cases for the README.md screenshots

These cases produce the images of the HTML report (`--casebook-html`) shown in [README.md](../../README.md). They are the English version of [docs/screenshots](../screenshots), run with `casebook_lang=en`.

| File | Contents |
|---|---|
| `casebook_demo_en.yaml` | the cases. One failure, one skip and one known bug (xfail) are included on purpose |
| `store_en.py` | the target (a CLI and Python functions) |
| `conftest.py` | a hook that runs the CLI in-process, and a hook that sets up the stock for each state |
| `golden/` | golden files. `receipt_free_shipping.txt` is written by hand with the correct spec (free shipping) so that it fails |

`docs/` is not in pytest's `testpaths`, so a normal `uv run pytest` does not collect these.

To regenerate the images, run `scripts/screenshots.sh` from the repository root (Windows Git Bash with Microsoft Edge). It writes both the Japanese and the English images to `docs/images/`. Do not use `--casebook-update` here: it would rewrite the golden file of the failing case.
