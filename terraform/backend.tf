terraform {
  backend "s3" {
    bucket         = "ai-log-deduper-tf-state-293012441360"
    key            = "state/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "ai-log-deduper-tf-locks"
    encrypt        = true
  }
}
