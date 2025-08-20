variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "proxygen"
}

variable "region" {
  description = "DigitalOcean region"
  type        = string
}

variable "deployment_uid" {
  description = "Unique deployment identifier"
  type        = string
  default     = ""
}

variable "instance_type" {
  description = "Droplet size"
  type        = string
  default     = "s-1vcpu-1gb"
}

variable "os_image" {
  description = "OS image for the droplet"
  type        = string
  default     = "ubuntu-22-04-x64"
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
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