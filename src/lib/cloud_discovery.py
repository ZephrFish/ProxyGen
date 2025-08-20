#!/usr/bin/env python3
"""
Cloud Resource Discovery for ProxyGen
Discovers existing Proxy deployments using cloud provider CLIs
"""

import json
import subprocess
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class CloudDiscovery:
    """Discover existing Proxy deployments using cloud provider CLIs"""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.state_dir = base_dir / "state"
        
        # ProxyGen naming patterns for each provider
        # Format: proxygen-{region}-{uid}-{suffix}
        self.naming_patterns = {
            "aws": r"^proxygen-[\w-]+-[a-f0-9]{6}-proxy$",  # proxygen-us-east-1-abc123-proxy
            "azure": r"^proxygen-[\w-]+-[a-f0-9]{6}-vm$",   # proxygen-westeurope-abc123-vm
            "digitalocean": r"^proxygen-[\w-]+-[a-f0-9]{6}$",  # proxygen-nyc1-abc123
            "hetzner": r"^proxygen-[\w-]+-[a-f0-9]{6}$"       # proxygen-fsn1-abc123
        }
        
        # Project name (could be made configurable)
        self.project_name = "proxygen"

    def discover_all_deployments(self) -> Dict[str, List[Dict]]:
        """Discover deployments across all cloud providers"""
        discoveries = {}
        
        # Try each provider
        aws_deployments = self.discover_aws_deployments()
        if aws_deployments:
            discoveries["aws"] = aws_deployments
            
        azure_deployments = self.discover_azure_deployments()
        if azure_deployments:
            discoveries["azure"] = azure_deployments
            
        digitalocean_deployments = self.discover_digitalocean_deployments()
        if digitalocean_deployments:
            discoveries["digitalocean"] = digitalocean_deployments
            
        hetzner_deployments = self.discover_hetzner_deployments()
        if hetzner_deployments:
            discoveries["hetzner"] = hetzner_deployments
            
        return discoveries

    def discover_aws_deployments(self) -> List[Dict]:
        """Discover AWS Proxy deployments using AWS CLI"""
        import re
        deployments = []
        
        try:
            # Get all regions
            regions_cmd = ["aws", "ec2", "describe-regions", "--query", "Regions[].RegionName", "--output", "json"]
            result = subprocess.run(regions_cmd, capture_output=True, text=True, check=True)
            regions = json.loads(result.stdout)
            
            for region in regions:
                logger.info(f"Searching AWS region: {region}")
                
                # Search for instances with ProxyGen naming pattern in Name tag
                # Using wildcard to catch proxygen-* instances
                cmd = [
                    "aws", "ec2", "describe-instances",
                    "--region", region,
                    "--filters",
                    f"Name=tag:Name,Values=proxygen-{region}-*-proxy",
                    "Name=instance-state-name,Values=running",
                    "--query", "Reservations[].Instances[].[InstanceId,PublicIpAddress,InstanceType,Tags,LaunchTime,State.Name]",
                    "--output", "json"
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                instances = json.loads(result.stdout)
                
                for instance in instances:
                    if not instance:
                        continue
                        
                    instance_id, public_ip, instance_type, tags, launch_time, state = instance
                    
                    # Extract tags into dict
                    tag_dict = {tag["Key"]: tag["Value"] for tag in (tags or [])}
                    
                    # Get the Name tag and validate it matches our pattern
                    name_tag = tag_dict.get("Name", "")
                    pattern = re.compile(self.naming_patterns["aws"])
                    
                    if not pattern.match(name_tag):
                        logger.debug(f"Skipping instance {instance_id} - name '{name_tag}' doesn't match pattern")
                        continue
                    
                    # Extract deployment UID from name (proxygen-region-UID-proxy)
                    name_parts = name_tag.split("-")
                    deployment_uid = name_parts[-2] if len(name_parts) >= 4 else tag_dict.get("DeploymentUID", "")
                    
                    deployment = {
                        "provider": "aws",
                        "region": region,
                        "instance_id": instance_id,
                        "instance_name": name_tag,
                        "public_ip": public_ip,
                        "instance_type": instance_type,
                        "deployment_uid": deployment_uid,
                        "created_at": launch_time,
                        "state": state,
                        "tags": tag_dict,
                        "discovered_at": datetime.now().isoformat()
                    }
                    
                    deployments.append(deployment)
                    # Use green color for found deployments
                    logger.info(f"\033[92mFound AWS deployment in {region}: {name_tag} ({public_ip})\033[0m")
                    
        except subprocess.CalledProcessError as e:
            logger.warning(f"AWS CLI error: {e}")
        except Exception as e:
            logger.error(f"Error discovering AWS deployments: {e}")
            
        return deployments

    def discover_azure_deployments(self) -> List[Dict]:
        """Discover Azure Proxy deployments using Azure CLI"""
        import re
        deployments = []
        
        try:
            # Get all resource groups that match proxygen naming pattern
            # Resource groups are named: proxygen-{region}-{uid}-rg
            cmd = [
                "az", "group", "list",
                "--query", "[?starts_with(name, 'proxygen-')]",
                "--output", "json"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            resource_groups = json.loads(result.stdout)
            
            for rg in resource_groups:
                rg_name = rg["name"]
                location = rg["location"]
                
                # Validate resource group name matches pattern: proxygen-{region}-{uid}-rg
                if not rg_name.startswith("proxygen-") or not rg_name.endswith("-rg"):
                    continue
                    
                logger.info(f"Searching Azure resource group: {rg_name}")
                
                # Get VMs in resource group
                vm_cmd = [
                    "az", "vm", "list",
                    "--resource-group", rg_name,
                    "--show-details",
                    "--query", "[].{name:name,publicIps:publicIps,vmSize:hardwareProfile.vmSize,id:id,tags:tags}",
                    "--output", "json"
                ]
                
                result = subprocess.run(vm_cmd, capture_output=True, text=True, check=True)
                vms = json.loads(result.stdout)
                
                pattern = re.compile(self.naming_patterns["azure"])
                
                for vm in vms:
                    vm_name = vm["name"]
                    
                    # Validate VM name matches pattern: proxygen-{region}-{uid}-vm
                    if not pattern.match(vm_name):
                        logger.debug(f"Skipping VM {vm_name} - doesn't match naming pattern")
                        continue
                    
                    # Extract deployment UID from name
                    name_parts = vm_name.split("-")
                    deployment_uid = name_parts[-2] if len(name_parts) >= 4 else vm.get("tags", {}).get("DeploymentUID", "")
                    
                    deployment = {
                        "provider": "azure",
                        "region": location,
                        "resource_group": rg_name,
                        "vm_name": vm_name,
                        "public_ip": vm["publicIps"] if vm["publicIps"] else None,
                        "instance_type": vm["vmSize"],
                        "deployment_uid": deployment_uid,
                        "tags": vm.get("tags", {}),
                        "discovered_at": datetime.now().isoformat()
                    }
                    
                    deployments.append(deployment)
                    # Use green color for found deployments
                    logger.info(f"\033[92mFound Azure deployment in {location}: {vm_name} ({vm['publicIps']})\033[0m")
                    
        except subprocess.CalledProcessError as e:
            logger.warning(f"Azure CLI error: {e}")
        except Exception as e:
            logger.error(f"Error discovering Azure deployments: {e}")
            
        return deployments

    def discover_digitalocean_deployments(self) -> List[Dict]:
        """Discover DigitalOcean Proxy deployments using doctl CLI"""
        import re
        deployments = []
        
        try:
            # List all droplets with names starting with proxygen-
            cmd = [
                "doctl", "compute", "droplet", "list",
                "--format", "ID,Name,PublicIPv4,Region,Size,Status,CreatedAt",
                "--no-header"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            lines = result.stdout.strip().split("\n")
            
            pattern = re.compile(r"^proxygen-.*")
            
            for line in lines:
                if not line:
                    continue
                    
                parts = line.split()
                if len(parts) < 7:
                    continue
                    
                droplet_id = parts[0]
                droplet_name = parts[1]
                public_ip = parts[2]
                region = parts[3]
                size = parts[4]
                status = parts[5]
                created_at = " ".join(parts[6:])
                
                # Check if name matches pattern
                if not pattern.match(droplet_name):
                    continue
                
                # Extract deployment UID from name
                name_parts = droplet_name.split("-")
                deployment_uid = name_parts[-1] if len(name_parts) >= 3 else ""
                
                deployment = {
                    "provider": "digitalocean",
                    "region": region,
                    "instance_name": droplet_name,
                    "instance_id": droplet_id,
                    "public_ip": public_ip if public_ip != "" else None,
                    "instance_type": size,
                    "deployment_uid": deployment_uid,
                    "created_at": created_at,
                    "status": status,
                    "discovered_at": datetime.now().isoformat()
                }
                
                deployments.append(deployment)
                logger.info(f"\033[92mFound DigitalOcean deployment in {region}: {droplet_name} ({public_ip})\033[0m")
                
        except subprocess.CalledProcessError as e:
            logger.warning(f"DigitalOcean CLI error: {e}")
        except Exception as e:
            logger.error(f"Error discovering DigitalOcean deployments: {e}")
            
        return deployments
    
    def discover_hetzner_deployments(self) -> List[Dict]:
        """Discover Hetzner Proxy deployments using hcloud CLI"""
        import re
        deployments = []
        
        try:
            # List all servers with names starting with proxygen-
            cmd = [
                "hcloud", "server", "list",
                "-o", "json"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            servers = json.loads(result.stdout)
            
            pattern = re.compile(r"^proxygen-.*")
            
            for server in servers:
                server_name = server["name"]
                
                # Check if name matches pattern
                if not pattern.match(server_name):
                    continue
                
                # Extract deployment UID from name
                name_parts = server_name.split("-")
                deployment_uid = name_parts[-1] if len(name_parts) >= 3 else ""
                
                deployment = {
                    "provider": "hetzner",
                    "region": server["datacenter"]["location"]["name"],
                    "instance_name": server_name,
                    "instance_id": str(server["id"]),
                    "public_ip": server["public_net"]["ipv4"]["ip"] if server.get("public_net", {}).get("ipv4") else None,
                    "instance_type": server["server_type"]["name"],
                    "deployment_uid": deployment_uid,
                    "created_at": server["created"],
                    "status": server["status"],
                    "labels": server.get("labels", {}),
                    "discovered_at": datetime.now().isoformat()
                }
                
                deployments.append(deployment)
                logger.info(f"\033[92mFound Hetzner deployment in {deployment['region']}: {server_name} ({deployment['public_ip']})\033[0m")
                
        except subprocess.CalledProcessError as e:
            logger.warning(f"Hetzner CLI error: {e}")
        except Exception as e:
            logger.error(f"Error discovering Hetzner deployments: {e}")
            
        return deployments

    def import_discovered_deployments(self, deployments: Dict[str, List[Dict]]) -> int:
        """Import discovered deployments into local inventory"""
        imported_count = 0
        
        try:
            from .deployment_tracker import DeploymentTracker
            tracker = DeploymentTracker(self.base_dir)
            
            for provider, provider_deployments in deployments.items():
                for deployment in provider_deployments:
                    # Check if already in inventory
                    existing = tracker.get_deployments_by_region(
                        deployment["provider"], 
                        deployment["region"]
                    )
                    
                    # Check if this specific deployment exists
                    exists = False
                    for existing_dep in existing:
                        if provider == "aws" and existing_dep.get("resources", {}).get("instance_id") == deployment.get("instance_id"):
                            exists = True
                            break
                        elif provider == "azure" and existing_dep.get("resources", {}).get("vm_name") == deployment.get("vm_name"):
                            exists = True
                            break
                        elif provider in ["digitalocean", "hetzner"] and existing_dep.get("resources", {}).get("instance_name") == deployment.get("instance_name"):
                            exists = True
                            break
                    
                    if not exists:
                        # Create deployment record
                        deployment_id = self._generate_deployment_id(deployment)
                        
                        resources = {
                            "public_ip": deployment.get("public_ip"),
                            "discovered": True,  # Mark as discovered vs created
                        }
                        
                        if provider == "aws":
                            resources["instance_id"] = deployment["instance_id"]
                        elif provider == "azure":
                            resources["vm_name"] = deployment["vm_name"]
                            resources["resource_group"] = deployment["resource_group"]
                        elif provider in ["digitalocean", "hetzner"]:
                            resources["instance_name"] = deployment["instance_name"]
                            resources["instance_id"] = deployment["instance_id"]
                        
                        config = {
                            "instance_type": deployment.get("instance_type"),
                            "deployment_uid": deployment.get("deployment_uid"),
                        }
                        
                        tracker.add_deployment(
                            deployment_id,
                            deployment["provider"],
                            deployment["region"],
                            resources,
                            config
                        )
                        
                        imported_count += 1
                        logger.info(f"Imported deployment: {deployment_id}")
                    else:
                        logger.debug(f"Deployment already in inventory: {deployment['provider']}-{deployment['region']}")
                        
        except Exception as e:
            logger.error(f"Error importing deployments: {e}")
            
        return imported_count

    def _generate_deployment_id(self, deployment: Dict) -> str:
        """Generate a deployment ID for discovered resources"""
        provider = deployment["provider"]
        region = deployment["region"]
        uid = deployment.get("deployment_uid", "")
        
        if uid:
            return f"{provider}-{region}-{uid}"
        else:
            # Use timestamp from creation or discovery
            timestamp = deployment.get("created_at", deployment.get("discovered_at", ""))
            if timestamp:
                # Extract date portion
                date_str = timestamp.split("T")[0].replace("-", "")
                return f"{provider}-{region}-{date_str}-discovered"
            else:
                return f"{provider}-{region}-discovered"

    def sync_with_cloud(self, provider: Optional[str] = None) -> Dict:
        """Sync local inventory with cloud resources"""
        results = {
            "discovered": 0,
            "imported": 0,
            "already_known": 0,
            "deployments": {}
        }
        
        if provider:
            # Sync specific provider
            if provider == "aws":
                deployments = self.discover_aws_deployments()
                results["deployments"]["aws"] = deployments
            elif provider == "azure":
                deployments = self.discover_azure_deployments()
                results["deployments"]["azure"] = deployments
            elif provider == "digitalocean":
                deployments = self.discover_digitalocean_deployments()
                results["deployments"]["digitalocean"] = deployments
            elif provider == "hetzner":
                deployments = self.discover_hetzner_deployments()
                results["deployments"]["hetzner"] = deployments
            else:
                raise ValueError(f"Unknown provider: {provider}")
                
            results["discovered"] = len(deployments)
            results["imported"] = self.import_discovered_deployments({provider: deployments})
        else:
            # Sync all providers
            all_deployments = self.discover_all_deployments()
            results["deployments"] = all_deployments
            
            for provider_deps in all_deployments.values():
                results["discovered"] += len(provider_deps)
                
            results["imported"] = self.import_discovered_deployments(all_deployments)
        
        results["already_known"] = results["discovered"] - results["imported"]
        
        return results

    def get_remote_state(self, provider: str, region: str, deployment_id: Optional[str] = None) -> Optional[Dict]:
        """Get state information for a remote deployment"""
        state = None
        
        try:
            if provider == "aws":
                state = self._get_aws_state(region, deployment_id)
            elif provider == "azure":
                state = self._get_azure_state(region, deployment_id)
            elif provider == "digitalocean":
                state = self._get_digitalocean_state(region, deployment_id)
            elif provider == "hetzner":
                state = self._get_hetzner_state(region, deployment_id)
                
        except Exception as e:
            logger.error(f"Error getting remote state: {e}")
            
        return state

    def _get_aws_state(self, region: str, deployment_id: Optional[str] = None) -> Optional[Dict]:
        """Get AWS instance state"""
        try:
            filters = ["Name=tag:ManagedBy,Values=proxygen"]
            if deployment_id:
                filters.append(f"Name=tag:DeploymentUID,Values={deployment_id}")
            
            cmd = [
                "aws", "ec2", "describe-instances",
                "--region", region,
                "--filters"] + filters + [
                "--query", "Reservations[].Instances[]",
                "--output", "json"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            instances = json.loads(result.stdout)
            
            if instances:
                return instances[0]  # Return first matching instance
                
        except Exception as e:
            logger.error(f"Error getting AWS state: {e}")
            
        return None

    def _get_azure_state(self, region: str, deployment_id: Optional[str] = None) -> Optional[Dict]:
        """Get Azure VM state"""
        try:
            # Find resource groups in region
            cmd = [
                "az", "group", "list",
                "--query", f"[?location=='{region}' && tags.ManagedBy=='proxygen']",
                "--output", "json"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            resource_groups = json.loads(result.stdout)
            
            for rg in resource_groups:
                # Get VMs in resource group
                vm_cmd = [
                    "az", "vm", "list",
                    "--resource-group", rg["name"],
                    "--show-details",
                    "--output", "json"
                ]
                
                result = subprocess.run(vm_cmd, capture_output=True, text=True, check=True)
                vms = json.loads(result.stdout)
                
                if deployment_id:
                    # Filter by deployment ID
                    for vm in vms:
                        if vm.get("tags", {}).get("DeploymentUID") == deployment_id:
                            return vm
                elif vms:
                    return vms[0]  # Return first VM
                    
        except Exception as e:
            logger.error(f"Error getting Azure state: {e}")
            
        return None

    def _get_digitalocean_state(self, region: str, deployment_id: Optional[str] = None) -> Optional[Dict]:
        """Get DigitalOcean droplet state"""
        try:
            cmd = ["doctl", "compute", "droplet", "list", "--format", "Status", "--no-header"]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            if result.stdout.strip():
                return {"status": result.stdout.strip()}
            
        except Exception as e:
            logger.error(f"Error getting DigitalOcean state: {e}")
            
        return None
    
    def _get_hetzner_state(self, region: str, deployment_id: Optional[str] = None) -> Optional[Dict]:
        """Get Hetzner server state"""
        try:
            cmd = ["hcloud", "server", "list", "-o", "json"]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            servers = json.loads(result.stdout)
            
            for server in servers:
                if deployment_id and server.get("labels", {}).get("uid") == deployment_id:
                    return {"status": server["status"]}
                elif server["datacenter"]["location"]["name"] == region:
                    return {"status": server["status"]}
            
        except Exception as e:
            logger.error(f"Error getting Hetzner state: {e}")
            
        return None