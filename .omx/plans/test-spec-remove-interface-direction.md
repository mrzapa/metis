# Test Spec: Remove Interface Direction Setting

## Regression Coverage

- A targeted UI regression test asserts the settings page does not render the "Interface direction" section.
- A targeted regression test asserts the app root layout exposes `data-ui-variant="motion"` as the fixed runtime direction.

## Manual / Targeted Verification

- `vitest` passes for the targeted regression test file(s).
- A type-aware verification step confirms the edited TypeScript files compile cleanly.
