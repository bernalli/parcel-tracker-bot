# Contributing to parcel-tracker-bot

Thanks for considering a contribution. This document covers the development workflow, code
quality bar, and submission etiquette. Bug reports and translations are as welcome as code.

## Reporting bugs / requesting features

Use the GitHub issue templates:
- **Bug report** — include environment, steps to reproduce, expected vs actual.
- **Feature request** — describe the use case before the implementation.
- **New tracker** — propose a courier with a sample tracking ID and the source you tested against.

## Development setup

Requirements: Python 3.11 or 3.12, `git`, `docker compose`, `make` (optional), a Linux/macOS host.

```bash
git clone https://github.com/bernalli/parcel-tracker-bot.git
cd parcel-tracker-bot
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pre-commit install
```

Run the suite:

```bash
pytest                            # full test suite + coverage gate
ruff check src tests              # lint
ruff format --check src tests     # formatter check
mypy src/parcel_tracker           # strict type checking
```

## Branching & commits

- Branch off `main`. Use `feat/<short-desc>`, `fix/<short-desc>`, `docs/<short-desc>`.
- Follow [Conventional Commits](https://www.conventionalcommits.org): `feat:`, `fix:`, `refactor:`,
  `docs:`, `test:`, `chore:`, `ci:`, `perf:`, `style:`, `build:`.
- One logical change per commit. If you find unrelated issues during your branch, open separate PRs.
- Pre-commit hooks run on every commit (ruff, ruff-format, mypy, gitleaks). Do not bypass with `--no-verify`.

## Pull requests

- Reference the issue you are closing in the PR description: `Closes #123`.
- All checks (CI, security, mypy strict, coverage ≥75%) must pass.
- A maintainer will review. Expect questions about test coverage and edge cases.
- We squash-merge by default; commit history on `main` stays linear.

## Code quality bar

- **Type hints** on every public function. `mypy --strict` is enforced.
- **Tests** for every new behaviour. Coverage gate is 75 % global, ≥90 % for `core/`.
- **No broad `except Exception:`** — `BLE001` is enforced. Catch the specific exceptions the call site can raise.
- **No `print()` in production code** — use `structlog` via `logging`.
- **No magic numbers** — pull constants into `constants.py` or near top of file with a docstring.

## Adding a new courier

A typical tracker plugin is ~150 lines. Read [docs/plugins.md](docs/plugins.md) for a
walk-through and skeleton. Steps:

1. Create `src/parcel_tracker/trackers/<name>.py` with `class <Name>Tracker(AbstractTracker)`.
2. Add tests under `tests/unit/trackers/test_<name>.py` with synthetic HTML fixtures in
   `tests/fixtures/trackers/<name>/`.
3. Register the priority in the docstring and update `docs/trackers.md`.
4. Run the full suite locally before opening the PR.

## Adding a new language

See [docs/i18n.md](docs/i18n.md). Short version:

1. Copy `src/parcel_tracker/i18n/locale/en/LC_MESSAGES/messages.po` to `<lang>/LC_MESSAGES/messages.po`.
2. Translate every `msgstr` (keep the `msgid` lines untouched).
3. Run `python -m parcel_tracker.i18n.build` to compile `.mo` files.
4. Open a PR with the new `.po` only — `.mo` is built in CI.

## License

By contributing you agree your code is published under the MIT License (see [LICENSE](LICENSE)).
