# Changelog

All notable changes to this project are documented in this file. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) (while the major version is 0, an
incompatible change raises the minor version).

## [Unreleased]

### Changed

- **Incompatible**: the check for golden files left over after a case was removed is now
  named `unused_golden_files` (it was `golden_orphans`), so the test id reads
  `casebook_x.yaml::unused_golden_files`. Update `-k` expressions and deselections that
  name it. A case can no longer be named `unused_golden_files` while the check is on;
  `golden_orphans` is free again. The YAML key `check_orphans` is unchanged. The failure
  message now says how to fix it.
- When an HTML report holds a single case file and `casebook_html_title` is not set, the
  browser tab reads "<the file's title:> - Test Specification", so the tabs of several
  reports can be told apart. The heading on the page is unchanged.
- In the HTML report, the expected-result column always reads "Golden file (…)", whether or
  not the golden contents are shown in the fold below. It no longer becomes a "See the golden
  file below (…)" link, which pointed at the row right under it and meant nothing on paper.

### Fixed

- When `unused_golden_files` fails, the HTML report lists the unused golden files in the
  case file's section. Before, pytest failed while the report showed every case passed.

## [0.9.1] - 2026-10-29

### Changed

- "command not found" now says where the command ran and how to fix it: use an installed
  command, or a script by its path from that directory (e.g. `[python, my_cli.py]`). The
  existing `{casebook_dir}` hint for cases run in a temporary working directory stays.
- The ini options are listed in `pytest --help` and in the README by role: collecting,
  running, golden files, reports, language.

### Fixed

- The README's "Getting started" example runs as written: it now includes the small CLI it
  tests (`hello.py`) instead of a `hello` command that does not exist. A test copies the
  example from both READMEs and runs it.
- With `casebook_html_reports` and no `--casebook-html`, the reports of a `--casebook-update`
  run now show the golden files that run wrote, instead of an empty or old one. The
  "… (N more lines)" note under a golden file follows the YAML's `lang:` like the rest of its
  row, not `casebook_lang`.
- The JSON Schema and the README say that `env:` applies to every kind of case, as it has
  since 0.9.0, not only to `command:` cases.

## [0.9.0] - 2026-10-28

### Added

- `lang:` at the top of a case file sets that file's language (`en` or `ja`): the messages
  of its cases (failed comparisons, errors while running, mistakes in the YAML), the texts in
  its report rows, the default `levels`, and the default language of `run_case()`. Without
  it, the `casebook_lang` ini option applies as before.
- The `casebook_html_reports` ini option writes several HTML sheets from one run, one per
  line: `<html file> = <case file patterns>` (comma-separated, globs allowed, relative to
  rootdir). A sheet's headings and labels follow the `lang:` of the files in it when they
  agree; a sheet with no cases is not written and the end of the run says so. `--casebook-html`
  still writes the whole sheet, and `-o casebook_html_reports=` turns the extra sheets off for
  a run. Example: `examples/21_reports`.

### Changed

- `env:` applies to every kind of case and to hooks. While a case runs, its environment
  variables are put over `os.environ` (and restored afterwards), so a CLI run in-process by
  `pytest_casebook_run_command`, the function of a `call:` case and the hook of a `request:`
  case see them without wrapping anything. `env:` on a call / request case used to be an
  error; now it works like on a command case. Manual cases, which are not run, do not
  inherit `env:` (as with `timeout`).
- The contents of `stdin_file:` are read when the case file is loaded and put into
  `case.stdin`, so a `pytest_casebook_run_command` hook (and `run_case()`) no longer has to
  read the file itself. A missing file is reported when the case file is collected, like a
  mistake in the YAML, instead of failing the case at run time.
- `states:` no longer requires a `default` state: a case without `state:` simply has no
  state content when `default` is not defined. Adding one named state no longer forces
  `default: {}` on every other case.
- `observe:`, `marks:` and `levels:` accept a single string as well as a list
  (`observe: files`, `marks: slow`).
- When a case with a working directory (`files:`) cannot find a program written as a path
  relative to the YAML, the error adds a hint to write it as `{casebook_dir}/...`.
- The README, the examples and the JSON Schema spell the matchers as `{$contains: ...}` /
  `{$regex: ...}` everywhere (the `$` may still be omitted under `stdout`, `stderr`, `raises`,
  `body` and `headers`), so there is one spelling to remember.
- The headings and labels of the `--casebook-html` sheet also follow the `lang:` of the case
  files in it when they agree (files without `lang:` keep the ini language, so existing
  reports do not change).
- `--casebook-update` and `--casebook-update-headers` print `Updated golden files: 0 (N
  unchanged)` when nothing was rewritten. Before, such a run printed nothing and could not be
  told from an ordinary run (or from a misspelled option that was ignored).
- The JSON Schema's patterns for case names and `params` element names no longer use `\w`.
  In editors (the VS Code YAML extension and other JavaScript validators) `\w` matches ASCII
  only, so a Japanese case name that loads fine was underlined as an error. The schema now
  rejects only whitespace and `/ \ : [ ]` (and a leading `.` or `-`); the exact rule is
  checked when the file is loaded, as before.

## [0.8.0] - 2026-10-27

### Added

- `--casebook-update-headers` rewrites golden files whose results still match into the
  current form (for example to add `# description:` after turning on
  `casebook_golden_description`), without regenerating everything. A golden file whose
  results differ still fails and is left untouched. Hand-written golden files are rewritten
  into the full form.
- The `--casebook-update` list marks files whose compared result headers changed, e.g.
  `golden/casebook_cli/convert.txt (exit_code 0 → 2)`, so a run that started failing does not
  slip into the golden files looking like any other change.
- `load(path, ini=True)` reads the `casebook_*` options from the pytest configuration file
  (`pytest.ini`, `pyproject.toml`, `tox.ini` or `setup.cfg`, looked up from the case file's
  directory), and `run_case()` uses them as its defaults (`casebook_lang`,
  `casebook_encoding`, `casebook_builtin_patterns`, `casebook_golden_description`).
  Explicit arguments win; without `ini=True`, `load()` behaves as before.

### Changed

- `setup: {files: {}}` (an empty mapping) also runs the case in a fresh temporary working
  directory. Before, only a non-empty `files:` did, and an empty one silently ran the case in
  the YAML's directory.
- In the HTML report, when the golden contents are shown, the expected-result column links to
  the fold below ("See the golden file below (…)") instead of repeating the file name;
  clicking it opens the fold.
- In a case with `expect:`, an `observe:` target (including `files`) that is not also a key of
  `expect:` is a YAML error. Its value used to be fetched and silently thrown away; with
  `expect:`, write the target in `expect:` directly (it is fetched automatically).
- Exceptions defined inside a class are named with their qualified name (`Outer.Inner: …`)
  in golden files and failure messages, matching `raises: "Outer.Inner"`. Golden files of
  such exceptions change.
- `load()` makes the path absolute (like pytest, without resolving symlinks), so
  `CasebookDoc.path` is always absolute.
- `params:` elements are validated strictly by the JSON Schema (only case keys, `name`
  required, no nested `params`), and a `params` template may give the action
  (`command:` / `call:` / `request:` / `manual:`) in each element instead.
- With `load(ini=True)`, an unreadable configuration file raises
  `ValueError("cannot read <path>: …")`.
- Hooks receive `config=None` when called through `run_case()` (typed
  `pytest.Config | None`).
- A string `command:` is split into arguments when the file is loaded, so `Case.command_argv`
  is set for every `command:` case (it used to be set only for a list `command:`). The run
  no longer splits the string again.
- The JSON Schema matches loading more closely: an empty `cases:` list, an empty `states:`,
  a text `expect:` on a `command:` / `call:` / `request:` case and a mapping `expect:` on a
  `manual:` case are schema errors too. The remaining intended differences are listed in
  `tests/test_schema_matrix.py`.
- Expected strings in `expect:` get the same replacements as the actual output (`normalize:`,
  the built-in datetime and UUID) before comparing, so `stdout: 1970-01-01T00:00:00` matches
  instead of failing against `<datetime>`. This covers `stdout`, `stderr`, `body`, `headers`,
  `raises` and the strings inside `return`, `json` and observe targets; only the inside of
  `{regex}` / `{$regex}` is left alone.
- The `--casebook-update` list annotates a new golden file whose result is a failure
  (`(new, exit_code 3)`, `(new, status 404)`, `(new, raises)`), so a run that created the
  golden files does not hide a failing case among the successes.
- Failure diffs show control characters such as ANSI colors as `\x1b[32m` instead of
  writing them raw to the terminal, where a one-code difference was invisible.
- The `golden_orphans` message shows the golden directory relative to the case file, like
  the other messages.
- `expect:` matches `.nan` against a NaN result.

### Fixed

- `load()` with a bare relative path (e.g. `load("casebook_x.yaml")`) followed by `run_case()`
  replaced every `.` in the output with `{casebook_dir}`, and broke `{casebook_dir}` and module
  imports after the case moved into a working directory.
- A `command:` argument containing a newline broke the golden file's header block, so
  `# exit_code:` was silently never compared. Header values are now written on one line.
- A program line such as `----- RESULTS -----` was read as a golden section. Only the known
  titles (`stdout`, `stderr`, `return`, `raises`, `json`, `body`, `observe: …`) are sections.
- The HTML report colored any line starting with `+` or `-` in the failure details (e.g. a
  Markdown `- item` in the actual output); only real diff lines are colored now.
- With `--casebook-update --casebook-html`, the golden contents in the report were the ones
  read at collection time: missing for a newly created golden file and stale for a rewritten
  one. The report now shows the golden file as written.
- A `command:` of only spaces, or a `command:` / `command_prefix:` with an unclosed quote,
  crashed at run time with `IndexError` / `ValueError`. Both are now errors when loading.
- `call:` accepted an empty module or function name (`:f`, `m:`), a relative import (`.m:f`)
  and spaces, and `:f` / `.m:f` crashed with `ValueError` / `TypeError`. They are now loading
  errors, and the JSON Schema rejects a leading `.` too.
- A false-looking value of the wrong type was taken as "not written": `setup: {files: []}`,
  `request: {query: ""}`, `state: ""`, `state: null`, `golden: ""` and the like are now errors.
  `files:` left empty (null) is still allowed, and the JSON Schema now allows it too.
- Errors in a `params:` element (missing `name`, nested `params`) pointed at the template's
  line instead of the element's.
- A program that is found but cannot be started (no execute permission, a directory) raised
  `PermissionError` instead of a casebook run error.
- `Decimal("NaN")` and `Decimal("Infinity")` in a result crashed the serialization.
- A case file that is not UTF-8 (e.g. saved as Shift_JIS) showed a `UnicodeDecodeError`
  traceback instead of a collection error.
- `load(path, golden_dir=...)` with a relative `golden_dir` mixed it with the absolute `path`,
  which broke the golden paths shown in the report.
- The JSON Schema rejects `stdin` together with `stdin_file`, as loading does.
- Under pytest-xdist, `--casebook-update --casebook-html` left the golden contents out of the
  report (the row kept the information from the setup phase). The report now takes the
  information from the latest phase.
- With `--casebook-update --casebook-html`, a case sharing its golden file with an earlier
  case showed no golden contents in the report (the earlier case had already written the
  file, so this one did not re-read it).
- The JSON Schema requires a non-empty `pattern` in `normalize:`, as loading does.
- The CI job that skips the heavy jobs for docs-only changes treated a failing `git diff`
  as "no changes"; it now runs everything in that case, and `CHANGELOG.md` counts as code
  because `tests/test_release_notes.py` checks it.
- `scripts/integration.sh` picks free host ports for PostgreSQL and the API unless
  `CASEBOOK_DB_PORT` / `CASEBOOK_API_PORT` are set; the fixed 58000 was occasionally taken on
  the CI runner ("address already in use").

## [0.7.1] - 2026-10-26

### Added

- The HTML report has a button next to the filter that expands or collapses every golden
  file at once (shown only when golden contents are shown). Rows hidden by the filter follow
  too, and the button label stays in sync when golden files are opened one by one.

### Changed

- In the Japanese HTML report, the observed-targets line in the expected-result column reads
  「実行後の値: …」 instead of 「観察: …」, matching the README. Golden files are unaffected.

## [0.7.0] - 2026-10-25

### Added

- The HTML report shows the compared parts of each golden file, folded under the case like
  the failure details (`casebook_html_golden = off / summary / full`, default `summary`;
  `casebook_html_golden_lines`, default 40). With `--collect-only --casebook-html` the plan
  report becomes a reviewable specification with expected values. A note explains the `<…>`
  notation for replaced values.
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

[Unreleased]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.9.1...HEAD
[0.9.1]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.7.1...v0.8.0
[0.7.1]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.5.2...v0.6.0
[0.5.2]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/gyuro-dev/pytest-casebook/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/gyuro-dev/pytest-casebook/releases/tag/v0.1.0
