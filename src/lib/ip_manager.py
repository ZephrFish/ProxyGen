#!/usr/bin/env python3
"""
IP Address Management for ProxyGen
Handles dynamic IP allocation and prevents IP address conflicts
"""

import json
import time
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional


class IPManager:
    """Manages IP address allocation and prevents reuse conflicts"""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.state_dir = base_dir / "state"
        self.ip_registry = self.state_dir / "ip_registry.json"
        self.load_ip_registry()

    def load_ip_registry(self):
        """Load IP address registry"""
        if self.ip_registry.exists():
            with open(self.ip_registry, "r") as f:
                self.registry = json.load(f)
        else:
            self.registry = {
                "elastic_ips": {},
                "server_ips": {},
                "client_subnets": {},
                "last_updated": datetime.now().isoformat()
            }
            self.save_ip_registry()

    def save_ip_registry(self):
        """Save IP address registry"""
        self.registry["last_updated"] = datetime.now().isoformat()
        with open(self.ip_registry, "w") as f:
            json.dump(self.registry, f, indent=2, default=str)

    def register_deployment_ip(self, deployment_id: str, provider: str, 
                             region: str, public_ip: str):
        """Register an IP address for a deployment"""
        key = f"{provider}-{region}-{deployment_id}"
        self.registry["elastic_ips"][key] = {
            "public_ip": public_ip,
            "deployment_id": deployment_id,
            "provider": provider,
            "region": region,
            "allocated_at": datetime.now().isoformat(),
            "status": "active"
        }
        self.save_ip_registry()

    def release_deployment_ip(self, deployment_id: str):
        """Release IP address when deployment is destroyed"""
        for key, ip_info in list(self.registry["elastic_ips"].items()):
            if ip_info["deployment_id"] == deployment_id:
                ip_info["status"] = "released"
                ip_info["released_at"] = datetime.now().isoformat()
                break
        self.save_ip_registry()

    def check_ip_conflicts(self, provider: str, region: str) -> List[str]:
        """Check for active IP addresses in the same region"""
        active_ips = []
        for key, ip_info in self.registry["elastic_ips"].items():
            if (ip_info["provider"] == provider and 
                ip_info["region"] == region and 
                ip_info["status"] == "active"):
                active_ips.append(ip_info["public_ip"])
        return active_ips

    def generate_client_subnet(self, deployment_id: str) -> str:
        """Generate a unique client subnet for a deployment"""
        # Use deployment timestamp to ensure uniqueness
        timestamp = int(time.time())
        
        # Generate subnet based on timestamp (avoid common ranges)
        # Use 10.x.x.0/24 where x is derived from timestamp
        subnet_base = (timestamp % 200) + 10  # Range 10-209
        subnet_second = (timestamp // 200) % 255
        
        subnet = f"10.{subnet_base}.{subnet_second}.0/24"
        
        # Ensure it's not already used
        while subnet in self.registry["client_subnets"].values():
            subnet_base = (subnet_base + 1) % 200 + 10
            subnet = f"10.{subnet_base}.{subnet_second}.0/24"
        
        self.registry["client_subnets"][deployment_id] = subnet
        self.save_ip_registry()
        return subnet

    def get_deployment_info(self, deployment_id: str) -> Optional[Dict]:
        """Get IP information for a deployment"""
        for key, ip_info in self.registry["elastic_ips"].items():
            if ip_info["deployment_id"] == deployment_id:
                return ip_info
        return None

    def cleanup_old_ips(self, max_age_days: int = 30):
        """Clean up old released IP entries"""
        cutoff_date = datetime.now() - timedelta(days=max_age_days)
        
        for key in list(self.registry["elastic_ips"].keys()):
            ip_info = self.registry["elastic_ips"][key]
            if ip_info["status"] == "released" and "released_at" in ip_info:
                released_date = datetime.fromisoformat(ip_info["released_at"])
                if released_date < cutoff_date:
                    del self.registry["elastic_ips"][key]
        
        self.save_ip_registry()

    def force_new_ip_allocation(self, deployment_id: str):
        """Force allocation of a new IP by marking current as avoid"""
        existing = self.get_deployment_info(deployment_id)
        if existing:
            existing["status"] = "avoid"
            existing["avoid_reason"] = "forced_new_allocation"
            self.save_ip_registry()

    def get_ip_usage_report(self) -> Dict:
        """Generate IP usage report"""
        active_count = sum(1 for ip in self.registry["elastic_ips"].values() 
                          if ip["status"] == "active")
        released_count = sum(1 for ip in self.registry["elastic_ips"].values() 
                           if ip["status"] == "released")
        
        return {
            "total_ips": len(self.registry["elastic_ips"]),
            "active_ips": active_count,
            "released_ips": released_count,
            "client_subnets": len(self.registry["client_subnets"]),
            "last_updated": self.registry["last_updated"]
        }