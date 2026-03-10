data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_key_pair" "orchestrator" {
  key_name   = var.key_pair_name
  public_key = var.ssh_public_key

  tags = {
    Name = "firecracker-orchestrator-key"
  }
}

resource "aws_instance" "orchestrator" {
  ami                    = data.aws_ami.amazon_linux_2023.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.private.id
  vpc_security_group_ids = [aws_security_group.orchestrator.id]
  key_name               = aws_key_pair.orchestrator.key_name
  iam_instance_profile   = aws_iam_instance_profile.orchestrator.name

  root_block_device {
    volume_size = 200
    volume_type = "gp3"
    encrypted   = true
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  user_data = templatefile("${path.module}/templates/user-data.sh.tpl", {
    s3_bucket = var.rootfs_s3_bucket
    region    = var.region
  })

  tags = {
    Name = "firecracker-orchestrator"
  }
}
