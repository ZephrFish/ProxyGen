#!/usr/bin/env python3
"""
Deployment Tracker for ProxyGen
Tracks all deployed resources and allows selective management
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging
try:
    from .ip_manager import IPManager
except ImportError:
    from ip_manager import IPManager

logger = logging.getLogger(__name__)


class DeploymentTracker:
    """Track and manage all Proxy deployments"""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.state_dir = base_dir / "state"
        self.inventory_file = self.state_dir / "deployment_inventory.json"
        self.ip_manager = IPManager(base_dir)
        self.load_inventory()

    def load_inventory(self):
        """Load deployment inventory from file"""
        if self.inventory_file.exists():
            try:
                with open(self.inventory_file, "r") as f:
                    self.inventory = json.load(f)
            except json.JSONDecodeError:
                logger.warning("Corrupted inventory file, creating new one")
                self.inventory = {"deployments": {}, "metadata": {}}
        else:
            self.inventory = {
                "deployments": {},
                "metadata": {
                    "created_at": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat(),
                    "version": "1.0",
                },
            }
            self.save_inventory()

    def save_inventory(self):
        """Save deployment inventory to file"""
        self.inventory["metadata"]["last_updated"] = datetime.now().isoformat()

        # Create backup of existing inventory
        if self.inventory_file.exists():
            backup_file = self.inventory_file.with_suffix(".json.backup")
            import shutil

            shutil.copy2(self.inventory_file, backup_file)

        with open(self.inventory_file, "w") as f:
            json.dump(self.inventory, f, indent=2, default=str)

    def add_deployment(
        self,
        deployment_id: str,
        provider: str,
        region: str,
        resources: Dict[str, Any],
        config: Optional[Dict] = None,
    ) -> str:
        """Add a new deployment to inventory"""

        # Create unique deployment ID if not provided
        if not deployment_id:
            deployment_id = (
                f"{provider}-{region}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            )

        # Check for IP conflicts before creating deployment
        existing_ips = self.ip_manager.check_ip_conflicts(provider, region)
        if existing_ips and "public_ip" in resources:
            logger.warning(f"IP conflict detected in {provider}-{region}: {existing_ips}")
        
        deployment_record = {
            "id": deployment_id,
            "provider": provider,
            "region": region,
            "created_at": datetime.now().isoformat(),
            "status": "active",
            "resources": resources,
            "config": config or {},
            "tags": {"managed_by": "proxygen", "provider": provider, "region": region},
            "cost_estimate": self._estimate_cost(provider, resources, config),
            "clients": [],
        }
        
        # Register IP address if provided
        if "public_ip" in resources:
            self.ip_manager.register_deployment_ip(
                deployment_id, provider, region, resources["public_ip"]
            )

        # Store in inventory
        if provider not in self.inventory["deployments"]:
            self.inventory["deployments"][provider] = {}

        if region not in self.inventory["deployments"][provider]:
            self.inventory["deployments"][provider][region] = []

        self.inventory["deployments"][provider][region].append(deployment_record)

        self.save_inventory()
        logger.info(f"Added deployment {deployment_id} to inventory")

        return deployment_id

    def get_deployment(self, deployment_id: str) -> Optional[Dict]:
        """Get a specific deployment by ID"""
        for provider in self.inventory["deployments"]:
            for region in self.inventory["deployments"][provider]:
                for deployment in self.inventory["deployments"][provider][region]:
                    if deployment["id"] == deployment_id:
                        return deployment
        return None

    def get_deployments_by_region(self, provider: str, region: str) -> List[Dict]:
        """Get all deployments in a specific region"""
        if provider in self.inventory["deployments"]:
            if region in self.inventory["deployments"][provider]:
                return self.inventory["deployments"][provider][region]
        return []

    def list_all_deployments(self) -> List[Dict]:
        """List all deployments across all providers and regions"""
        deployments = []
        for provider in self.inventory["deployments"]:
            for region in self.inventory["deployments"][provider]:
                deployments.extend(self.inventory["deployments"][provider][region])
        return deployments

    def update_deployment_status(self, deployment_id: str, status: str):
        """Update the status of a deployment"""
        deployment = self.get_deployment(deployment_id)
        if deployment:
            deployment["status"] = status
            deployment["last_modified"] = datetime.now().isoformat()
            self.save_inventory()
            return True
        return False

    def add_client_to_deployment(self, deployment_id: str, client_info: Dict):
        """Add a client configuration to a deployment"""
        deployment = self.get_deployment(deployment_id)
        if deployment:
            if "clients" not in deployment:
                deployment["clients"] = []

            client_record = {
                "name": client_info.get("name"),
                "ip_address": client_info.get("ip_address"),
                "created_at": datetime.now().isoformat(),
                "config_file": client_info.get("config_file"),
                "active": True,
            }

            deployment["clients"].append(client_record)
            self.save_inventory()
            return True
        return False

    def remove_deployment(self, deployment_id: str) -> bool:
        """Remove a deployment from inventory"""
        for provider in self.inventory["deployments"]:
            for region in self.inventory["deployments"][provider]:
                deployments = self.inventory["deployments"][provider][region]
                for i, deployment in enumerate(deployments):
                    if deployment["id"] == deployment_id:
                        # Release IP address before marking as destroyed
                        self.ip_manager.release_deployment_ip(deployment_id)
                        
                        # Mark as destroyed instead of removing
                        deployment["status"] = "destroyed"
                        deployment["destroyed_at"] = datetime.now().isoformat()
                        self.save_inventory()
                        logger.info(f"Marked deployment {deployment_id} as destroyed")
                        return True
        return False

    def get_active_deployments(self) -> List[Dict]:
        """Get all active deployments"""
        active = []
        for deployment in self.list_all_deployments():
            if deployment.get("status") == "active":
                active.append(deployment)
        return active

    def _estimate_cost(self, provider: str, resources: Dict, config: Dict = None) -> Dict:
        """Estimate monthly cost for resources based on actual instance types"""
        
        # Detailed instance type pricing (USD per month)
        instance_pricing = {
            "aws": {
                "t3.nano": 3.80,
                "t3.micro": 7.60,
                "t3.small": 15.20,
                "t3.medium": 30.40,
                "t3.large": 60.80,
                "t2.micro": 8.50,  # Legacy, in free tier
                "t2.small": 16.80,
                "t2.medium": 33.70,
            },
            "azure": {
                "Standard_B1s": 3.80,
                "Standard_B1ms": 7.60,
                "Standard_B2s": 15.20,
                "Standard_B2ms": 30.40,
                "Standard_B4ms": 60.80,
                "Standard_D2s_v3": 70.00,
            },
            "digitalocean": {
                "s-1vcpu-1gb": 6.00,
                "s-1vcpu-2gb": 12.00,
                "s-2vcpu-2gb": 18.00,
                "s-2vcpu-4gb": 24.00,
                "s-4vcpu-8gb": 48.00,
            },
            "hetzner": {
                "cx11": 3.60,
                "cx21": 6.40,
                "cx31": 11.60,
                "cx41": 22.00,
                "cx51": 43.00,
            }
        }
        
        # Additional costs
        additional_costs = {
            "aws": {"ip": 3.60, "storage_per_gb": 0.10},
            "azure": {"ip": 3.60, "storage_per_gb": 0.115},
            "digitalocean": {"ip": 0, "storage_per_gb": 0.10},
            "hetzner": {"ip": 0, "storage_per_gb": 0.05},
        }

        # Get instance type from config if available
        instance_type = None
        if config and "instance_type" in config:
            instance_type = config["instance_type"]
        
        # Calculate instance cost
        monthly_cost = 0
        if instance_type and provider in instance_pricing:
            if instance_type in instance_pricing[provider]:
                monthly_cost = instance_pricing[provider][instance_type]
            else:
                # Default to cheapest if instance type not found
                monthly_cost = min(instance_pricing[provider].values())
        else:
            # Default costs if no instance type specified
            default_costs = {"aws": 7.60, "azure": 7.60, "digitalocean": 6.00, "hetzner": 3.60}
            monthly_cost = default_costs.get(provider, 10.00)
        
        # Add IP cost if public IP exists
        if resources.get("public_ip"):
            monthly_cost += additional_costs.get(provider, {}).get("ip", 3.60)
        
        # Add storage cost (default 20GB)
        storage_gb = resources.get("storage_gb", 20)
        storage_cost = storage_gb * additional_costs.get(provider, {}).get("storage_per_gb", 0.10)
        monthly_cost += storage_cost

        return {
            "monthly": round(monthly_cost, 2),
            "yearly": round(monthly_cost * 12, 2),
            "daily": round(monthly_cost / 30, 2),
            "currency": "USD",
        }

    def generate_summary_report(self) -> str:
        """Generate a summary report of all deployments"""
        active_deployments = self.get_active_deployments()

        report_lines = [
            "=" * 60,
            "ProxyGen Deployment Inventory Report",
            "=" * 60,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"Total Active Deployments: {len(active_deployments)}",
            "",
        ]

        # Group by provider
        by_provider = {}
        total_monthly_cost = 0
        total_clients = 0

        for deployment in active_deployments:
            provider = deployment["provider"]
            if provider not in by_provider:
                by_provider[provider] = []
            by_provider[provider].append(deployment)
            total_monthly_cost += deployment.get("cost_estimate", {}).get("monthly", 0)
            total_clients += len(deployment.get("clients", []))

        # Provider summaries
        for provider, deployments in by_provider.items():
            report_lines.append(f"\n{provider.upper()} Deployments:")
            report_lines.append("-" * 40)

            for dep in deployments:
                report_lines.append(f"  ID: {dep['id']}")
                report_lines.append(f"    Region: {dep['region']}")
                report_lines.append(f"    Status: {dep['status']}")
                report_lines.append(f"    Created: {dep['created_at']}")
                report_lines.append(
                    f"    Monthly Cost: ${dep.get('cost_estimate', {}).get('monthly', 0):.2f}"
                )
                report_lines.append(f"    Clients: {len(dep.get('clients', []))}")

                if dep.get("resources", {}).get("public_ip"):
                    report_lines.append(
                        f"    Public IP: {dep['resources']['public_ip']}"
                    )

        # Summary statistics
        report_lines.extend(
            [
                "",
                "=" * 60,
                "Summary Statistics:",
                f"  Total Monthly Cost: ${total_monthly_cost:.2f}",
                f"  Total Yearly Cost: ${total_monthly_cost * 12:.2f}",
                f"  Total Clients: {total_clients}",
                f"  Providers in Use: {', '.join(by_provider.keys())}",
                "=" * 60,
            ]
        )

        return "\n".join(report_lines)

    def export_inventory(self, format: str = "json") -> str:
        """Export inventory in various formats"""
        if format == "json":
            return json.dumps(self.inventory, indent=2, default=str)

        elif format == "csv":
            import csv
            import io

            output = io.StringIO()
            writer = csv.writer(output)

            # Write header
            writer.writerow(
                [
                    "Deployment ID",
                    "Provider",
                    "Region",
                    "Status",
                    "Created At",
                    "Monthly Cost",
                    "Public IP",
                    "Clients",
                ]
            )

            # Write data
            for deployment in self.list_all_deployments():
                writer.writerow(
                    [
                        deployment["id"],
                        deployment["provider"],
                        deployment["region"],
                        deployment["status"],
                        deployment["created_at"],
                        deployment.get("cost_estimate", {}).get("monthly", 0),
                        deployment.get("resources", {}).get("public_ip", "N/A"),
                        len(deployment.get("clients", [])),
                    ]
                )

            return output.getvalue()

        elif format == "yaml":
            import yaml

            return yaml.dump(self.inventory, default_flow_style=False, default=str)

        else:
            raise ValueError(f"Unsupported export format: {format}")

    def cleanup_destroyed_deployments(self, days_old: int = 30):
        """Remove destroyed deployments older than specified days"""
        from datetime import timedelta

        cutoff_date = datetime.now() - timedelta(days=days_old)
        cleaned = 0

        for provider in list(self.inventory["deployments"].keys()):
            for region in list(self.inventory["deployments"][provider].keys()):
                deployments = self.inventory["deployments"][provider][region]
                active_deployments = []

                for deployment in deployments:
                    if deployment.get("status") == "destroyed":
                        destroyed_at = datetime.fromisoformat(
                            deployment.get("destroyed_at", deployment["created_at"])
                        )
                        if destroyed_at < cutoff_date:
                            cleaned += 1
                            continue

                    active_deployments.append(deployment)

                self.inventory["deployments"][provider][region] = active_deployments

                # Clean up empty regions
                if not active_deployments:
                    del self.inventory["deployments"][provider][region]

            # Clean up empty providers
            if not self.inventory["deployments"][provider]:
                del self.inventory["deployments"][provider]

        if cleaned > 0:
            self.save_inventory()
            logger.info(f"Cleaned up {cleaned} old destroyed deployments")

        return cleaned
