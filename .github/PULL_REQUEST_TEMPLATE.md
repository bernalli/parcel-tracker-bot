## Summary

<!-- One paragraph: what changed and why. -->

Closes #<issue>.

## Changes

- ...
- ...

## Testing

- [ ] `pytest` passes locally (suite + coverage gate).
- [ ] `ruff check src tests` clean.
- [ ] `mypy src/parcel_tracker` clean.
- [ ] Added/updated tests for the changed behaviour.

## Checklist

- [ ] Conventional commit messages on every commit.
- [ ] Docs updated where relevant (`README.md`, `docs/*.md`, `CHANGELOG.md`).
- [ ] No secrets, tokens, or personal tracking IDs in the diff.
- [ ] If adding a new tracker: tests cover delivered / in_transit / out_for_delivery /
      not_found, regex patterns are anchored, priority documented in `docs/trackers.md`.
- [ ] If adding a new language: `messages.po` translated end-to-end, no empty `msgstr`.

## Notes for reviewer

<!-- Anything that helps the reviewer understand the trade-offs. Optional. -->
