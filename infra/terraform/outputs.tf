output "orchestrator_url" {
  description = "URL of the Firecracker orchestrator API"
  value       = "http://${aws_instance.orchestrator.private_ip}:8090"
}

output "instance_id" {
  description = "EC2 instance ID of the orchestrator"
  value       = aws_instance.orchestrator.id
}

output "bucket_name" {
  description = "Name of the S3 bucket storing rootfs images"
  value       = aws_s3_bucket.rootfs.id
}

output "private_ip" {
  description = "Private IP address of the orchestrator instance"
  value       = aws_instance.orchestrator.private_ip
}
