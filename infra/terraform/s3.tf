resource "aws_s3_bucket" "rootfs" {
  bucket = var.rootfs_s3_bucket

  tags = {
    Name = "firecracker-rootfs-bucket"
  }
}

resource "aws_s3_bucket_versioning" "rootfs" {
  bucket = aws_s3_bucket.rootfs.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "rootfs" {
  bucket = aws_s3_bucket.rootfs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "rootfs" {
  bucket = aws_s3_bucket.rootfs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
