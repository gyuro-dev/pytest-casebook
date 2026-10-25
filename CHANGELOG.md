# Changelog

All notable changes to this project are documented in this file. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) (while the major version is 0, an
incompatible change raises the minor version).

## [Unreleased]

### Added

- `pytest_casebook.run_case()` runs one case outside pytest and returns the result as a
  string in the golden-file format: the same text `--casebook-update` writes, with changing
  values already normalized (no comparison is made). `hooks` takes any object or module with
  `pytest_casebook_*` functions, e.g. an imported conftest module. Failures while running
  raise `pytest_casebook.CasebookRunError` (now exported); manual cases cannot be run.
- The `casebook_golden_description` ini option (default `false`): golden files written by
  `--casebook-update` get a `# description: <the case's description>` line right after
  `# case:` for cases that have a description. The line is an explanation and is never
  compared, so existing files pick it up the next time they are rewritten.

## [0.6.0] - 2026-10-25

### Added

- `params:` writes cases that differ only in arguments and expected values as rows. The case
  becomes a template, and every element is laid over it (replacing its keys wholesale),
  giving one ordinary case per element named `<case name>-<element name>`. See the
  `20_params` sample.
- `--casebook-update` ends the run with a list of the golden files it rewrote (before, only
  the HTML report's "updated" badge and git diff showed them).
- `timeout:` can be written at the top of the case file and on groups as the default for the
  cases inside; the nearest value wins and a case's own `timeout:` overrides it. Manual
  cases never run, so the default does not apply to them.
- `stdin_file:` passes a file to a command's standard input (a relative path inside the
  YAML's directory, read as UTF-8; cannot be combined with `stdin:`).
- The README links to a live demo report on GitHub Pages
  (https://gyuro-dev.github.io/pytest-casebook/), and has a troubleshooting section.

### Changed

- `decimal.Decimal` values are compared and written as numbers (`int` for integral values,
  `float` otherwise). DynamoDB returns numbers as `Decimal`, so until now an observe hook had
  to convert them itself, or `price: 300` in the YAML never matched. Golden files that
  recorded the old `Decimal('…')` text change.
- Case names that differ only in letter case (such as `Add` and `add`) are an error: on
  Windows their golden files are the same file, so a case file written on Linux broke there,
  and only `--casebook-update` noticed.
- A group whose `cases:` is an empty list is an error, like the file-level `cases: []`.

## [0.5.2] - 2026-10-25

### Changed

- A file whose `cases:` is an empty list is an error, like a file without `cases:` (it
  silently passed with only the golden-file check before).
- A case name cannot start with `.` or `-` (`.foo` made the golden file a dotfile, which
  the check for leftover golden files skips).
- In `observe: [files]` / `expect: {files: ...}`, a file that is not UTF-8 (an image etc.)
  is written as one line with its size and SHA-256, instead of being read with replacement
  characters. Different bytes used to produce the same replacement characters, so a changed
  binary file could pass; now it fails. Golden files of binary files change.

### Fixed

- `{casebook_dir}` in `env:` values is replaced with the YAML's directory, as in `command:`
  (it was passed to the program as the literal token).
- A case's `request: headers:` now overrides `request_defaults` headers whatever the case of
  the header name (`authorization` vs `Authorization` sent both headers before).
- In the `--collect-only` plan report, a manual case without `result:` shows "Manual"
  instead of "Not run" (it will not run).

## [0.5.1] - 2026-10-24

### Fixed

- When a case cannot be run (command not found, cannot import a function, timeout, …), the
  message is shown once. Before, it was repeated after "During handling of the above
  exception, another exception occurred:" (and the import error a third time).
- `pytest --help` describes the options and ini settings in English (they were in Japanese
  only, although the default language is English).
- Clearer messages for common mistakes: `skip: true` / `xfail: true` show how to write the
  reason, `expect: {}` says that at least one item is needed, and a misspelled result key in
  `expect:` (e.g. `retrun`) suggests the right one instead of only saying that the observe
  hook returned nothing.

## [0.5.0] - 2026-10-24

### Added

- Manual cases: checks that cannot be automated (looking at a screen, printed forms) go in the
  same test specification sheet. Write the steps in `manual:` instead of `command:` / `call:` /
  `request:`, the expected results as text in `expect:` (a string or a list of strings), and
  the result checked by hand in `result:` (`passed`, `failed` or `skipped`). Manual cases are
  never run; without `result:` they are skipped and the HTML report shows them as "Manual".
  `Case.kind` can now be `"manual"` (new fields `Case.manual`, `Case.manual_expect` and
  `Case.result`). See the `18_manual` sample.
- A sample for code that uses AWS (`19_aws`: S3, DynamoDB and SQS with moto), and a README
  section on checking AWS with moto and with real AWS.

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

[Unreleased]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.5.2...v0.6.0
[0.5.2]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/gyuro-dev/pytest-casebook/releases/tag/v0.1.0
