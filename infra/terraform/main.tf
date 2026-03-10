terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket = "firecracker-sandbox-tfstate"
    key    = "infra/terraform.tfstate"
    region = "eu-west-1"
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "firecracker-sandbox"
      ManagedBy = "terraform"
    }
  }
}
