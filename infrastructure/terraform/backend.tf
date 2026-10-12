# Remote state backend (Requirement 11.7).
#
# Terraform state is stored in an S3 bucket and locked via a DynamoDB table so
# that concurrent team runs are safe. The bucket and lock table are created once
# as a bootstrap step (separate configuration) BEFORE this configuration is
# initialised against the real backend.
#
# For local validation without AWS credentials or a real backend, initialise
# with:  terraform init -backend=false
terraform {
  backend "s3" {
    bucket         = "strands-rag-tfstate"
    key            = "serverless-deployment/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "strands-rag-tflock"
    encrypt        = true
  }
}
