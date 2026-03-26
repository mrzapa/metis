#!/usr/bin/env python3
"""Quick validation of trace_event_schema implementation."""

from metis_app.models.trace_event_schema import (
    EventType,
    EventStatus,
    get_event_category,
    is_valid_event_type,
    get_event_lifecycle,
)

# List all event types
events = list(EventType)
print(f'Total EventType members: {len(events)}')
print(f'EventStatus members: {len(list(EventStatus))}')
print()
print('Event Types by Category:')
categories = {}
for evt in events:
    cat = get_event_category(evt.value)
    if cat not in categories:
        categories[cat] = []
    categories[cat].append(evt.value)

for cat in sorted(categories.keys()):
    types = categories[cat]
    print(f'  {cat}: {len(types)} types - {types}')
    
print()
print('Validation tests:')
print(f'  is_valid_event_type(tool_invoke): {is_valid_event_type("tool_invoke")}')
print(f'  is_valid_event_type(invalid_type): {is_valid_event_type("invalid_type")}')
print(f'  get_event_lifecycle(tool_invoke): {get_event_lifecycle("tool_invoke")}')
print(f'  get_event_lifecycle(stage_start): {get_event_lifecycle("stage_start")}')
print()
print("Expected: 13 event types, 5 categories, all functions working")
