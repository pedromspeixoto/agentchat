variable "region" {
  description = "AWS region to deploy resources into"
  type        = string
  default     = "eu-west-1"
}

variable "instance_type" {
  description = "EC2 instance type for the Firecracker orchestrator (must support bare-metal/KVM)"
  type        = string
  default     = "c5.metal"
}

variable "key_pair_name" {
  description = "Name of the AWS key pair for SSH access to the orchestrator instance"
  type        = string
}

variable "api_backend_cidr" {
  description = "CIDR block allowed to access the orchestrator API (port 8090) and SSH (port 22)"
  type        = string
}

variable "rootfs_s3_bucket" {
  description = "Name of the S3 bucket used to store Firecracker rootfs images"
  type        = string
}

variable "ssh_public_key" {
  description = "SSH public key material for the EC2 key pair"
  type        = string
}
