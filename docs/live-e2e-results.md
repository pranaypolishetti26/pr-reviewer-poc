# Live PR-review POC verification — 2026-10-10

These checks used the existing AWS resources in `us-east-2` and the real GitHub
webhooks. The intentionally faulty [PR #6](https://github.com/pranaypolishetti26/pr-reviewer-poc/pull/6)
is an evaluation fixture and must not be merged.

## Documentation synchronization

[PR #4](https://github.com/pranaypolishetti26/pr-reviewer-poc/pull/4) added the
`GLOBAL-INTERVAL-MISSING-VALUE` requirement and its required coverage. There was
no documentation-sync run while the changes were unmerged. After merging,
[Actions run 38061783918](https://github.com/pranaypolishetti26/pr-reviewer-poc/actions/runs/38061783918)
succeeded: S3 documents matched the merged files, and Bedrock ingestion job
`LHORCQ0TA0` completed with two modified documents indexed and zero failures.
An independent Bedrock retrieval returned the new requirement from
`customer-preferences-service/requirements.md`.

GitHub OIDC and the dedicated `pr-reviewer-docs-sync` role were configured.
Trust is limited to this repository's main branch; permissions cover the existing
document prefix and Knowledge Base. Repository Variables API access was
unavailable with the existing GitHub tokens, so the workflow uses overridable,
nonsecret defaults for the verified resource IDs. See [setup](knowledge-base-sync.md).
No new bucket, Knowledge Base, or data source was created.

This live check covered modified documents. New/deleted-document handling and
main/event guards also have local mocked checks; this run did not exercise a
live document deletion.

## Fault detection and CodeBuild publishing

[Issue #5](https://github.com/pranaypolishetti26/pr-reviewer-poc/issues/5) supplies
the acceptance criteria. PR #6 implements the demo endpoint without range
validation, a service layer, missing/null handling, or feature tests.

Build `kiro-pr-review-poc:bd9e9c28-154d-43fd-b518-f411e5bbe1ab` reviewed commit
`fe439e04fcbee48c8b4f188e76ed4278c8416440`. Gradle and Kiro both exited zero,
JSON validation passed, and CodeBuild's Python publisher posted
[comment 6098972402](https://github.com/pranaypolishetti26/pr-reviewer-poc/pull/6#issuecomment-6098972402)
with verdict **NEEDS_CHANGES**. Structured events record successful GitHub MCP
and Knowledge Base MCP use, PASS build/tests, publication, and about 93 seconds
of workflow execution. Kiro's configuration permits only PR/Issue reads and the
project-documents search tool; it has no GitHub comment/write tool.

The review found controller-owned mutable state, missing range/HTTP 400
validation, missing/null HTTP 500 behavior, and missing unit/integration tests.
It explicitly cited the newly ingested requirement, demonstrating that a green
build can still receive NEEDS_CHANGES using updated Knowledge Base evidence.
A separate safe tooling [PR #7](https://github.com/pranaypolishetti26/pr-reviewer-poc/pull/7)
received APPROVE and its CodeBuild run succeeded before it was merged.

Live testing uncovered and fixed a project-level CodeBuild repository value
that was a URL instead of `owner/repo`, plus Kiro stream-envelope and response
extraction mismatches. The parser fixes reached main through PR #7, without
merging the faulty application code. Earlier invalid-output runs failed without
posting a review. Extraction still rejects malformed JSON, multiple JSON
documents, trailing text, failed tools, and invalid schemas.

## Rerun behavior

Retry build `kiro-pr-review-poc:c7d85b26-f957-469c-9a9c-65fa7e1b5ed5` succeeded
with the same commit and NEEDS_CHANGES verdict. CodeBuild updated comment
`6098972402` at `2026-10-10T15:17:55Z`; the PR still had exactly one marked
reviewer comment. No duplicate was created.

## Reproducible offline evaluation and quality limits

`evals/observed-bad-review.json` was reconstructed from the first published
comment's fields; rendering the reconstructed JSON reproduced the comment
exactly. It is a captured observation, not a newly generated offline model run.

```sh
python3 scripts/evaluate_reviews.py \
  --scenario bad-live-global-interval \
  --review evals/observed-bad-review.json
```

The phrase-based evaluator detected all six expected issues, with no missed
issues or unmatched findings. Several issues can be covered by one finding.
This check does **not** establish factual accuracy of every sentence:

- The captured review incorrectly attributes Gradle's passing tests to Python.
  Gradle runs the existing Java tests; Python checks were run separately locally.
- It correctly identifies null unboxing as HTTP 500, but incorrectly claims that
  this failed assignment overwrites state. Unboxing throws before the field is
  assigned, so the previous value remains unchanged. The actual violation is
  HTTP 500 instead of the required HTTP 400.

These are review-quality limitations despite the correct verdict and issue
detection. JSON/schema validation verifies structure and supplied build status;
it does not prove semantic accuracy. Existing mocked tests additionally cover
stale-head rejection, comment updates, tool failures, and build-result mismatch.
No credentials or raw Kiro/build logs are stored in this report or fixture.
