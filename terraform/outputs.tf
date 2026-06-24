output "sqs_queue_url" {
  value       = aws_sqs_queue.queue.url
  description = "The URL of the SQS log ingestion queue"
}

output "sqs_queue_arn" {
  value       = aws_sqs_queue.queue.arn
  description = "The ARN of the SQS log ingestion queue"
}

output "dynamodb_table_name" {
  value       = aws_dynamodb_table.table.name
  description = "The name of the DynamoDB fingerprints table"
}

output "lambda_function_arn" {
  value       = aws_lambda_function.processor.arn
  description = "The ARN of the Lambda log processor"
}

output "sqs_dlq_url" {
  value       = aws_sqs_queue.dlq.url
  description = "The URL of the SQS dead letter queue"
}

output "sqs_dlq_arn" {
  value       = aws_sqs_queue.dlq.arn
  description = "The ARN of the SQS dead letter queue"
}

