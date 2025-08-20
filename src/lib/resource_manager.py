#!/usr/bin/env python3
"""
Resource Manager for ProxyGen
Tracks and manages cloud resources
"""

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class ResourceManager:
    """Manage and track cloud resources"""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.state_dir = base_dir / "state"

    def list_resources(self, provider: str, region: str) -> Dict:
        """List all resources in a region from Terraform state"""
        state_file = self.state_dir / f"{provider}-{region}.tfstate"

        if not state_file.exists():
            return {}

        resources = {"provider": provider, "region": region, "resources": []}

        try:
            # Use terraform show to get resources
            terraform_dir = self.base_dir / "terraform" / provider
            cmd = ["terraform", "show", "-json", str(state_file)]

            result = subprocess.run(
                cmd, cwd=terraform_dir, capture_output=True, text=True
            )

            if result.returncode == 0:
                state_data = json.loads(result.stdout)

                # Parse resources from state
                if "values" in state_data and "root_module" in state_data["values"]:
                    root = state_data["values"]["root_module"]

                    # Get resources
                    for resource in root.get("resources", []):
                        resource_info = {
                            "type": resource.get("type", ""),
                            "name": resource.get("name", ""),
                            "address": resource.get("address", ""),
                        }

                        # Get specific resource details based on type
                        values = resource.get("values", {})

                        if resource["type"] == "aws_instance":
                            resource_info["details"] = {
                                "instance_id": values.get("id"),
                                "instance_type": values.get("instance_type"),
                                "public_ip": values.get("public_ip"),
                                "state": values.get("instance_state"),
                            }
                        elif resource["type"] == "aws_vpc":
                            resource_info["details"] = {
                                "vpc_id": values.get("id"),
                                "cidr_block": values.get("cidr_block"),
                            }
                        elif resource["type"] == "aws_security_group":
                            resource_info["details"] = {
                                "security_group_id": values.get("id"),
                                "name": values.get("name"),
                            }
                        elif resource["type"] == "aws_eip":
                            resource_info["details"] = {
                                "allocation_id": values.get("id"),
                                "public_ip": values.get("public_ip"),
                            }
                        elif resource["type"] == "azurerm_linux_virtual_machine":
                            resource_info["details"] = {
                                "vm_id": values.get("id"),
                                "size": values.get("size"),
                                "name": values.get("name"),
                            }
                        elif resource["type"] == "azurerm_public_ip":
                            resource_info["details"] = {
                                "ip_id": values.get("id"),
                                "ip_address": values.get("ip_address"),
                            }
                        elif resource["type"] == "digitalocean_droplet":
                            resource_info["details"] = {
                                "instance_id": values.get("id"),
                                "size": values.get("size"),
                                "name": values.get("name"),
                            }
                        elif resource["type"] == "hcloud_server":
                            resource_info["details"] = {
                                "instance_id": values.get("id"),
                                "server_type": values.get("server_type"),
                                "name": values.get("name"),
                            }

                        resources["resources"].append(resource_info)

                return resources

        except Exception as e:
            logger.error(f"Error listing resources: {e}")

        return resources

    def estimate_destruction_cost(self, provider: str, region: str) -> Dict:
        """Estimate the cost of resources that will be destroyed"""
        resources = self.list_resources(provider, region)

        # Simple cost estimation based on resource types
        cost_estimate = {
            "provider": provider,
            "region": region,
            "estimated_monthly_cost": 0,
            "resources_count": len(resources.get("resources", [])),
        }

        # Basic cost estimation (simplified)
        for resource in resources.get("resources", []):
            if resource["type"] in [
                "aws_instance",
                "azurerm_linux_virtual_machine",
                "digitalocean_droplet",
                "hcloud_server",
            ]:
                # Estimate instance cost
                cost_estimate["estimated_monthly_cost"] += 30  # Basic estimate
            elif resource["type"] in [
                "aws_eip",
                "azurerm_public_ip",
                "digitalocean_floating_ip",
                "hcloud_floating_ip",
            ]:
                # Estimate IP cost
                cost_estimate["estimated_monthly_cost"] += 3.6  # ~$0.005/hour

        return cost_estimate

    def get_resource_summary(self, provider: str, regions: List[str]) -> str:
        """Get a summary of resources to be destroyed"""
        summary_lines = []
        total_resources = 0
        total_cost = 0

        for region in regions:
            resources = self.list_resources(provider, region)
            cost = self.estimate_destruction_cost(provider, region)

            if resources.get("resources"):
                summary_lines.append(f"\n{provider.upper()} - {region}:")
                summary_lines.append("-" * 40)

                # Group resources by type
                resource_types = {}
                for resource in resources["resources"]:
                    rtype = resource["type"]
                    if rtype not in resource_types:
                        resource_types[rtype] = []
                    resource_types[rtype].append(resource)

                # Display resources by type
                for rtype, items in resource_types.items():
                    summary_lines.append(f"  {rtype}: {len(items)} resource(s)")
                    for item in items:
                        if "details" in item and item["details"]:
                            details = item["details"]
                            if "public_ip" in details:
                                summary_lines.append(
                                    f"    - {item['name']} (IP: {details['public_ip']})"
                                )
                            elif "ip_address" in details:
                                summary_lines.append(
                                    f"    - {item['name']} (IP: {details['ip_address']})"
                                )
                            else:
                                summary_lines.append(f"    - {item['name']}")

                total_resources += len(resources["resources"])
                total_cost += cost["estimated_monthly_cost"]

        if total_resources > 0:
            summary_lines.append("\n" + "=" * 40)
            summary_lines.append(f"Total resources to destroy: {total_resources}")
            summary_lines.append(f"Estimated monthly cost saved: ${total_cost:.2f}")

        return "\n".join(summary_lines)
