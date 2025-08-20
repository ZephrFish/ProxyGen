output "public_ip" {
  description = "Public IP address of the Proxy server"
  value       = azurerm_public_ip.proxy_pip.ip_address
}

output "instance_id" {
  description = "Virtual Machine ID"
  value       = azurerm_linux_virtual_machine.proxy_vm.id
}

output "private_key_path" {
  description = "Path to the private SSH key"
  value       = abspath(local_file.private_key.filename)
}

output "resource_group_name" {
  description = "Resource Group name"
  value       = azurerm_resource_group.proxy_rg.name
}

output "vnet_id" {
  description = "Virtual Network ID"
  value       = azurerm_virtual_network.proxy_vnet.id
}

output "region" {
  description = "Azure region"
  value       = var.region
}