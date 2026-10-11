def lambda_handler(event, context):

    pr_number = event["pr_number"]

    return {
        "pr_number": pr_number,
        "title": "Add Cognito authentication",
        "author": "Pranay",
        "files_changed": [
            "src/security/CognitoConfig.java",
            "src/controllers/CustomerController.java"
        ],
        "description": "Adds Cognito authentication to customer APIs."
    }
