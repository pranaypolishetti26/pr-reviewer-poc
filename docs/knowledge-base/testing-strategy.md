# Customer Preferences Service — Testing Strategy

## Required testing gates

Every pull request must pass:

1. unit tests
2. integration tests

A feature is not complete if either category is missing for new behavior.

## Global polling interval feature

Unit tests must cover:

- value exactly at 60 seconds
- value exactly at 900 seconds
- value below 60 seconds
- value above 900 seconds
- valid update changes the stored value
- invalid update does not change the previous value

Integration tests must cover:

- valid `PUT /api/config/global-polling-interval` returns HTTP 200
- invalid value returns HTTP 400

## Review expectation

A pull request that implements the feature without these tests should be flagged during review.
