#!/usr/bin/env bash
set -euo pipefail

export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1

ENDPOINT="--endpoint-url=http://localhost:4566"

aws $ENDPOINT s3 mb s3://mf-uploads
aws $ENDPOINT s3 mb s3://mf-results

for dlq in cpu-jobs-dlq gpu-jobs-dlq; do
  aws $ENDPOINT sqs create-queue --queue-name "$dlq"
done

cpu_dlq_arn=$(aws $ENDPOINT sqs get-queue-attributes \
  --queue-url "http://localhost:4566/000000000000/cpu-jobs-dlq" \
  --attribute-names QueueArn --query "Attributes.QueueArn" --output text)
gpu_dlq_arn=$(aws $ENDPOINT sqs get-queue-attributes \
  --queue-url "http://localhost:4566/000000000000/gpu-jobs-dlq" \
  --attribute-names QueueArn --query "Attributes.QueueArn" --output text)

aws $ENDPOINT sqs create-queue --queue-name cpu-jobs --attributes "{
  \"RedrivePolicy\": \"{\\\"deadLetterTargetArn\\\":\\\"${cpu_dlq_arn}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"
}"
aws $ENDPOINT sqs create-queue --queue-name gpu-jobs --attributes "{
  \"RedrivePolicy\": \"{\\\"deadLetterTargetArn\\\":\\\"${gpu_dlq_arn}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"
}"

# Single table for Users, Models, Datasets, Jobs, JobEvents and Usage counters.
# See docs/decisions.md ("Day 7: Single-table DynamoDB schema") for the access patterns
# behind this key design.
aws $ENDPOINT dynamodb create-table \
  --table-name modelforge \
  --attribute-definitions \
      AttributeName=PK,AttributeType=S \
      AttributeName=SK,AttributeType=S \
      AttributeName=GSI1PK,AttributeType=S \
      AttributeName=GSI1SK,AttributeType=S \
  --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
  --global-secondary-indexes \
      "[{\"IndexName\":\"GSI1\",\"KeySchema\":[{\"AttributeName\":\"GSI1PK\",\"KeyType\":\"HASH\"},{\"AttributeName\":\"GSI1SK\",\"KeyType\":\"RANGE\"}],\"Projection\":{\"ProjectionType\":\"ALL\"}}]" \
  --billing-mode PAY_PER_REQUEST

aws $ENDPOINT dynamodb wait table-exists --table-name modelforge
aws $ENDPOINT dynamodb update-time-to-live \
  --table-name modelforge \
  --time-to-live-specification "Enabled=true,AttributeName=ttl"

# KMS key for envelope-encrypting the user's optional Hugging Face token.
aws $ENDPOINT kms create-key --description "modelforge hf-token key"

echo "modelforge: LocalStack init complete (buckets, queues + DLQs, table + GSI1 + TTL, KMS key)."
