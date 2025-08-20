output "instance_id" {
  description = "ID of the DigitalOcean droplet"
  value       = digitalocean_droplet.proxy.id
}

output "public_ip" {
  description = "Public IP address of the Proxy server"
  value       = digitalocean_floating_ip.proxy_ip.ip_address
}

output "private_ip" {
  description = "Private IP address of the Proxy server"
  value       = digitalocean_droplet.proxy.ipv4_address_private
}

output "private_key_path" {
  description = "Path to the SSH private key"
  value       = abspath(local_file.private_key.filename)
}

output "region" {
  description = "DigitalOcean region"
  value       = var.region
}

output "instance_type" {
  description = "Droplet size"
  value       = var.instance_type
}

output "vpc_id" {
  description = "VPC ID"
  value       = digitalocean_vpc.proxy_vpc.id
}

output "deployment_uid" {
  description = "Unique deployment identifier"
  value       = var.deployment_uid
}

output "droplet_status" {
  description = "Status of the droplet"
  value       = digitalocean_droplet.proxy.status
}

output "droplet_name" {
  description = "Name of the droplet"
  value       = digitalocean_droplet.proxy.name
}