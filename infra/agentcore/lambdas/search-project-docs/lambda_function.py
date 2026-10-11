import os
import boto3

kb = boto3.client(
    "bedrock-agent-runtime",
    region_name="us-east-2"
)

KNOWLEDGE_BASE_ID = os.environ["KNOWLEDGE_BASE_ID"]


def lambda_handler(event, context):
    query = event["query"]

    response = kb.retrieve(
        knowledgeBaseId=KNOWLEDGE_BASE_ID,
        retrievalQuery={
            "text": query
        },
        retrievalConfiguration={
            "vectorSearchConfiguration": {
                "numberOfResults": 3
            }
        }
    )

    return {
        "matches": [
            {
                "text": result["content"]["text"],
                "score": result.get("score")
            }
            for result in response["retrievalResults"]
        ]
    }
