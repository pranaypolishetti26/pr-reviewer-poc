# PR Reviewer AgentCore infrastructure

The reviewer workflow, Gateway configuration, tool schemas, and Lambda source are now maintained in this repository. This project was copied from `pranaypolishetti26/aws-practice` at commit `0f58005978dfa64a9d00453db8ad1c525ce077ee`; that repository was left unchanged. The imported configuration was reconciled with the existing deployment on October 11, 2026.

## Files

| Path | Purpose |
| --- | --- |
| [agentcore/agentcore.json](agentcore/agentcore.json) | Gateway specification, including both existing Lambda targets |
| [agentcore/aws-targets.json](agentcore/aws-targets.json) | Existing account and deployment region |
| [agentcore/cdk](agentcore/cdk) | Original generated CDK project and pinned dependency lockfile |
| [agentcore/.cli/deployed-state.json](agentcore/.cli/deployed-state.json) | Existing gateway URL, target IDs, stack identity, and historical deploy hash |
| [agentcore/.llm-context](agentcore/.llm-context) | Reference types for editing the declarative configuration |
| [tools.json](tools.json) | Existing `get_pull_request` tool schema |
| [project-docs-tools.json](project-docs-tools.json) | Exact deployed `search_project_docs` tool schema |
| [lambdas/search-project-docs/lambda_function.py](lambdas/search-project-docs/lambda_function.py) | Source captured from the deployed documentation Lambda |
| [lambdas/get-pull-request/lambda_function.py](lambdas/get-pull-request/lambda_function.py) | Source captured from the original mock PR Lambda |
| [existing-resources.json](existing-resources.json) | Read-only inventory of resource IDs, Lambda settings, Knowledge Base configuration, and CloudFormation ownership |

The learning repository's unrelated Bedrock experiments were not imported. Its older Knowledge Base ID is not used by the active reviewer.

## Resource ownership

The existing stack is `AgentCore-PRReviewAgentcore-default` in account `018724218019`, region `us-east-2`. Project name `PRReviewAgentcore`, gateway name `PRReviewGateway`, construct IDs, and target names are preserved. Moving the directory does not move or recreate AWS resources.

| Resource | How it is maintained |
| --- | --- |
| Gateway, gateway execution role/policy, both Gateway targets | Existing CloudFormation stack; declared by the CDK project here |
| `search-project-docs` and `get-pull-request` Lambdas | Existing functions referenced by ARN; captured source is available here, but CDK does not create or update their code |
| Knowledge Base `UW6ENMRRLS`, data source `5H1O8QTP3N`, S3 document bucket/prefix, S3 Vectors index, and their roles | Existing external resources recorded in the inventory; not created, imported into CloudFormation, or re-ingested by this project |
| CodeBuild, Secrets Manager, docs-sync role | Existing reviewer infrastructure; described in the root README and sync guide |

The original saved configuration omitted `ProjectDocsLambdaTarget`; the consolidated specification includes it and its existing target ID `KOL1ZTCAMX`. CloudFormation inspection confirmed that both targets are already owned by the existing stack, so adding its missing source declaration does not require resource adoption.

Offline synthesis was compared with the deployed template: all five functional resources have the same logical IDs and definitions, with no added or removed resources. Only `AWS::CDK::Metadata` differs. The tool schema files preserve deployed asset contents so their S3 asset references also remain unchanged. This comparison is a point-in-time check, not a guarantee about future edits.

The CLI deploy hash is historical state copied from the source project; it is not proof that today's source has been deployed. The resource inventory is a snapshot, not a deployment manifest or backup of document content. No secrets, signed download URLs, model credentials, document chunks, or vector data are included.

## Validate locally

Use Node.js 20 or newer and the committed lockfile. From this repository root:

```sh
cd infra/agentcore/agentcore/cdk
npm ci --ignore-scripts --no-audit --no-fund
npm run build
npm test -- --runInBand
npm run cdk -- synth --no-lookups --quiet
```

Run these commands from the CDK directory: the generated project discovers its configuration relative to that working directory. Synthesis writes ignored local artifacts under `cdk.out`; it does not deploy, upload schemas, invoke a Lambda/model, or start Knowledge Base ingestion. The migration test verifies deployed logical IDs, both target names and Lambda ARNs, and the absence of newly created Lambda, Knowledge Base, or S3 bucket resources.

The AgentCore CLI is optional for these checks and was not installed in the migration environment. When installed separately, its project commands run from `infra/agentcore`; the existing generated schema and CDK layout are retained.

## Inspect the existing deployment

```sh
aws bedrock-agentcore-control get-gateway \
  --gateway-identifier prreviewagentcore-prreviewgateway-6tdiyooexa \
  --region us-east-2

aws bedrock-agentcore-control list-gateway-targets \
  --gateway-identifier prreviewagentcore-prreviewgateway-6tdiyooexa \
  --region us-east-2

aws cloudformation list-stack-resources \
  --stack-name AgentCore-PRReviewAgentcore-default \
  --region us-east-2
```

Future infrastructure edits can be assessed with `npm run cdk -- diff --change-set false` from the CDK directory. It reads the deployed template without creating a change set. Deployment is a separate operation through the existing stack; it is not needed to use the reviewer after this source migration. Keep resource names stable and inspect the proposed changes before deployment.

## Lambda maintenance

`search-project-docs` uses `KNOWLEDGE_BASE_ID=UW6ENMRRLS`, calls Bedrock Retrieve for three results, and returns their text and scores. It does not currently return source filenames or locations. The exported implementation and current runtime, handler, memory, timeout, role ARN, and code hashes are recorded locally.

`get-pull-request` returns a fixed mock PR payload. It is retained because it is an existing Gateway target; the active reviewer disables it and reads real PRs through GitHub MCP.

Editing these source files does not deploy them. Any later Lambda update must package the relevant `lambda_function.py`, target the existing function name, and preserve its required settings. Boto3 is provided by the documentation function's AWS Python runtime. The imported CDK project intentionally references existing function ARNs instead of creating duplicate functions or claiming ownership of their code.

## Review and document workflows

The existing [.kiro MCP configuration](../../.kiro/settings/mcp.json) continues to use the same live Gateway endpoint. CodeBuild and its reviewer do not need another deployment or endpoint change. Fineract reviews use Jira and pinned repository files, with this Knowledge Base connection removed from their runtime configuration.

Only changes to `docs/knowledge-base/**` on `main` trigger the separate document-sync workflow. The infrastructure migration does not change that directory, upload/synchronize document content, or start ingestion. The root [README](../../README.md) describes the full reviewer flow; [the sync guide](../../docs/knowledge-base-sync.md) describes the existing document pipeline.
