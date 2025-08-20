terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.4"
    }
  }
  
  backend "local" {}
}

provider "aws" {
  region = var.region
}

# Generate SSH key pair
resource "tls_private_key" "proxy_key" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "aws_key_pair" "proxy_key" {
  key_name   = "${var.project_name}-${var.region}-${var.deployment_uid}-key"
  public_key = tls_private_key.proxy_key.public_key_openssh
  
  tags = merge(
    var.tags,
    {
      Name    = "${var.project_name}-${var.region}-${var.deployment_uid}-key"
      Project = var.project_name
      Region  = var.region
    }
  )
}

# Save private key locally
resource "local_file" "private_key" {
  content         = tls_private_key.proxy_key.private_key_pem
  filename        = abspath("${path.module}/../../../state/${var.project_name}-${var.region}-${var.deployment_uid}-key.pem")
  file_permission = "0600"
}

# Create VPC
resource "aws_vpc" "proxy_vpc" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  
  tags = merge(
    var.tags,
    {
      Name    = "${var.project_name}-${var.region}-${var.deployment_uid}-vpc"
      Project = var.project_name
      Region  = var.region
    }
  )
}

# Create Internet Gateway
resource "aws_internet_gateway" "proxy_igw" {
  vpc_id = aws_vpc.proxy_vpc.id
  
  tags = merge(
    var.tags,
    {
      Name    = "${var.project_name}-${var.region}-${var.deployment_uid}-igw"
      Project = var.project_name
      Region  = var.region
    }
  )
}

# Create public subnet
resource "aws_subnet" "proxy_subnet" {
  vpc_id                  = aws_vpc.proxy_vpc.id
  cidr_block              = var.subnet_cidr
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true
  
  tags = merge(
    var.tags,
    {
      Name    = "${var.project_name}-${var.region}-${var.deployment_uid}-subnet"
      Project = var.project_name
      Region  = var.region
    }
  )
}

# Create route table
resource "aws_route_table" "proxy_rt" {
  vpc_id = aws_vpc.proxy_vpc.id
  
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.proxy_igw.id
  }
  
  tags = merge(
    var.tags,
    {
      Name    = "${var.project_name}-${var.region}-${var.deployment_uid}-rt"
      Project = var.project_name
      Region  = var.region
    }
  )
}

resource "aws_route_table_association" "proxy_rta" {
  subnet_id      = aws_subnet.proxy_subnet.id
  route_table_id = aws_route_table.proxy_rt.id
}

# Security group for WireGuard
resource "aws_security_group" "proxy_sg" {
  name        = "${var.project_name}-${var.region}-${var.deployment_uid}-sg"
  description = "Security group for WireGuard Proxy"
  vpc_id      = aws_vpc.proxy_vpc.id
  
  # SSH access
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.allowed_ips
  }
  
  # WireGuard UDP port
  ingress {
    from_port   = var.wireguard_port
    to_port     = var.wireguard_port
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  # Allow all outbound traffic
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = merge(
    var.tags,
    {
      Name    = "${var.project_name}-${var.region}-${var.deployment_uid}-sg"
      Project = var.project_name
      Region  = var.region
    }
  )
}

# Get latest Ubuntu AMI
data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical
  
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
  
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Create EC2 instance for Proxy server
resource "aws_instance" "proxy_server" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  key_name               = aws_key_pair.proxy_key.key_name
  subnet_id              = aws_subnet.proxy_subnet.id
  vpc_security_group_ids = [aws_security_group.proxy_sg.id]
  
  # Enable IP forwarding
  source_dest_check = false
  
  user_data = <<-EOF
    #!/bin/bash
    # Update package lists
    apt-get update
    
    # Install WireGuard and dependencies
    DEBIAN_FRONTEND=noninteractive apt-get install -y wireguard iptables python3-pip
    
    # Enable IP forwarding
    echo 'net.ipv4.ip_forward=1' >> /etc/sysctl.conf
    echo 'net.ipv6.conf.all.forwarding=1' >> /etc/sysctl.conf
    sysctl -p
    
    # Note: WireGuard configuration will be done via SSH after instance is ready
  EOF
  
  tags = merge(
    var.tags,
    {
      Name    = "${var.project_name}-${var.region}-${var.deployment_uid}-proxy"
      Project = var.project_name
      Region  = var.region
      Type    = "proxy-server"
    }
  )
  
  lifecycle {
    create_before_destroy = true
  }
}

# Elastic IP for consistent access
resource "aws_eip" "proxy_eip" {
  domain   = "vpc"
  instance = aws_instance.proxy_server.id
  
  tags = merge(
    var.tags,
    {
      Name    = "${var.project_name}-${var.region}-${var.deployment_uid}-eip"
      Project = var.project_name
      Region  = var.region
    }
  )
}

# CloudWatch monitoring
resource "aws_cloudwatch_metric_alarm" "proxy_cpu" {
  count               = var.monitoring_enabled ? 1 : 0
  alarm_name          = "${var.project_name}-${var.region}-${var.deployment_uid}-cpu-alarm"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = "120"
  statistic           = "Average"
  threshold           = "80"
  alarm_description   = "This metric monitors Proxy server CPU utilisation"
  
  dimensions = {
    InstanceId = aws_instance.proxy_server.id
  }
}

resource "aws_cloudwatch_metric_alarm" "proxy_status_check" {
  count               = var.monitoring_enabled ? 1 : 0
  alarm_name          = "${var.project_name}-${var.region}-status-alarm"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "StatusCheckFailed"
  namespace           = "AWS/EC2"
  period              = "60"
  statistic           = "Average"
  threshold           = "0"
  alarm_description   = "This metric monitors Proxy server status"
  
  dimensions = {
    InstanceId = aws_instance.proxy_server.id
  }
}