# Customer Preferences Service — Architecture

## Purpose

The Customer Preferences Service stores configuration used by downstream polling jobs.

## Request flow

```text
Client
  |
  v
REST Controller
  |
  v
Service Layer
  |
  v
Configuration Store
```

## Architecture rules

### Controllers must remain stateless

REST controllers are responsible only for accepting HTTP input, calling a service, and converting service results into HTTP responses.

Controllers must **not** hold mutable application configuration in fields. Any configuration that changes while the application runs must be owned by the service layer or configuration store.

### Validation belongs in the service layer

Business validation must be enforced by the service layer so all callers follow the same rules.

### Global polling configuration

The intended flow is:

```text
PUT /api/config/global-polling-interval
        |
        v
GlobalPollingConfigController
        |
        v
GlobalPollingConfigService
        |
        v
Configuration Store
```

The controller must not directly store the global polling interval.

## Current technology

- Java 21
- Spring Boot
- REST APIs
- Gradle
