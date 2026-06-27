variable "aws_region" {
  type        = string
  description = "AWS region to deploy resources"
  default     = "us-east-1"
}

variable "project_name" {
  type        = string
  description = "Prefix for resource naming to avoid collisions"
  default     = "ai-log-deduper"
}

variable "gemini_api_key" {
  type        = string
  description = "API key for Gemini analysis"
  sensitive   = true
}

variable "discord_webhook_url" {
  type        = string
  description = "Webhook URL to send alerts to Discord or Slack"
  sensitive   = true
}

variable "gateway_image" {
  type        = string
  description = "Docker image name for the FastAPI gateway"
  default     = "ghcr.io/cd-emman/ai-log-deduper-gateway:latest"
}

