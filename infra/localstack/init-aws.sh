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

aws $ENDPOINT dynamodb create-table \
  --table-name modelforge-jobs \
  --attribute-definitions AttributeName=pk,AttributeType=S AttributeName=sk,AttributeType=S \
  --key-schema AttributeName=pk,KeyType=HASH AttributeName=sk,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST

echo "modelforge: LocalStack init complete (buckets, queues + DLQs, table)."
