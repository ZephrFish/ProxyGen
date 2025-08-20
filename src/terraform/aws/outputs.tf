output "public_ip" {
  description = "Public IP address of the Proxy server"
  value       = aws_eip.proxy_eip.public_ip
}

output "instance_id" {
  description = "Instance ID of the Proxy server"
  value       = aws_instance.proxy_server.id
}

output "private_key_path" {
  description = "Path to the private SSH key"
  value       = abspath(local_file.private_key.filename)
}

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.proxy_vpc.id
}

output "security_group_id" {
  description = "Security group ID"
  value       = aws_security_group.proxy_sg.id
}

output "region" {
  description = "AWS region"
  value       = var.region
}