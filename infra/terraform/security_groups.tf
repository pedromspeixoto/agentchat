resource "aws_security_group" "orchestrator" {
  name        = "firecracker-orchestrator-sg"
  description = "Security group for the Firecracker orchestrator instance"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "firecracker-orchestrator-sg"
  }
}

resource "aws_vpc_security_group_ingress_rule" "orchestrator_api" {
  security_group_id = aws_security_group.orchestrator.id
  description       = "Allow orchestrator API access from backend CIDR"
  cidr_ipv4         = var.api_backend_cidr
  from_port         = 8090
  to_port           = 8090
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "orchestrator_ssh" {
  security_group_id = aws_security_group.orchestrator.id
  description       = "Allow SSH access from backend CIDR"
  cidr_ipv4         = var.api_backend_cidr
  from_port         = 22
  to_port           = 22
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "orchestrator_all" {
  security_group_id = aws_security_group.orchestrator.id
  description       = "Allow all outbound traffic"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}
