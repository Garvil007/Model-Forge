#!/usr/bin/env bash
set -euo pipefail

export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1

ENDPOINT="--endpoint-url=http://localhost:4566"

aws $ENDPOINT s3 mb s3://mf-uploads
aws $ENDPOINT s3 mb s3://mf-results

# CORS + lifecycle for both buckets, built from infra/storage_rules.json (also read by
# StorageStack — see docs/decisions.md on keeping dev/prod rules from drifting apart).
for bucket in mf-uploads mf-results; do
  aws $ENDPOINT s3api put-bucket-cors --bucket "$bucket" --cors-configuration '{
    "CORSRules": [{
      "AllowedMethods": ["PUT", "GET", "HEAD"],
      "AllowedOrigins": ["http://localhost:5173", "http://localhost:4173"],
      "AllowedHeaders": ["*"],
      "ExposeHeaders": ["ETag"],
      "MaxAgeSeconds": 3000
    }]
  }'
  aws $ENDPOINT s3api put-bucket-lifecycle-configuration --bucket "$bucket" --lifecycle-configuration '{
    "Rules": [
      {"ID": "expire-retention-7d", "Status": "Enabled", "Filter": {"Tag": {"Key": "retention", "Value": "7d"}}, "Expiration": {"Days": 7}},
      {"ID": "expire-retention-30d", "Status": "Enabled", "Filter": {"Tag": {"Key": "retention", "Value": "30d"}}, "Expiration": {"Days": 30}},
      {"ID": "expire-untagged-catch-all", "Status": "Enabled", "Filter": {"Prefix": "users/"}, "Expiration": {"Days": 30}},
      {"ID": "abort-incomplete-multipart", "Status": "Enabled", "Filter": {"Prefix": ""}, "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1}}
    ]
  }'
done
# Note: LocalStack accepts and stores these rules but does not actually expire objects on
# a timer — verify them with get-bucket-lifecycle-configuration, not by waiting.

for dlq in cpu-jobs-dlq gpu-jobs-dlq system-jobs-dlq; do
  aws $ENDPOINT sqs create-queue --queue-name "$dlq"
done

cpu_dlq_arn=$(aws $ENDPOINT sqs get-queue-attributes \
  --queue-url "http://localhost:4566/000000000000/cpu-jobs-dlq" \
  --attribute-names QueueArn --query "Attributes.QueueArn" --output text)
gpu_dlq_arn=$(aws $ENDPOINT sqs get-queue-attributes \
  --queue-url "http://localhost:4566/000000000000/gpu-jobs-dlq" \
  --attribute-names QueueArn --query "Attributes.QueueArn" --output text)
system_dlq_arn=$(aws $ENDPOINT sqs get-queue-attributes \
  --queue-url "http://localhost:4566/000000000000/system-jobs-dlq" \
  --attribute-names QueueArn --query "Attributes.QueueArn" --output text)

aws $ENDPOINT sqs create-queue --queue-name cpu-jobs --attributes "{
  \"RedrivePolicy\": \"{\\\"deadLetterTargetArn\\\":\\\"${cpu_dlq_arn}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"
}"
aws $ENDPOINT sqs create-queue --queue-name gpu-jobs --attributes "{
  \"RedrivePolicy\": \"{\\\"deadLetterTargetArn\\\":\\\"${gpu_dlq_arn}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"
}"
aws $ENDPOINT sqs create-queue --queue-name system-jobs --attributes "{
  \"RedrivePolicy\": \"{\\\"deadLetterTargetArn\\\":\\\"${system_dlq_arn}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"
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
