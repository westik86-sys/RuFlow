# Codex project rules

## Goal

Improve code quality and performance without changing visible product behavior unless explicitly requested.

## Working rules

1. Before editing code, inspect the relevant files and explain the refactoring plan.
2. Prefer small, reviewable changes over large rewrites.
3. Do not rename public APIs, files, targets, schemes, assets, or localization keys unless necessary.
4. Preserve existing UI behavior, navigation, animations, accessibility labels, and state handling.
5. After every meaningful change, run `./scripts/verify_ios.py`.
6. If tests fail, fix the root cause instead of weakening or deleting tests.
7. Add or update tests for changed business logic, view models, parsers, formatters, state machines, reducers, and critical user flows.
8. Do not optimize by guesswork. For performance changes, first identify the suspected bottleneck and explain why the change should help.
9. At the end, summarize changed files, risks, verification commands, and remaining concerns.

## Done means

- The project builds.
- Existing tests pass.
- New or updated tests cover the changed behavior.
- The diff is minimal and explainable.
- No unrelated formatting or architecture churn is introduced.
