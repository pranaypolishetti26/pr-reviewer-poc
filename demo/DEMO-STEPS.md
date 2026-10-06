# PR Reviewer POC — Demo Steps

## Goal

Create a pull request containing intentional problems, then ask the Kiro reviewer agent to detect them using:

- GitHub MCP for the PR and GitHub Issue
- Bedrock Knowledge Base MCP for project documentation

## 1. Push the baseline repository

Create a new GitHub repository and push this project to `main`.

## 2. Create the Knowledge Base

Upload `docs/knowledge-base/` to the S3 data source for your Bedrock Knowledge Base and sync it.

## 3. Create GitHub Issue #1

Create a GitHub Issue using `demo/GITHUB_ISSUE.md`.

## 4. Create the intentionally flawed PR

```bash
git checkout -b feature/1/global-polling-interval
git apply demo/demo-review.patch
git add .
git commit -m "feat: Add configurable global polling interval"
git push -u origin feature/1/global-polling-interval
```

Open a PR into `main`.

Suggested PR title:

```text
feat: Add configurable global polling interval
```

Suggested description:

```text
Implements #1.

Adds an API for updating the global polling interval.
```

## 5. Expected reviewer findings

A good reviewer should identify that the demo implementation:

1. stores mutable configuration directly in the controller
2. does not enforce the required 60–900 second range
3. allows invalid values instead of returning HTTP 400
4. has no service-layer implementation for the new configuration
5. adds no unit tests
6. adds no integration tests

## 6. Example Kiro review request

```text
Review pull request <PR_NUMBER> in <OWNER>/<REPO>.

Read the pull request changes and the linked GitHub issue.
Retrieve the relevant project requirements, architecture rules, and testing requirements from the project knowledge base.
Review the implementation only against that evidence.
Return a concise review with blocking issues clearly identified.
```
