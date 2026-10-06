# Add configurable global polling interval

## Problem

Polling jobs currently rely on customer-specific values. We need a global default that can be changed without restarting the application.

## Acceptance criteria

- Add `PUT /api/config/global-polling-interval`.
- Accept `pollingIntervalSeconds` in the request body.
- Only values from **60 through 900 seconds inclusive** are valid.
- Invalid values return HTTP 400.
- An invalid update must not overwrite the previously valid value.
- Default value is 300 seconds.
- The controller must remain stateless and delegate to the service layer.
- Add unit tests and integration tests for the new behavior.
- Existing customer preference APIs must remain unchanged.
