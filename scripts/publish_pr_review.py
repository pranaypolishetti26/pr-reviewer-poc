"""Validate Kiro's review, then create or update the publisher's PR comment."""

import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MARKER = "<!-- kiro-pr-reviewer -->"


def log_event(event, exit_code=0):
    """Log only bounded metadata, never raw logs, model text, exceptions, or env dumps."""
    if event not in {"workflow_started", "checkout_completed", "build_completed",
                     "kiro_completed", "review_validated", "review_published", "workflow_finished",
                     "review_failed", "github_api_failed"}:
        event = "review_failed"
    pr = os.environ.get("PR_NUMBER", os.environ.get("CODEBUILD_WEBHOOK_TRIGGER", "").removeprefix("pr/"))
    sha = os.environ.get("PR_HEAD_SHA", "")
    gradle = os.environ.get("GRADLE_EXIT_CODE", "")
    stage = os.environ.get("WORKFLOW_STAGE", "")
    stage = stage if stage in ("checkout", "gradle", "kiro", "extract", "publish") else None
    record = {"event": event, "timestamp_epoch": time.time(),
              "pr_number": int(pr) if re.fullmatch(r"[1-9][0-9]{0,9}", pr) else None,
              "commit_sha": sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None,
              "stage": stage, "exit_code": exit_code,
              "build_status": ("PASS" if gradle == "0" else "FAIL") if gradle.isdigit() else "UNKNOWN",
              "test_status": "UNKNOWN", "review_verdict": None,
              "github_mcp_used": False, "knowledge_base_mcp_used": False,
              "jira_mcp_used": False, "repository_docs_mcp_used": False,
              "error": f"{stage or 'workflow'}_failed" if exit_code else None}
    for field, variable in (("duration_seconds", "REVIEW_STARTED_AT"),
                            ("stage_duration_seconds", "STAGE_STARTED_AT")):
        started = os.environ.get(variable, "")
        record[field] = max(0, round(time.time() - int(started), 3)) if started.isdigit() else None
    stream = Path(os.environ.get("KIRO_STREAM_PATH", "/tmp/pr-reviewer-kiro.jsonl"))
    calls = {}
    try:
        for line in stream.read_text().splitlines():
            try:
                item = json.loads(line)
                notification = item.get("params", item.get("data", item))
                update = notification.get("update", notification)
                if update.get("sessionUpdate") not in ("tool_call", "tool_call_update"):
                    continue
                call = calls.setdefault(update.get("toolCallId"), {})
                for key in ("name", "title", "status"):
                    if update.get(key):
                        call[key] = update[key]
                if isinstance(update.get("rawOutput"), dict) and update["rawOutput"].get("isError"):
                    call["status"] = "failed"
            except (ValueError, AttributeError, TypeError):
                continue
        names = [call.get("name", call.get("title", "")) for call in calls.values()
                 if call.get("status") == "completed"
                 and isinstance(call.get("name", call.get("title", "")), str)]
        record["github_mcp_used"] = any("pull_request_read" in name or "issue_read" in name for name in names)
        record["knowledge_base_mcp_used"] = any("ProjectDocsLambdaTarget___search_project_docs" in name for name in names)
        record["jira_mcp_used"] = any("jira_get_issue" in name for name in names)
        record["repository_docs_mcp_used"] = any("get_file_contents" in name for name in names)
    except OSError:
        pass
    try:
        review = json.loads(Path(os.environ.get("REVIEW_JSON", "/tmp/pr-reviewer-review.json")).read_text())
        validate_review(review, int(gradle), sha)
        record["review_verdict"] = review["verdict"]
        record["test_status"] = review["build_tests"]["test_result"]
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        pass
    if exit_code == 3:
        record["error"] = "STALE_REVIEW"
    print(json.dumps(record), file=sys.stderr, flush=True)


class StaleReviewError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def extract_review(stream_path, review_path):
    """Keep assistant text from ACP events; reject failed/unauthorized tool runs."""
    chunks = []
    tool_names = {}
    tool_statuses = {}
    completed_tools = set()
    tool_inputs = {}
    for line in Path(stream_path).read_text().splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        require(isinstance(event, dict), "Invalid Kiro stream event")
        require(event.get("type") != "runError", "REVIEW_TOOL_ERROR: Kiro reported a run error")
        require(not event.get("error"), "REVIEW_TOOL_ERROR: Kiro reported an error")
        require(event.get("method") != "session/request_permission",
                "REVIEW_TOOL_ERROR: tool requested unauthorized interactive permission")
        notification = event.get("params", event.get("data", event))
        result = notification.get("result", notification)
        if "stopReason" in result:
            require(result["stopReason"] == "end_turn", "REVIEW_FAILED: Kiro run did not complete")
        # Support Kiro's {type, data} stream envelope, JSON-RPC, and direct ACP.
        update = notification.get("update", notification)
        kind = update.get("sessionUpdate")
        if kind in ("tool_call", "tool_call_update"):
            if kind == "tool_call":
                # ACP streams progress messages too; only the final response is the review.
                chunks.clear()
            call_id = update.get("toolCallId")
            name = update.get("name") or update.get("title")
            if update.get("name") or (name and call_id not in tool_names):
                tool_names[call_id] = name
            if isinstance(update.get("rawInput"), dict):
                tool_inputs[call_id] = update["rawInput"]
            if "status" in update:
                tool_statuses[call_id] = update["status"]
            require(update.get("status") != "failed",
                    f'REVIEW_TOOL_ERROR: required tool failed: {update.get("name", update.get("toolCallId"))}')
            raw_output = update.get("rawOutput")
            require(not (isinstance(raw_output, dict) and raw_output.get("isError")),
                    "REVIEW_TOOL_ERROR: MCP returned an error")
            if update.get("status") == "completed":
                completed_tools.add(tool_names.get(call_id, ""))
        if kind == "agent_message_chunk":
            content = update.get("content", {})
            require(content.get("type") == "text", "Non-text Kiro review output")
            chunks.append(content["text"])
    require(bool(chunks), "REVIEW_FAILED: no assistant review in Kiro output")
    assistant_text = "".join(chunks)
    print(json.dumps({"event": "review_output_format", "assistant_chunks": len(chunks),
                      "starts_with_json": assistant_text.lstrip().startswith("{"),
                      "starts_with_fence": assistant_text.lstrip().startswith("```"),
                      "completed_tool_calls": len(completed_tools)}), file=sys.stderr)
    assistant_text = assistant_text.strip()
    # Kiro can add a short introduction even when asked for JSON only. Capture
    # one final JSON document; never repair JSON or accept text after the review.
    fenced = re.search(r"(?:^|\n)```json\n(.*)\n```$", assistant_text, re.DOTALL)
    if fenced:
        assistant_text = fenced.group(1)
    elif not assistant_text.startswith("{"):
        start = re.search(r"(?:^|\n)[ \t]*\{", assistant_text)
        require(start is not None, "REVIEW_FAILED: no final JSON document")
        assistant_text = assistant_text[start.start():].lstrip()
    review = json.loads(assistant_text)
    require(isinstance(review, dict), "Review must be a JSON object")
    require(not review.get("error"), f'REVIEW_FAILED: {review.get("error")}')
    require(all(status == "completed" for status in tool_statuses.values()),
            "REVIEW_TOOL_ERROR: required tool call did not complete")
    context_path = os.environ.get("REVIEW_CONTEXT_PATH")
    context = json.loads(Path(context_path).read_text()) if context_path else {
        "documentation_source": "knowledge-base", "jira_keys": [], "github_issue_linked": False}
    if context_path:
        require(review.get("head_sha") == context["head_sha"], "STALE_REVIEW: context SHA mismatch")
    required_tools = ["pull_request_read"]
    if context["documentation_source"] == "knowledge-base":
        required_tools.append("ProjectDocsLambdaTarget___search_project_docs")
    else:
        require(context["documentation_source"] == "repository", "Invalid documentation source")
        require(not any("ProjectDocsLambdaTarget___search_project_docs" in name for name in completed_tools),
                "REVIEW_TOOL_ERROR: unrelated Knowledge Base used for repository documentation")
        required_tools.append("get_file_contents")
    if context["jira_keys"]:
        required_tools.append("jira_get_issue")
    elif context["github_issue_linked"]:
        required_tools.append("issue_read")
    for required_tool in required_tools:
        require(any(required_tool in name for name in completed_tools),
                f"REVIEW_TOOL_ERROR: no successful call to required tool {required_tool}")
    def completed_inputs(tool):
        return [tool_inputs.get(call_id, {}) for call_id, name in tool_names.items()
                if tool in name and tool_statuses.get(call_id) == "completed"]
    for key in context["jira_keys"]:
        require(any(args.get("issue_key") == key
                    for args in completed_inputs("jira_get_issue")),
                f"REVIEW_TOOL_ERROR: no successful Jira read for {key}")
    for path in context.get("documentation_paths", []):
        require(any(args.get("path") == path and args.get("ref") == context["head_sha"]
                    for args in completed_inputs("get_file_contents")),
                f"REVIEW_TOOL_ERROR: no successful pinned documentation read for {path}")
    Path(review_path).write_text(json.dumps(review) + "\n")


def validate_review(review, gradle_exit_code, expected_sha):
    require(isinstance(review, dict), "Review must be a JSON object")
    require(review.get("head_sha") == expected_sha, "Review head SHA does not match the checkout")
    require(review.get("verdict") in ("APPROVE", "NEEDS_CHANGES"), "Invalid verdict")
    build = review.get("build_tests")
    require(isinstance(build, dict), "Missing build_tests object")
    require(build.get("command") == os.environ.get("REVIEW_BUILD_COMMAND", "gradle clean build"),
            "Incorrect build command")
    require(type(build.get("exit_code")) is int and build["exit_code"] == gradle_exit_code,
            "Build exit code does not match CodeBuild")
    require(build.get("build_result") == ("PASS" if gradle_exit_code == 0 else "FAIL"),
            "Build result does not match CodeBuild")
    require(build.get("test_result") in ("PASS", "FAIL", "NOT_RUN", "UNKNOWN"),
            "Invalid test result")
    require(text(build.get("details")), "Missing build/test details")
    alignment = review.get("requirement_alignment")
    require(isinstance(alignment, dict), "Missing requirement_alignment object")
    require(all(text(alignment.get(key)) for key in ("requested", "implemented")),
            "Missing requirement alignment details")
    require(alignment.get("match") in ("YES", "NO", "UNVERIFIED"), "Invalid alignment match")
    require(text(review.get("test_coverage")), "Missing test coverage summary")
    findings = review.get("findings")
    require(isinstance(findings, list), "Findings must be an array")
    for finding in findings:
        require(isinstance(finding, dict), "Each finding must be an object")
        require(finding.get("severity") in ("BLOCKING", "INFO"), "Invalid finding severity")
        require(all(text(finding.get(key)) for key in
                    ("title", "requirement", "implementation", "why_it_matters")),
                "Missing finding details")
        require(isinstance(finding.get("file"), str), "Finding file must be a string")
    evidence = review.get("evidence")
    require(isinstance(evidence, list) and bool(evidence) and all(text(item) for item in evidence),
            "Evidence must be a nonempty array of strings")
    blocking = (gradle_exit_code != 0 or build["test_result"] == "FAIL"
                or alignment["match"] == "NO"
                or any(f["severity"] == "BLOCKING" for f in findings))
    require(not blocking or review["verdict"] == "NEEDS_CHANGES",
            "APPROVE contradicts blocking findings or failed build/tests")


def render_comment(review):
    build = review["build_tests"]
    alignment = review["requirement_alignment"]
    lines = [MARKER, "## Kiro PR Review", "", f'**Verdict:** {review["verdict"]}',
             f'Reviewed commit: `{review["head_sha"]}`', "",
             "### Build & Tests", f'- Command: `{build["command"]}` (run by CodeBuild)',
             f'- Exit code: {build["exit_code"]}', f'- Build: {build["build_result"]}',
             f'- Tests: {build["test_result"]}', f'- Details: {build["details"]}', "",
             "### Requirement Alignment", f'- What was requested: {alignment["requested"]}',
             f'- What was implemented: {alignment["implemented"]}',
             f'- Match: {alignment["match"]}', "", "### Test Coverage",
             review["test_coverage"], "", "### Findings"]
    for index, finding in enumerate(review["findings"], 1):
        lines.extend([f'{index}. **[{finding["severity"]}] {finding["title"]}**',
                      f'   - Requirement: {finding["requirement"]}',
                      f'   - Implementation: {finding["implementation"]}',
                      f'   - Why it matters: {finding["why_it_matters"]}',
                      f'   - File: {finding["file"] or "N/A"}'])
    if not review["findings"]:
        lines.append("No findings.")
    lines.extend(["", "### Evidence Checked", *[f"- {item}" for item in review["evidence"]]])
    body = "\n".join(lines)
    require(len(body) <= 65536, "Review exceeds GitHub comment size limit")
    return body


def github_request(method, path, token, payload=None):
    request = Request("https://api.github.com" + path, method=method,
                      data=json.dumps(payload).encode() if payload is not None else None,
                      headers={"Authorization": f"Bearer {token}",
                               "Accept": "application/vnd.github+json",
                               "Content-Type": "application/json",
                               "X-GitHub-Api-Version": "2026-03-10"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def get_head_sha(repository, pr_number, token):
    sha = github_request("GET", f"/repos/{repository}/pulls/{pr_number}", token)["head"]["sha"]
    require(isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha), "Invalid PR head SHA")
    return sha


def publish_comment(repository, pr_number, token, body, expected_sha):
    author_id = github_request("GET", "/user", token)["id"]
    comments_path = f"/repos/{repository}/issues/{pr_number}/comments"
    page = 1
    comment_id = None
    while True:
        comments = github_request("GET", f"{comments_path}?per_page=100&page={page}", token)
        for comment in comments:
            existing_body = comment.get("body") or ""
            # Also migrate comments created by the earlier workflow, without a marker.
            if comment["user"]["id"] == author_id and (
                existing_body.startswith(MARKER)
                or existing_body.startswith("## Kiro PR Review\n")
            ):
                comment_id = comment["id"]
                break
        if comment_id is not None or len(comments) < 100:
            break
        page += 1
    # Check after comment discovery, immediately before either GitHub write.
    current_sha = get_head_sha(repository, pr_number, token)
    if current_sha != expected_sha:
        raise StaleReviewError(
            f"STALE_REVIEW: reviewed {expected_sha}, current PR head is {current_sha}; "
            "review discarded, no comment posted or updated")
    if comment_id is not None:
        return github_request("PATCH", f"/repos/{repository}/issues/comments/{comment_id}",
                              token, {"body": body})
    return github_request("POST", comments_path, token, {"body": body})


def main():
    if sys.argv[1] == "--log-event":
        log_event(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 0)
        return
    if sys.argv[1] == "--extract-review":
        extract_review(sys.argv[2], sys.argv[3])
        return
    repository = os.environ["GITHUB_REPOSITORY"]
    pr_number = os.environ["PR_NUMBER"]
    require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository), "Invalid repository")
    require(re.fullmatch(r"[1-9][0-9]*", pr_number), "Invalid PR number")
    token = os.environ["GITHUB_PERSONAL_ACCESS_TOKEN"]
    if sys.argv[1] == "--head-sha":
        print(get_head_sha(repository, pr_number, token))
        return
    review_path = Path(sys.argv[1])
    review = json.loads(review_path.read_text())
    expected_sha = sys.argv[3]
    require(re.fullmatch(r"[0-9a-f]{40}", expected_sha), "Invalid saved head SHA")
    validate_review(review, int(sys.argv[2]), expected_sha)
    body = render_comment(review)
    log_event("review_validated")
    try:
        result = publish_comment(repository, pr_number, token, body, expected_sha)
    except StaleReviewError:
        review_path.unlink(missing_ok=True)
        raise
    log_event("review_published")


if __name__ == "__main__":
    try:
        main()
    except StaleReviewError as error:
        log_event("review_failed", 3)
        sys.exit(3)
    except HTTPError as error:
        log_event("github_api_failed", error.code)
        sys.exit(1)
    except (ValueError, KeyError, OSError, URLError, IndexError, TypeError, AttributeError) as error:
        category = "invalid_json" if isinstance(error, json.JSONDecodeError) else type(error).__name__
        if isinstance(error, ValueError) and str(error).startswith("REVIEW_TOOL_ERROR"):
            category = "required_tool_failed"
        print(json.dumps({"event": "review_error_category", "category": category}), file=sys.stderr)
        log_event("review_failed", 1)
        sys.exit(1)
