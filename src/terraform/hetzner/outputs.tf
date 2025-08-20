output "instance_id" {
  description = "ID of the Hetzner server"
  value       = hcloud_server.proxy.id
}

output "public_ip" {
  description = "Public IP address of the Proxy server"
  value       = hcloud_floating_ip.proxy_ip.ip_address
}

output "private_ip" {
  description = "Private IP address of the Proxy server"
  value       = var.server_private_ip
}

output "private_key_path" {
  description = "Path to the SSH private key"
  value       = abspath(local_file.private_key.filename)
}

output "region" {
  description = "Hetzner location"
  value       = var.region
}

output "instance_type" {
  description = "Server type"
  value       = var.instance_type
}

output "network_id" {
  description = "Network ID"
  value       = hcloud_network.proxy_network.id
}

output "deployment_uid" {
  description = "Unique deployment identifier"
  value       = var.deployment_uid
}

output "server_status" {
  description = "Status of the server"
  value       = hcloud_server.proxy.status
}

output "server_name" {
  description = "Name of the server"
  value       = hcloud_server.proxy.name
}

output "ipv4_address" {
  description = "IPv4 address of the server"
  value       = hcloud_server.proxy.ipv4_address
}

output "ipv6_address" {
  description = "IPv6 address of the server"
  value       = hcloud_server.proxy.ipv6_address
}