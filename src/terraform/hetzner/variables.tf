variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "proxygen"
}

variable "region" {
  description = "Hetzner location"
  type        = string
}

variable "deployment_uid" {
  description = "Unique deployment identifier"
  type        = string
  default     = ""
}

variable "instance_type" {
  description = "Server type"
  type        = string
  default     = "cx11"
}

variable "os_image" {
  description = "OS image for the server"
  type        = string
  default     = "ubuntu-22.04"
}

variable "network_cidr" {
  description = "CIDR block for network"
  type        = string
  default     = "10.0.0.0/16"
}

variable "subnet_cidr" {
  description = "CIDR block for subnet"
  type        = string
  default     = "10.0.1.0/24"
}

variable "network_zone" {
  description = "Network zone"
  type        = string
  default     = "eu-central"
}

variable "server_private_ip" {
  description = "Private IP for the server in the network"
  type        = string
  default     = "10.0.1.10"
}

variable "ssh_allowed_ips" {
  description = "List of IPs allowed for SSH access"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "wireguard_port" {
  description = "WireGuard UDP port"
  type        = number
  default     = 51820
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default = {
    Environment = "proxy"
    ManagedBy   = "terraform"
  }
}