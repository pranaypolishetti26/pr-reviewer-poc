# Customer Preferences Service — Functional Requirements

## Existing customer preference behavior

Each customer can have a polling interval.

- minimum: 30 seconds
- maximum: 3600 seconds
- invalid values must return HTTP 400

## Feature: Configurable global polling interval

The service must support a global polling interval that acts as the default for customers without an individual override.

### API

```text
PUT /api/config/global-polling-interval
```

Request:

```json
{
  "pollingIntervalSeconds": 120
}
```

### Validation

The global polling interval must be between **60 and 900 seconds inclusive**.

If the value is outside this range:

- return HTTP 400
- do not change the existing global polling interval

### Default

The default global polling interval is **300 seconds**.

### Ownership

The global polling interval must be managed by the service layer. The REST controller must remain stateless.

### Compatibility

Existing customer-specific preference APIs must continue to work without behavior changes.
