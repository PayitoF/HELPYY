#!/bin/bash
# Deploy Helpyy Hand to AWS via CDK.
set -e

echo "Running tests before deploy..."
make test

echo "Deploying infrastructure..."
cd infra/aws/cdk
cdk deploy --all --require-approval broadening

echo "Deploy complete."
