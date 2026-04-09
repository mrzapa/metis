## Task Statement

Remove the now-redundant "Interface direction" setting from the METIS settings UI because only one interface direction remains.

## Desired Outcome

- The settings page no longer shows the interface-direction card.
- The web app consistently uses the single remaining interface direction (`motion`) without relying on user selection state.
- Legacy variant bootstrap code is removed or simplified so runtime behavior matches the fixed direction.

## Known Facts / Evidence

- The settings UI block lives in `apps/metis-web/app/settings/page.tsx`.
- The page still keeps local `uiVariant` state and writes `metis-ui-variant` into `localStorage`.
- App bootstrap still accepts legacy `refined` and `bold` values in `apps/metis-web/components/ui-variant-bootstrap.tsx`.
- Root layout currently renders `data-ui-variant="refined"`.
- Runtime behavior in `apps/metis-web/app/page.tsx` checks whether `document.documentElement.dataset.uiVariant === "motion"`.

## Constraints

- Keep the diff small and reversible.
- Prefer deletion over adding new abstraction.
- Add regression coverage before cleanup edits where behavior is not already protected.
- Do not disturb unrelated user changes already present in the worktree.

## Unknowns / Open Questions

- Whether any tests already cover the settings header copy or layout data attribute.
- Whether the legacy public bootstrap script is still referenced anywhere at runtime.

## Likely Touchpoints

- `apps/metis-web/app/settings/page.tsx`
- `apps/metis-web/app/layout.tsx`
- `apps/metis-web/components/ui-variant-bootstrap.tsx`
- `apps/metis-web/public/ui-variant-bootstrap.js`
- `apps/metis-web/app/__tests__/...` or a new targeted regression test
