Differences from the TypeScript SDK
===================================

acodex aims for one-to-one feature parity with the vendored TypeScript SDK while applying a small
number of intentional Python-specific adaptations (for example: snake_case naming and kwargs-based
options).

Top differences (high level)
----------------------------

- **snake_case surface**: TS camelCase names map to Python snake_case (methods, option keys, model
  fields).
- **kwargs options**: instead of passing a single options object, Python passes options as kwargs
  with `TypedDict` typing.
- **cancellation**: TS uses ``AbortSignal``; Python uses ``threading.Event`` / ``asyncio.Event`` via
  ``TurnOptions.signal``.
- **return models**: TS uses structural object types; Python uses frozen dataclasses for events and
  items.
- **typed structured output**: Python adds ``output_type`` + ``Turn.structured_response`` on top of
  ``output_schema``.

When to use this page
---------------------

- You want to understand how Python differs from the upstream TypeScript surface.
- You are deciding whether a change should be documented as a deliberate divergence.

The complete, source-linked list lives in the repository file ``DIFFERENCES.md``. For the policy
and enforcement mechanics, see :doc:`parity-and-automation`.
