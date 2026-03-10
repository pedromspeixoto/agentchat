data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "orchestrator" {
  name               = "firecracker-orchestrator-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json

  tags = {
    Name = "firecracker-orchestrator-role"
  }
}

data "aws_iam_policy_document" "s3_read_rootfs" {
  statement {
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
    ]

    resources = [
      aws_s3_bucket.rootfs.arn,
      "${aws_s3_bucket.rootfs.arn}/*",
    ]
  }
}

resource "aws_iam_policy" "s3_read_rootfs" {
  name        = "firecracker-s3-read-rootfs"
  description = "Allow read access to the Firecracker rootfs S3 bucket"
  policy      = data.aws_iam_policy_document.s3_read_rootfs.json

  tags = {
    Name = "firecracker-s3-read-rootfs"
  }
}

resource "aws_iam_role_policy_attachment" "orchestrator_s3" {
  role       = aws_iam_role.orchestrator.name
  policy_arn = aws_iam_policy.s3_read_rootfs.arn
}

resource "aws_iam_instance_profile" "orchestrator" {
  name = "firecracker-orchestrator-profile"
  role = aws_iam_role.orchestrator.name

  tags = {
    Name = "firecracker-orchestrator-profile"
  }
}
