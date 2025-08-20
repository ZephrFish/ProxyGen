terraform {
  required_version = ">= 1.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
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

provider "azurerm" {
  features {}
}

# Create Resource Group
resource "azurerm_resource_group" "proxy_rg" {
  name     = "${var.project_name}-${var.region}-${var.deployment_uid}-rg"
  location = var.region
  
  tags = {
    Name    = "${var.project_name}-${var.region}-${var.deployment_uid}-rg"
    Project = var.project_name
    Region  = var.region
    DeploymentUID = var.deployment_uid
  }
}

# Create Virtual Network
resource "azurerm_virtual_network" "proxy_vnet" {
  name                = "${var.project_name}-${var.region}-${var.deployment_uid}-vnet"
  address_space       = [var.vnet_cidr]
  location            = azurerm_resource_group.proxy_rg.location
  resource_group_name = azurerm_resource_group.proxy_rg.name
  
  tags = {
    Name    = "${var.project_name}-${var.region}-${var.deployment_uid}-vnet"
    Project = var.project_name
    Region  = var.region
    DeploymentUID = var.deployment_uid
  }
}

# Create Subnet
resource "azurerm_subnet" "proxy_subnet" {
  name                 = "${var.project_name}-${var.region}-${var.deployment_uid}-subnet"
  resource_group_name  = azurerm_resource_group.proxy_rg.name
  virtual_network_name = azurerm_virtual_network.proxy_vnet.name
  address_prefixes     = [var.subnet_cidr]
}

# Create Public IP
resource "azurerm_public_ip" "proxy_pip" {
  name                = "${var.project_name}-${var.region}-${var.deployment_uid}-pip"
  location            = azurerm_resource_group.proxy_rg.location
  resource_group_name = azurerm_resource_group.proxy_rg.name
  allocation_method   = "Static"
  sku                 = "Standard"
  
  tags = {
    Name    = "${var.project_name}-${var.region}-${var.deployment_uid}-pip"
    Project = var.project_name
    Region  = var.region
    DeploymentUID = var.deployment_uid
  }
}

# Create Network Security Group
resource "azurerm_network_security_group" "proxy_nsg" {
  name                = "${var.project_name}-${var.region}-${var.deployment_uid}-nsg"
  location            = azurerm_resource_group.proxy_rg.location
  resource_group_name = azurerm_resource_group.proxy_rg.name
  
  # SSH Rule
  security_rule {
    name                       = "SSH"
    priority                   = 1001
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefixes    = var.allowed_ips
    destination_address_prefix = "*"
  }
  
  # WireGuard Rule
  security_rule {
    name                       = "WireGuard"
    priority                   = 1002
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Udp"
    source_port_range          = "*"
    destination_port_range     = tostring(var.wireguard_port)
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
  
  tags = {
    Name    = "${var.project_name}-${var.region}-nsg"
    Project = var.project_name
    Region  = var.region
  }
}

# Create Network Interface
resource "azurerm_network_interface" "proxy_nic" {
  name                = "${var.project_name}-${var.region}-${var.deployment_uid}-nic"
  location            = azurerm_resource_group.proxy_rg.location
  resource_group_name = azurerm_resource_group.proxy_rg.name
  
  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.proxy_subnet.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.proxy_pip.id
  }
  
  tags = {
    Name    = "${var.project_name}-${var.region}-nic"
    Project = var.project_name
    Region  = var.region
  }
}

# Associate Network Security Group with Network Interface
resource "azurerm_network_interface_security_group_association" "proxy_nic_nsg" {
  network_interface_id      = azurerm_network_interface.proxy_nic.id
  network_security_group_id = azurerm_network_security_group.proxy_nsg.id
}

# Generate SSH key pair
resource "tls_private_key" "proxy_key" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

# Save private key locally
resource "local_file" "private_key" {
  content         = tls_private_key.proxy_key.private_key_pem
  filename        = abspath("${path.module}/../../../state/${var.project_name}-${var.region}-${var.deployment_uid}-key.pem")
  file_permission = "0600"
}

# Create Virtual Machine
resource "azurerm_linux_virtual_machine" "proxy_vm" {
  name                = "${var.project_name}-${var.region}-${var.deployment_uid}-vm"
  location            = azurerm_resource_group.proxy_rg.location
  resource_group_name = azurerm_resource_group.proxy_rg.name
  size                = var.instance_type
  admin_username      = "azureuser"
  
  disable_password_authentication = true
  
  admin_ssh_key {
    username   = "azureuser"
    public_key = tls_private_key.proxy_key.public_key_openssh
  }
  
  network_interface_ids = [
    azurerm_network_interface.proxy_nic.id,
  ]
  
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
  }
  
  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }
  
  custom_data = base64encode(<<-EOF
    #!/bin/bash
    apt-get update
    apt-get install -y wireguard iptables python3-pip
    
    # Enable IP forwarding
    echo 'net.ipv4.ip_forward=1' >> /etc/sysctl.conf
    echo 'net.ipv6.conf.all.forwarding=1' >> /etc/sysctl.conf
    sysctl -p
    
    # Configure firewall rules
    iptables -A FORWARD -i wg0 -j ACCEPT
    iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
    
    # Save iptables rules
    apt-get install -y iptables-persistent
    netfilter-persistent save
  EOF
  )
  
  tags = {
    Name    = "${var.project_name}-${var.region}-vm"
    Project = var.project_name
    Region  = var.region
    Type    = "proxy-server"
  }
}

# Enable IP forwarding on the NIC
resource "azurerm_network_interface" "proxy_nic_ip_forwarding" {
  name                 = azurerm_network_interface.proxy_nic.name
  location             = azurerm_network_interface.proxy_nic.location
  resource_group_name  = azurerm_network_interface.proxy_nic.resource_group_name
  enable_ip_forwarding = true
  
  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.proxy_subnet.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.proxy_pip.id
  }
  
  depends_on = [azurerm_linux_virtual_machine.proxy_vm]
  
  lifecycle {
    create_before_destroy = true
  }
}

# Azure Monitor Metrics Alert for CPU
resource "azurerm_monitor_metric_alert" "proxy_cpu" {
  count               = var.monitoring_enabled ? 1 : 0
  name                = "${var.project_name}-${var.region}-cpu-alert"
  resource_group_name = azurerm_resource_group.proxy_rg.name
  scopes              = [azurerm_linux_virtual_machine.proxy_vm.id]
  description         = "Alert when CPU usage is too high"
  severity            = 2
  frequency           = "PT5M"
  window_size         = "PT15M"
  
  criteria {
    metric_namespace = "Microsoft.Compute/virtualMachines"
    metric_name      = "Percentage CPU"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 80
  }
  
  action {
    action_group_id = azurerm_monitor_action_group.proxy_alerts[0].id
  }
}

# Azure Monitor Action Group
resource "azurerm_monitor_action_group" "proxy_alerts" {
  count               = var.monitoring_enabled ? 1 : 0
  name                = "${var.project_name}-${var.region}-alerts"
  resource_group_name = azurerm_resource_group.proxy_rg.name
  short_name          = "proxyalerts"
}