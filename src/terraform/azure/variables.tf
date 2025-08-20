variable "region" {
  description = "Azure region"
  type        = string
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "proxygen"
}

variable "instance_type" {
  description = "Azure VM size"
  type        = string
  default     = "Standard_B1s"
}

variable "vnet_cidr" {
  description = "CIDR block for Virtual Network"
  type        = string
  default     = "10.0.0.0/16"
}

variable "subnet_cidr" {
  description = "CIDR block for subnet"
  type        = string
  default     = "10.0.1.0/24"
}

variable "wireguard_port" {
  description = "WireGuard UDP port"
  type        = number
  default     = 51820
}

variable "allowed_ips" {
  description = "List of allowed IP addresses for SSH access"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "monitoring_enabled" {
  description = "Enable Azure Monitor alerts"
  type        = bool
  default     = true
}

variable "deployment_uid" {
  description = "Unique deployment identifier"
  type        = string
  default     = ""
}