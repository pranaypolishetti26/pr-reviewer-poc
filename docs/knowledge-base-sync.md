# Automatic project documentation synchronization

The separate `.github/workflows/sync-knowledge-base.yml` workflow runs on pushes
to `main` that change `docs/knowledge-base/**`, including merges and deletions.
It never runs on PR events. Protect `main` with required PR reviews if all main
changes must be merged through a PR rather than pushed directly.

The workflow checks out latest `main`, serializes runs without cancelling an
active sync, mirrors documents with `aws s3 sync --delete`, and waits for ingestion
to complete. Queued runs therefore cannot overwrite newer docs with an older
event checkout. The existing CodeBuild buildspec and PR reviewer are untouched.

Bedrock's standard ingestion job is incremental: it processes added, modified,
and deleted documents since the previous sync. See [AWS synchronization docs](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-sync.html).

## Repository variables

The workflow environment defaults to this POC's verified existing resources:
bucket `project-docs-018724218019-us-east-2-an`, Knowledge Base `UW6ENMRRLS`, data
source `5H1O8QTP3N`, prefix `customer-preferences-service/`, and sync role
`arn:aws:iam::018724218019:role/pr-reviewer-docs-sync`. These are resource
identifiers, not credentials. AWS authentication uses short-lived OIDC credentials.
The dedicated sync role and OIDC provider were configured for the live test.

Override them when needed under **Settings → Secrets and variables → Actions → Variables**:

| Variable | Value |
| --- | --- |
| `S3_BUCKET` | Existing S3 bucket name, without `s3://` |
| `KNOWLEDGE_BASE_ID` | Existing Bedrock Knowledge Base ID |
| `DATA_SOURCE_ID` | Existing S3 data source ID within that Knowledge Base |
| `AWS_DOCS_SYNC_ROLE_ARN` | IAM role assumed by GitHub Actions using OIDC |
| `S3_PREFIX` | Existing dedicated document prefix; this POC uses `customer-preferences-service/` |

All AWS calls use `us-east-2`. The script checks the existing data source's bucket
and inclusion prefixes before writing to S3. It does not create or modify AWS
resources or the data source configuration.

Set `S3_PREFIX` to the location where the documents are already stored and that
the data source indexes. **The repository docs folder owns every object under
this prefix**: `--delete` removes objects that are absent locally, so use a
dedicated prefix. If the existing bucket root holds only these docs, explicitly
set `S3_PREFIX` to `/` and adjust the IAM object/list scopes below to the bucket
root. Do not select bucket root when it contains unrelated objects.

If the last document is deleted, an empty directory is synchronized to remove
the remaining S3 documents. Symlinked files are not uploaded. No PR credentials
or Kiro authentication is needed for this workflow.

## AWS IAM prerequisites

Reuse an existing deployment role if appropriate. Add a GitHub OIDC trust
statement; preserve its other required trust statements. Do not replace the
CodeBuild service role's existing trust or policy.

The account must have the IAM OIDC provider
`https://token.actions.githubusercontent.com`, with audience `sts.amazonaws.com`.
See [GitHub's AWS OIDC guide](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws).

Example trust statement (replace `ACCOUNT_ID` and `EXACT_MAIN_BRANCH_SUBJECT`):

```json
{
  "Effect": "Allow",
  "Principal": {
    "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
  },
  "Action": "sts:AssumeRoleWithWebIdentity",
  "Condition": {
    "StringEquals": {
      "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
      "token.actions.githubusercontent.com:sub": "EXACT_MAIN_BRANCH_SUBJECT"
    }
  }
}
```

For the traditional GitHub subject format, the subject is
`repo:pranaypolishetti26/pr-reviewer-poc:ref:refs/heads/main`. Repositories using
GitHub's immutable subject format must include their owner/repository IDs, as
described in the linked guide. Match your repository's actual subject exactly;
do not allow feature branches or PR merge refs.

Attach this permissions policy to the sync role, replacing placeholders and
adjusting `docs/knowledge-base/` to the actual document prefix:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::BUCKET_NAME",
      "Condition": {
        "StringLike": { "s3:prefix": ["docs/knowledge-base/", "docs/knowledge-base/*"] }
      }
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::BUCKET_NAME/docs/knowledge-base/*"
    },
    {
      "Effect": "Allow",
      "Action": ["bedrock:GetDataSource", "bedrock:StartIngestionJob", "bedrock:GetIngestionJob"],
      "Resource": "arn:aws:bedrock:us-east-2:ACCOUNT_ID:knowledge-base/KNOWLEDGE_BASE_ID"
    }
  ]
}
```

If the bucket uses a customer-managed KMS key, grant the sync role
`kms:GenerateDataKey` and `kms:Decrypt` on that key and allow the role in the key
policy. The existing Bedrock Knowledge Base service role must retain S3 read,
KMS decrypt (if applicable), embedding model, and vector store permissions.
If it previously allowed a different S3 prefix, include the chosen prefix in its
S3 permissions and the bucket policy. No vector store permissions are needed by
the GitHub sync role.

## Logs and reruns

The script emits JSON status events for S3 synchronization, ingestion start,
progress, completion, and failure, including stage, job ID, and duration.
It suppresses raw AWS CLI output and credentials. A failed S3 sync prevents
ingestion from starting. Failed/stopped ingestion, document ingestion failures,
or a 20-minute ingestion timeout fail the workflow. Authentication/setup failures
are visible in their separate GitHub Actions steps.

Rerun a failed main-branch workflow after fixing configuration or permissions.
If another ingestion job is already running outside this workflow, starting a
new job may fail; wait for it to finish before rerunning. S3 changes and ingestion
are separate operations, so an ingestion failure can leave S3 updated while the
Knowledge Base still needs synchronization. A rerun syncs the latest main again
and starts another incremental ingestion job. A timeout does not stop Bedrock's
job; check its status before rerunning.

Run local mocked checks without contacting AWS:

```sh
python3 -m unittest discover -s tests -p 'test_sync_knowledge_base.py'
```
