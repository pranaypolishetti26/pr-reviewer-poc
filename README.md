# Customer Preferences Service — PR Review POC

A small Spring Boot project designed specifically for an AI PR-review proof of concept.

## What this repo demonstrates

The reviewer should combine:

1. **GitHub PR/Issue data** from the GitHub MCP server.
2. **Project requirements and architecture** from a Bedrock Knowledge Base.
3. The PR diff itself.

The included demo patch intentionally violates documented requirements so the reviewer has something meaningful to catch.

## CodeBuild PR reviews

The PR webhook supplies the PR number. CodeBuild retrieves the latest PR head SHA
with the existing GitHub token, saves it to `/tmp/pr-reviewer-head-sha`, and fetches
and checks out that exact commit before running Gradle or Kiro.
CodeBuild runs `gradle clean build`, captures
its output and exit code, and runs Kiro even when Gradle fails. Kiro uses GitHub
PR/Issue read tools and the existing Knowledge Base MCP. CodeBuild supplies the
Gradle output through stdin and captures Kiro's JSON response from its ACP stream
into `/tmp/pr-reviewer-review.json`. Kiro has no local file or shell tools and
does not rerun builds/tests or publish to GitHub.

The agent's `tools`, `allowedTools`, and permission rules explicitly allow only
the three MCP read tools. Built-in tools and other MCP tools are denied.
CodeBuild runs Kiro V3 outside the PR checkout to avoid loading PR-defined agent
overrides or hooks, without blanket tool trust, and requires MCP startup.
Approved reads run without interactive approval. Failed tools, permission
requests, error responses, and missing successful PR/Knowledge Base calls fail
the review before publishing. The Issue read tool must be used when an issue is
linked; its failures also fail the review.

CodeBuild validates the JSON and checks its build result against the recorded
Gradle exit code before publishing through the GitHub REST API. It updates the
publishing account's comment marked `<!-- kiro-pr-reviewer -->` on reruns (or
migrates that account's earlier `## Kiro PR Review` comment). Other accounts'
comments are left alone. Sequential reruns reuse the comment; simultaneous first
runs can race when creating it.

Reviews include the pinned `head_sha`. Immediately before creating or updating a
comment, the publisher retrieves the PR head again. If it changed, it removes the
review JSON, prints `STALE_REVIEW` with both SHAs, and exits with code 3, failing
CodeBuild without changing any GitHub comment. GitHub comments do not support an
atomic head-SHA condition, so a push between this final check and the write remains
a small race window. The published comment identifies the reviewed commit.

The existing Secrets Manager `GITHUB_PERSONAL_ACCESS_TOKEN` supplies both GitHub
MCP authentication and publishing authentication. The token needs PR or Issues
write permission for the CodeBuild publisher. Kiro's MCP exposes only read tools.

Failed Kiro runs, missing/invalid JSON, and publishing errors fail the build.
No comment is posted for failed Kiro runs or invalid reviews. A valid review of a
failed Gradle build is published as `NEEDS_CHANGES`, then CodeBuild fails.

Validate the publisher locally without contacting GitHub:

```sh
python3 -m unittest discover -s tests
```

## Observability

CodeBuild emits JSON events for workflow start/finish, checkout, Gradle, Kiro,
review validation, publishing, and failures. Each event includes the PR number,
reviewed SHA, stage, exit code, build/test status, review verdict, elapsed workflow
and stage durations, and a fixed error code. Fields remain `UNKNOWN` or null until
results are available. Test status comes from the validated review's interpretation
of the Gradle log; it is not an independently parsed test report.

`github_mcp_used` and `knowledge_base_mcp_used` come from successful tool calls in
the captured ACP stream, rather than the model's evidence claims. They are false
when no successful call has been observed, including before Kiro runs. Events go
to the existing CodeBuild log output; no new AWS service is required.

Only bounded metadata is logged. Environment dumps, API payloads, raw model text,
raw Gradle/checkout/Kiro output, and exception messages are excluded from console
logging. Raw outputs remain local workflow inputs in `/tmp`; do not publish those
files as log artifacts. The reviewer agent configuration is unchanged.

## Local review-quality evaluation

[evals/scenarios.json](evals/scenarios.json) contains four synthetic scenarios,
with requirements, expected verdicts, and issue-specific matching phrases:
a complete global interval implementation, the flawed demo, missing tests, and a
failed build. These fixtures describe intended PR changes; they do not create PRs
or call Kiro. Save the structured Kiro review for the matching scenario, then run:

```sh
python3 scripts/evaluate_reviews.py --scenario bad-demo --review /path/to/review.json
```

Run a fully offline smoke example with the included hand-written good review:

```sh
python3 scripts/evaluate_reviews.py --scenario good-global-interval --review evals/example-good-review.json
```

The evaluator validates the existing JSON contract and expected Gradle exit code,
then reports detected/missed issue IDs, unmatched finding indexes (false positives),
verdict/test-result agreement, recall, and precision. Exit codes are 0 for a match,
1 for quality mismatches, and 2 for invalid input. It needs only Python's standard
library, no credentials or AWS setup, and never publishes GitHub comments.

Matching is a case-insensitive phrase heuristic: each issue needs one phrase from
each term group and the expected severity. Combined findings can cover several
issues. This is a small regression rubric, not semantic judgment; wording changes,
negation, and unexpected valid findings need manual inspection or rubric updates.
The example demonstrates the evaluator, not measured Kiro performance.

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
