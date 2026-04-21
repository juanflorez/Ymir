# TBD / TDD / BDD — Quick Reference

## Trunk-Based Development (TBD)

**Core rule:** One branch (`main`). Everyone commits to trunk daily.

### What this means in practice

- No long-lived feature branches. Short-lived branches (< 1 day) are OK for code review.
- Incomplete work is hidden behind **feature flags**, not on separate branches.
- Every commit must leave the trunk in a deployable state.
- CI runs on every push to main — if it breaks, it's the highest priority fix.

### Feature Flags in TBD

```python
# Branch by abstraction — both paths live in the code
if feature_enabled("new_checkout"):
    return new_checkout_flow(request)
return legacy_checkout_flow(request)
```

The flag is controlled by an environment variable (`FEATURE_NEW_CHECKOUT=true/false`),
not by the branch you're on. This is how you ship code without shipping the feature.

### Dark Launch

Deploy the feature to production with the flag **OFF**. The code is live but invisible to users.
Run smoke tests, check metrics, then flip the flag to release.

### Branch by Abstraction (for larger refactors)

1. Create an abstraction layer over the thing you want to replace.
2. Build the new implementation behind the abstraction.
3. Switch the abstraction to use the new implementation (feature flagged).
4. Remove the old implementation once fully switched.

---

## Test-Driven Development (TDD)

**Cycle:** Red → Green → Refactor

1. **Red** — Write a failing test for the behavior you want.
2. **Green** — Write the minimum code to make it pass.
3. **Refactor** — Clean up without breaking the tests.

### Rules

- Never write production code without a failing test first.
- Only write enough production code to pass the current test.
- Refactor only when tests are green.

### In this project (Django)

```bash
# Run tests
python manage.py test

# Or with pytest
pytest

# Watch mode (re-run on file change)
pytest-watch
```

---

## Behavior-Driven Development (BDD)

BDD writes tests as **user-facing scenarios** using Given/When/Then.

```gherkin
Feature: Test Label

  Scenario: Label is shown when feature is active
    Given the testlabel feature flag is ON
    When I visit the homepage
    Then I should see "Test Label Active"

  Scenario: Label is hidden when feature is off
    Given the testlabel feature flag is OFF
    When I visit the homepage
    Then I should not see "Test Label Active"
```

### In this project

Use `pytest-bdd` or `behave` to wire Gherkin scenarios to Python step definitions.

Feature files live in `tests/features/`.

---

## CI/CD Pipeline (this project)

```
commit to main
    │
    ▼
[pre-commit hook]  → ruff lint + format check
    │
    ▼
[pre-push hook]    → run full test suite
    │
    ▼
[CI]               → build Docker image, tag with commit SHA
    │
    ├──[dev]       → deploy to dev container on deploy server (feature flags configurable)
    │
    └──[prod]      → deploy to prod container on deploy server (all flags OFF by default)
```

### Release Gate

A commit is tagged as a **release candidate** when:
1. All tests pass (unit + BDD scenarios)
2. No regressions detected against current prod baseline
3. Manual quality check passes

Tag: `git tag -a rc-<version> -m "Release candidate <version>"`
