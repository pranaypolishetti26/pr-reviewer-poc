# Customer Preferences Service — PR Review POC

A small Spring Boot project designed specifically for an AI PR-review proof of concept.

## What this repo demonstrates

The reviewer should combine:

1. **GitHub PR/Issue data** from the GitHub MCP server.
2. **Project requirements and architecture** from a Bedrock Knowledge Base.
3. The PR diff itself.

The included demo patch intentionally violates documented requirements so the reviewer has something meaningful to catch.

## Knowledge Base documents

Upload only this folder to the S3 location used by your Bedrock Knowledge Base:

```text
docs/knowledge-base/
```

It contains:

- `architecture.md`
- `requirements.md`
- `testing-strategy.md`

## Demo

See `demo/DEMO-STEPS.md`.

