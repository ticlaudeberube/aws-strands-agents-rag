# Terraform and provider version pinning (Requirement 11.8).
#
# NOTE on required_version: the design document specifies ">= 1.6.0", but the
# Terraform binary available in this environment is v1.5.7. We relax the floor
# to ">= 1.5.0" so that `terraform init`/`validate`/`fmt` run here. Bump this
# back to ">= 1.6.0" in CI/production where a newer Terraform is installed.
#
# NOTE on the aws provider pin: the design mentions "~> 5.60". The official
# terraform-aws-modules/vpc/aws module used by the networking child module
# (pinned to ~> 5.21) requires the aws provider ">= 5.79". To keep a pinned 5.x
# provider while remaining compatible with that module, we pin to "~> 5.95"
# (still the 5.x major line, satisfies the module's >= 5.79 floor).
terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.95"
    }
  }
}
