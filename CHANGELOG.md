# Changelog

All notable changes to this project are documented in this file. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) (while the major version is 0, an
incompatible change raises the minor version).

## [Unreleased]

### Fixed

- A `command:` that times out now also stops the processes it started. Before, on Windows the
  run waited until those processes ended (e.g. a command run through `cmd /c`), so `timeout`
  did not work; on Linux and macOS they kept running in the background.
- `--casebook-update` fails a case when another case uses the same golden file with a
  different result (`golden:` pointing to one file, or case names that differ only in case,
  such as `Add` and `add`, on Windows). Before, the later case silently overwrote the file and
  the earlier case failed on the next run.
- `--casebook-html` no longer stops with an internal error when another plugin reports its own
  outcome, such as `rerun` from pytest-rerunfailures. Those reports are ignored, and the result
  of the last attempt is shown.
- `timeout` must be a positive number, as the JSON Schema already said. `0` or a negative
  number made the case always time out, and `.inf` stopped the case with an error.
- A case cannot be named `golden_orphans` while `check_orphans` is on, because the check for
  leftover golden files uses that test name (there were two tests with the same ID).

## [0.4.0] - 2026-10-23

### Added

- `env:` sets environment variables for `command:` cases. It can be written at the top of the
  case file, on groups and on cases, and is merged key by key (file -> group -> case; `null`
  removes an inherited value). Exposed as `Case.env` and `CasebookDoc.env`.
- `timeout` now also applies to `call:` and `request:` cases: the case fails when the
  function or the request hook does not finish in time. The function is not stopped (it
  keeps running in a background thread); use pytest-timeout for a hard limit.
- The HTML report can be filtered by result (toggle buttons with counts) and by text
  (groups, case, command, description, preconditions, expected results).

### Fixed

- `golden_orphans` now also checks golden files with the extensions used in `golden:`
  (e.g. `.json`), not only `.txt`. Other files in the golden directory are still ignored.

## [0.3.0] - 2026-10-23

### Changed

- Messages for mistakes in the YAML and for errors while running a case (command not found,
  cannot import a function, etc.) now follow `casebook_lang` too (English by default).
- `pytest_casebook.load()` takes `lang` (the language of the messages and of the default
  `levels`; defaults to `en`). Without `levels`, the level names of that language are used
  (up to 0.2.0 the default was the Japanese 大項目・中項目・小項目).

### Added

- Write the test specification sheet without running the cases:
  `pytest --collect-only --casebook-html=...`. Cases that were collected but not run are kept
  in the report as "Not run" (also when `-x` stops the session).
- The JSON Schema can be referenced by its GitHub URL (`$id` in the schema, and
  `# yaml-language-server: $schema=...` on the first line of the samples and in the README).
  The descriptions shown by editors are in English and Japanese.

## [0.2.0] - 2026-10-22

### Changed

- The default language of the HTML report and of comparison failures is now English
  (`casebook_lang` defaults to `en` instead of `ja`). Set `casebook_lang = "ja"` for
  Japanese.
- Golden files write `(no files)` for an empty `files` target whatever the language
  (0.1.0 wrote 「（ファイルなし）」).

## [0.1.0] - 2026-10-22

The first release.

### Added

- Write cases in YAML as "preconditions -> action -> expected result" and run them with pytest
  - Actions: run a CLI (`command:`), call a Python function (`call:`, async supported), send a
    request to an HTTP API (`request:`)
  - Preconditions: `setup:` (`files` are put in a working directory; everything else is passed
    to the `pytest_casebook_setup` hook) and named preconditions, `states:`
  - Expected results: `expect:` in YAML, or golden files (generated with `--casebook-update`;
    only the results are compared, and the headers can be omitted when written by hand)
  - Values after the action: `observe:` (e.g. DB rows written one per line into golden files)
- Nested groups such as categories / subcategories / items, and an HTML test specification
  sheet with `--casebook-html` (English or Japanese with `casebook_lang`)
- Matchers in `expect:`: exact, `{contains}` and `{regex}` for text; only the written keys,
  `$contains`, `$regex`, `$unordered` and `$includes` for values
- Normalization of values that change on every run (datetimes and UUIDs automatically; others
  with `normalize:` or hooks)
- Reasons for `skip:` / `xfail:`; free-form `meta:`; `pytest_casebook.load()` to read the YAML
  outside pytest
- The YAML line of a failed case is reported; a JSON Schema (`pytest_casebook.SCHEMA_PATH`)
  for editor completion and validation
- Program names in `command:` (such as `python`) are looked up on PATH (the virtual
  environment's Python is used on Windows too). Works with pytest-cov; subprocesses are
  measured with coverage.py's `patch = ["subprocess"]`
- Depends only on pytest and PyYAML. HTTP requests are sent with your framework's test client
  (adapters in `pytest_casebook.http`)
- Checked with Python 3.11-3.15, pytest 8 / 9 and pytest-xdist (Windows and Ubuntu 22.04 on
  WSL), mypy (strict) and ruff

[Unreleased]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/gyuro-dev/pytest-casebook/releases/tag/v0.1.0
