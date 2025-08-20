terraform {
  required_version = ">= 1.0"
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.42"
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

# Create SSH key in Hetzner Cloud
resource "hcloud_ssh_key" "proxy_key" {
  name       = "${var.project_name}-${var.region}-${var.deployment_uid}"
  public_key = tls_private_key.proxy_key.public_key_openssh
}

# Save private key locally
resource "local_file" "private_key" {
  content         = tls_private_key.proxy_key.private_key_pem
  filename        = abspath("${path.module}/../../../state/proxygen-${var.region}-${var.deployment_uid}-key.pem")
  file_permission = "0600"
}

# Create network
resource "hcloud_network" "proxy_network" {
  name     = "${var.project_name}-net-${var.region}-${var.deployment_uid}"
  ip_range = var.network_cidr
}

# Create subnet
resource "hcloud_network_subnet" "proxy_subnet" {
  network_id   = hcloud_network.proxy_network.id
  type         = "cloud"
  network_zone = var.network_zone
  ip_range     = var.subnet_cidr
}

# Create server (VM instance)
resource "hcloud_server" "proxy" {
  name        = "${var.project_name}-${var.region}-${var.deployment_uid}"
  server_type = var.instance_type
  image       = var.os_image
  location    = var.region
  ssh_keys    = [hcloud_ssh_key.proxy_key.id]
  
  labels = {
    project = var.project_name
    service = "wireguard"
    uid     = var.deployment_uid
  }

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

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }

  depends_on = [
    hcloud_network_subnet.proxy_subnet
  ]
}

# Attach server to network
resource "hcloud_server_network" "proxy_network" {
  server_id  = hcloud_server.proxy.id
  network_id = hcloud_network.proxy_network.id
  ip         = var.server_private_ip
}

# Create Firewall
resource "hcloud_firewall" "proxy_firewall" {
  name = "${var.project_name}-fw-${var.region}-${var.deployment_uid}"

  # Allow SSH
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = var.ssh_allowed_ips
  }

  # Allow WireGuard
  rule {
    direction  = "in"
    protocol   = "udp"
    port       = "51820"
    source_ips = [
      "0.0.0.0/0",
      "::/0"
    ]
  }

  # Allow all outbound traffic (Hetzner allows all outbound by default)
}

# Attach firewall to server
resource "hcloud_firewall_attachment" "proxy_firewall" {
  firewall_id = hcloud_firewall.proxy_firewall.id
  server_ids  = [hcloud_server.proxy.id]
}

# Create a Floating IP
resource "hcloud_floating_ip" "proxy_ip" {
  type          = "ipv4"
  home_location = var.region
  description   = "${var.project_name}-${var.region}-${var.deployment_uid}"
  
  labels = {
    project = var.project_name
    uid     = var.deployment_uid
  }
}

# Assign floating IP to server
resource "hcloud_floating_ip_assignment" "proxy_ip_assignment" {
  floating_ip_id = hcloud_floating_ip.proxy_ip.id
  server_id      = hcloud_server.proxy.id
}