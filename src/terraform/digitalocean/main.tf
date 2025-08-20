terraform {
  required_version = ">= 1.0"
  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
  
  backend "local" {}
}

# Generate SSH key pair
resource "tls_private_key" "proxy_key" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

# Create SSH key in DigitalOcean
resource "digitalocean_ssh_key" "proxy_key" {
  name       = "${var.project_name}-${var.region}-${var.deployment_uid}"
  public_key = tls_private_key.proxy_key.public_key_openssh
}

# Save private key locally
resource "local_file" "private_key" {
  content         = tls_private_key.proxy_key.private_key_pem
  filename        = abspath("${path.module}/../../../state/proxygen-${var.region}-${var.deployment_uid}-key.pem")
  file_permission = "0600"
}

# Create VPC
resource "digitalocean_vpc" "proxy_vpc" {
  name     = "${var.project_name}-vpc-${var.region}-${var.deployment_uid}"
  region   = var.region
  ip_range = var.vpc_cidr
}

# Create Droplet (VM instance)
resource "digitalocean_droplet" "proxy" {
  name     = "${var.project_name}-${var.region}-${var.deployment_uid}"
  size     = var.instance_type
  image    = var.os_image
  region   = var.region
  vpc_uuid = digitalocean_vpc.proxy_vpc.id
  
  ssh_keys = [digitalocean_ssh_key.proxy_key.fingerprint]
  
  tags = [
    var.project_name,
    "wireguard",
    var.deployment_uid
  ]

  user_data = <<-EOF
    #!/bin/bash
    # Update system
    apt-get update
    apt-get upgrade -y
    
    # Install WireGuard
    apt-get install -y wireguard iptables
    
    # Enable IP forwarding
    echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
    echo "net.ipv6.conf.all.forwarding=1" >> /etc/sysctl.conf
    sysctl -p
    
    # Create WireGuard directory
    mkdir -p /etc/wireguard
    
    # Set up firewall rules
    iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
    iptables -A FORWARD -i wg0 -j ACCEPT
    iptables-save > /etc/iptables/rules.v4
  EOF
}

# Create Firewall
resource "digitalocean_firewall" "proxy_firewall" {
  name = "${var.project_name}-fw-${var.region}-${var.deployment_uid}"

  droplet_ids = [digitalocean_droplet.proxy.id]

  # Allow SSH
  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = var.ssh_allowed_ips
  }

  # Allow WireGuard
  inbound_rule {
    protocol         = "udp"
    port_range       = "51820"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  # Allow all outbound traffic
  outbound_rule {
    protocol              = "tcp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "udp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "icmp"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
}

# Create a reserved IP (floating IP)
resource "digitalocean_floating_ip" "proxy_ip" {
  region = var.region
}

# Assign floating IP to droplet
resource "digitalocean_floating_ip_assignment" "proxy_ip_assignment" {
  ip_address = digitalocean_floating_ip.proxy_ip.ip_address
  droplet_id = digitalocean_droplet.proxy.id
}