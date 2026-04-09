# PRD: Remove Interface Direction Setting

## Goal

Simplify the settings experience now that the interface direction is no longer configurable.

## User Story

As a METIS user, I should not see a configuration control for interface direction when there is only one supported direction, so the settings page reflects the real product surface without implying extra choices.

## Acceptance Criteria

- The settings page no longer renders the "Interface direction" heading or the single-option "Motion" card.
- The application defaults to the supported direction without reading or persisting a user-selected variant.
- No runtime code path depends on a settings-page side effect to enable the supported direction.
- Regression coverage verifies the fixed direction and absence of the redundant settings copy.
