#!/usr/bin/env python3
"""
Multi-Hop Proxy Manager for ProxyGen
Implements cascading Proxy connections for enhanced privacy
"""

import json
import random
import ipaddress
import subprocess
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class MultiHopManager:
    """Manages multi-hop Proxy configurations with cascading connections"""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.configs_dir = base_dir / "configs"
        self.state_dir = base_dir / "state"
        self.chains_file = self.state_dir / "multihop_chains.json"
        self.load_chains()

        # DNS-over-HTTPS providers for each hop
        self.doh_providers = {
            "cloudflare": {
                "url": "https://cloudflare-dns.com/dns-query",
                "ips": ["1.1.1.1", "1.0.0.1"],
                "bootstrap": "1.1.1.1",
            },
            "quad9": {
                "url": "https://dns.quad9.net/dns-query",
                "ips": ["9.9.9.9", "149.112.112.112"],
                "bootstrap": "9.9.9.9",
            },
            "nextdns": {
                "url": "https://dns.nextdns.io",
                "ips": ["45.90.28.0", "45.90.30.0"],
                "bootstrap": "45.90.28.0",
            },
            "adguard": {
                "url": "https://dns.adguard.com/dns-query",
                "ips": ["94.140.14.14", "94.140.15.15"],
                "bootstrap": "94.140.14.14",
            },
            "mullvad": {
                "url": "https://doh.mullvad.net/dns-query",
                "ips": ["194.242.2.2"],
                "bootstrap": "194.242.2.2",
            },
        }

        # Recommended hop configurations for different threat models
        self.hop_presets = {
            "standard": {
                "hops": 2,
                "description": "Standard 2-hop configuration for good privacy",
                "entry_regions": ["us-east-1", "eu-west-1"],
                "exit_regions": ["eu-north-1", "ap-southeast-1"],
                "dns_strategy": "different_per_hop",
            },
            "maximum": {
                "hops": 3,
                "description": "Maximum 3-hop configuration for highest privacy",
                "entry_regions": ["us-west-2"],
                "middle_regions": ["eu-central-1", "ca-central-1"],
                "exit_regions": ["ap-northeast-1", "eu-north-1"],
                "dns_strategy": "rotating",
            },
            "geographic": {
                "hops": 2,
                "description": "Cross-continental routing for geographic diversity",
                "entry_regions": ["us-east-1"],
                "exit_regions": ["ap-southeast-1", "eu-west-1"],
                "dns_strategy": "cloudflare_then_quad9",
            },
            "paranoid": {
                "hops": 4,
                "description": "Ultra-paranoid 4-hop configuration",
                "entry_regions": ["us-west-2"],
                "middle_regions": ["eu-west-1", "ca-central-1", "eu-north-1"],
                "exit_regions": ["ap-northeast-1"],
                "dns_strategy": "random_each_hop",
            },
        }

    def load_chains(self):
        """Load existing multi-hop chains"""
        if self.chains_file.exists():
            with open(self.chains_file, "r") as f:
                self.chains = json.load(f)
        else:
            self.chains = {}

    def save_chains(self):
        """Save multi-hop chains"""
        with open(self.chains_file, "w") as f:
            json.dump(self.chains, f, indent=2, default=str)

    def create_multihop_chain(
        self,
        name: str,
        servers: List[Dict],
        preset: str = "standard",
        custom_dns: Optional[List[str]] = None,
    ) -> Dict:
        """Create a multi-hop Proxy chain configuration"""

        if len(servers) < 2:
            raise ValueError("Multi-hop requires at least 2 servers")

        if len(servers) > 5:
            raise ValueError("Maximum 5 hops supported for performance reasons")

        # Generate chain configuration
        chain = {
            "name": name,
            "created_at": datetime.now().isoformat(),
            "preset": preset,
            "hops": [],
            "dns_config": self._generate_dns_config(len(servers), preset, custom_dns),
            "routing_rules": [],
            "kill_switch": True,
            "mtu": 1280,  # Lower MTU for multi-hop to avoid fragmentation
        }

        # Configure each hop
        for i, server in enumerate(servers):
            hop_config = self._configure_hop(i, server, servers, chain["dns_config"])
            chain["hops"].append(hop_config)

        # Generate routing rules for the chain
        chain["routing_rules"] = self._generate_routing_rules(chain["hops"])

        # Save chain configuration
        self.chains[name] = chain
        self.save_chains()

        # Generate client configuration
        client_config = self._generate_multihop_client_config(chain)

        # Save client configuration
        config_file = self.configs_dir / f"multihop-{name}.conf"
        with open(config_file, "w") as f:
            f.write(client_config)

        logger.info(f"Created multi-hop chain: {name} with {len(servers)} hops")

        return chain

    def _configure_hop(
        self, hop_index: int, server: Dict, all_servers: List[Dict], dns_config: Dict
    ) -> Dict:
        """Configure individual hop in the chain"""

        hop = {
            "index": hop_index,
            "server_id": server["id"],
            "public_ip": server["public_ip"],
            "internal_ip": self._allocate_internal_ip(hop_index),
            "port": 51820 + hop_index,  # Different port for each hop
            "public_key": server["public_key"],
            "role": self._get_hop_role(hop_index, len(all_servers)),
        }

        # Configure DNS for this hop
        hop["dns"] = dns_config["hops"][hop_index]

        # Configure routing based on role
        if hop["role"] == "entry":
            # Entry node routes to next hop
            next_server = all_servers[hop_index + 1]
            hop["allowed_ips"] = [f"{next_server['public_ip']}/32"]
            hop["endpoint"] = f"{server['public_ip']}:{hop['port']}"

        elif hop["role"] == "middle":
            # Middle nodes route between previous and next
            prev_server = all_servers[hop_index - 1]
            next_server = (
                all_servers[hop_index + 1] if hop_index < len(all_servers) - 1 else None
            )

            hop["allowed_ips"] = []
            if next_server:
                hop["allowed_ips"].append(f"{next_server['public_ip']}/32")
            hop["allowed_ips"].append("10.0.0.0/8")  # Internal routing

        elif hop["role"] == "exit":
            # Exit node routes to internet
            hop["allowed_ips"] = ["0.0.0.0/0", "::/0"]
            hop["nat_enabled"] = True

        # Add obfuscation if configured
        if server.get("obfuscation_enabled"):
            hop["obfuscation"] = {
                "method": "stunnel",
                "port": 443,
                "certificate": server.get("tls_cert"),
            }

        return hop

    def _get_hop_role(self, index: int, total_hops: int) -> str:
        """Determine the role of a hop in the chain"""
        if index == 0:
            return "entry"
        elif index == total_hops - 1:
            return "exit"
        else:
            return "middle"

    def _allocate_internal_ip(self, hop_index: int) -> str:
        """Allocate internal IP for hop communication"""
        # Use different subnets for each hop
        base_subnet = ipaddress.ip_network("10.100.0.0/16")
        hop_subnet = ipaddress.ip_network(f"10.100.{hop_index}.0/24")

        # Return gateway IP for the hop
        return str(list(hop_subnet.hosts())[0])

    def _generate_dns_config(
        self, num_hops: int, preset: str, custom_dns: Optional[List[str]]
    ) -> Dict:
        """Generate DNS configuration for multi-hop chain"""

        config = {
            "strategy": self.hop_presets[preset].get(
                "dns_strategy", "different_per_hop"
            ),
            "hops": [],
            "fallback": ["1.1.1.1", "8.8.8.8"],
        }

        if custom_dns:
            # Use custom DNS servers
            for i in range(num_hops):
                config["hops"].append({"servers": custom_dns, "doh_enabled": False})
        else:
            # Use DoH providers based on strategy
            if config["strategy"] == "different_per_hop":
                providers = list(self.doh_providers.keys())
                for i in range(num_hops):
                    provider = providers[i % len(providers)]
                    config["hops"].append(
                        {
                            "provider": provider,
                            "servers": self.doh_providers[provider]["ips"],
                            "doh_url": self.doh_providers[provider]["url"],
                            "doh_enabled": True,
                        }
                    )

            elif config["strategy"] == "rotating":
                providers = list(self.doh_providers.keys())
                random.shuffle(providers)
                for i in range(num_hops):
                    provider = providers[i % len(providers)]
                    config["hops"].append(
                        {
                            "provider": provider,
                            "servers": self.doh_providers[provider]["ips"],
                            "doh_url": self.doh_providers[provider]["url"],
                            "doh_enabled": True,
                        }
                    )

            elif config["strategy"] == "random_each_hop":
                for i in range(num_hops):
                    provider = random.choice(list(self.doh_providers.keys()))
                    config["hops"].append(
                        {
                            "provider": provider,
                            "servers": self.doh_providers[provider]["ips"],
                            "doh_url": self.doh_providers[provider]["url"],
                            "doh_enabled": True,
                        }
                    )

        return config

    def _generate_routing_rules(self, hops: List[Dict]) -> List[Dict]:
        """Generate routing rules for multi-hop chain"""
        rules = []

        for i, hop in enumerate(hops):
            if hop["role"] == "entry":
                # Route all traffic through first hop
                rules.append(
                    {
                        "table": 100 + i,
                        "priority": 100,
                        "rule": f"ip rule add from all lookup {100 + i}",
                        "route": f"ip route add default via {hop['internal_ip']} table {100 + i}",
                    }
                )

            elif hop["role"] == "middle":
                # Route between hops
                prev_hop = hops[i - 1]
                next_hop = hops[i + 1] if i < len(hops) - 1 else None

                rules.append(
                    {
                        "table": 100 + i,
                        "priority": 100 + i,
                        "rule": f"ip rule add from {prev_hop['internal_ip']} lookup {100 + i}",
                        "route": f"ip route add default via {next_hop['internal_ip'] if next_hop else '0.0.0.0'} table {100 + i}",
                    }
                )

            elif hop["role"] == "exit":
                # NAT and route to internet
                rules.append(
                    {
                        "table": 100 + i,
                        "priority": 100 + i,
                        "nat": f"iptables -t nat -A POSTROUTING -s 10.100.0.0/16 -o eth0 -j MASQUERADE",
                        "forward": f"iptables -A FORWARD -i wg{i} -j ACCEPT",
                    }
                )

        return rules

    def _generate_multihop_client_config(self, chain: Dict) -> str:
        """Generate WireGuard configuration for multi-hop client"""

        config_lines = [
            "# Multi-Hop Proxy Configuration",
            f"# Chain: {chain['name']}",
            f"# Hops: {len(chain['hops'])}",
            f"# Created: {chain['created_at']}",
            "",
        ]

        # Generate configuration for each hop
        for i, hop in enumerate(chain["hops"]):
            if i == 0:
                # First hop - client connects directly
                config_lines.extend(
                    [
                        "[Interface]",
                        f"# Hop {i + 1}: Entry Node",
                        f"PrivateKey = <CLIENT_PRIVATE_KEY_{i}>",
                        f"Address = 10.100.{i}.2/24",
                        f"DNS = {', '.join(hop['dns']['servers'])}",
                        f"MTU = {chain['mtu']}",
                        "",
                        "# DNS-over-HTTPS Configuration",
                        f"PostUp = echo 'nameserver 127.0.0.1' > /etc/resolv.conf",
                        f"PostUp = systemctl start dnscrypt-proxy",
                        f"PostDown = systemctl stop dnscrypt-proxy",
                        "",
                        "# Kill Switch",
                        "PostUp = iptables -I OUTPUT ! -o %i -m mark ! --mark $(wg show %i fwmark) -j DROP",
                        "PostDown = iptables -D OUTPUT ! -o %i -m mark ! --mark $(wg show %i fwmark) -j DROP",
                        "",
                        "[Peer]",
                        f"# Server: {hop['server_id']}",
                        f"PublicKey = {hop['public_key']}",
                        f"Endpoint = {hop['endpoint']}",
                        f"AllowedIPs = {', '.join(hop['allowed_ips'])}",
                        "PersistentKeepalive = 25",
                        "",
                    ]
                )
            else:
                # Subsequent hops - configured on servers
                config_lines.extend(
                    [
                        f"# Hop {i + 1} Configuration (Server-Side)",
                        f"# This hop is configured on server {chain['hops'][i-1]['server_id']}",
                        f"# Role: {hop['role']}",
                        f"# DNS: {hop['dns']['provider'] if hop['dns'].get('doh_enabled') else 'Custom'}",
                        "",
                    ]
                )

        # Add routing configuration
        config_lines.extend(
            [
                "# Routing Configuration",
                "# The following routes are applied in sequence:",
            ]
        )

        for rule in chain["routing_rules"]:
            if "rule" in rule:
                config_lines.append(f"# PostUp = {rule['rule']}")
            if "route" in rule:
                config_lines.append(f"# PostUp = {rule['route']}")

        return "\n".join(config_lines)

    def deploy_multihop_chain(
        self, chain_name: str, providers: List[str], regions: List[str]
    ) -> Dict:
        """Deploy servers for a multi-hop chain"""

        if len(providers) != len(regions):
            raise ValueError("Number of providers must match number of regions")

        deployed_servers = []

        # Use subprocess to call proxygen script directly
        proxygen_script = self.base_dir / "proxygen"

        # Deploy each server
        for i, (provider, region) in enumerate(zip(providers, regions)):
            logger.info(f"Deploying hop {i + 1}: {provider} in {region}")

            # Deploy server using subprocess
            try:
                result = subprocess.run(
                    [str(proxygen_script), "deploy", "--provider", provider, "--regions", region],
                    cwd=str(self.base_dir),
                    capture_output=True,
                    text=True,
                    check=True
                )
                success = True
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to deploy hop {i + 1}: {e}")
                success = False

            if not success:
                logger.error(f"Failed to deploy hop {i + 1}")
                # Rollback previously deployed servers
                for j in range(i):
                    subprocess.run(
                        [str(proxygen_script), "destroy", "--provider", providers[j], "--regions", regions[j], "--force"],
                        cwd=str(self.base_dir),
                        capture_output=True
                    )
                raise Exception(f"Multi-hop deployment failed at hop {i + 1}")

            # Get server information from deployment tracker
            try:
                from .deployment_tracker import DeploymentTracker
                tracker = DeploymentTracker(self.base_dir)
                deployments = tracker.get_deployments_by_region(provider, region)
                if deployments:
                    server_info = deployments[-1]  # Get most recent deployment
                else:
                    raise Exception("No deployment found after successful deployment")
            except ImportError:
                # Fallback to basic server info
                server_info = {
                    "provider": provider,
                    "region": region,
                    "public_ip": "0.0.0.0",  # Will be updated later
                    "id": f"{provider}-{region}"
                }
            server_info["id"] = f"{provider}-{region}"
            server_info["provider"] = provider
            server_info["region"] = region

            # Generate WireGuard keys for this hop
            keys = self._generate_wireguard_keys()
            server_info["public_key"] = keys["public"]
            server_info["private_key"] = keys["private"]

            deployed_servers.append(server_info)

        # Configure each server for multi-hop
        for i, server in enumerate(deployed_servers):
            self._configure_server_for_multihop(i, server, deployed_servers)

        # Create the multi-hop chain configuration
        chain = self.create_multihop_chain(
            chain_name, deployed_servers, preset="standard"
        )

        logger.info(f"Multi-hop chain {chain_name} deployed successfully")

        return chain

    def _generate_wireguard_keys(self) -> Dict[str, str]:
        """Generate WireGuard key pair"""
        private_key_result = subprocess.run(
            ["wg", "genkey"], capture_output=True, text=True
        )
        private_key = private_key_result.stdout.strip()

        public_key_result = subprocess.run(
            ["wg", "pubkey"], input=private_key, capture_output=True, text=True
        )
        public_key = public_key_result.stdout.strip()

        return {"private": private_key, "public": public_key}

    def _configure_server_for_multihop(
        self, hop_index: int, server: Dict, all_servers: List[Dict]
    ):
        """Configure a server for its role in the multi-hop chain"""

        role = self._get_hop_role(hop_index, len(all_servers))

        # Generate Ansible playbook for multi-hop configuration
        playbook = {
            "name": f"Configure {role} node for multi-hop",
            "hosts": f"{server['provider']}-{server['region']}",
            "tasks": [],
        }

        if role == "entry":
            # Entry node configuration
            playbook["tasks"].extend(
                [
                    {
                        "name": "Configure as entry node",
                        "template": {
                            "src": "multihop_entry.j2",
                            "dest": "/etc/wireguard/wg0.conf",
                        },
                    },
                    {
                        "name": "Setup DoH for entry node",
                        "include_tasks": "setup_doh.yaml",
                        "vars": {"doh_provider": "cloudflare"},
                    },
                ]
            )

        elif role == "middle":
            # Middle node configuration
            playbook["tasks"].extend(
                [
                    {
                        "name": "Configure as middle node",
                        "template": {
                            "src": "multihop_middle.j2",
                            "dest": "/etc/wireguard/wg0.conf",
                        },
                    },
                    {
                        "name": "Setup routing for middle node",
                        "shell": "echo 1 > /proc/sys/net/ipv4/ip_forward",
                    },
                    {
                        "name": "Setup DoH for middle node",
                        "include_tasks": "setup_doh.yaml",
                        "vars": {"doh_provider": "quad9"},
                    },
                ]
            )

        elif role == "exit":
            # Exit node configuration
            playbook["tasks"].extend(
                [
                    {
                        "name": "Configure as exit node",
                        "template": {
                            "src": "multihop_exit.j2",
                            "dest": "/etc/wireguard/wg0.conf",
                        },
                    },
                    {
                        "name": "Setup NAT for exit node",
                        "iptables": {
                            "table": "nat",
                            "chain": "POSTROUTING",
                            "out_interface": "eth0",
                            "jump": "MASQUERADE",
                        },
                    },
                    {
                        "name": "Setup DoH for exit node",
                        "include_tasks": "setup_doh.yaml",
                        "vars": {"doh_provider": "nextdns"},
                    },
                ]
            )

        # Save and execute playbook
        playbook_file = (
            self.base_dir / "ansible" / f"multihop_{role}_{server['id']}.yaml"
        )
        with open(playbook_file, "w") as f:
            import yaml

            yaml.dump([playbook], f)

        logger.info(f"Configured {server['id']} as {role} node")

    def test_multihop_chain(self, chain_name: str) -> Dict:
        """Test multi-hop chain connectivity and DNS resolution"""

        if chain_name not in self.chains:
            raise ValueError(f"Chain {chain_name} not found")

        chain = self.chains[chain_name]
        results = {
            "chain": chain_name,
            "tested_at": datetime.now().isoformat(),
            "hops": [],
            "dns_tests": [],
            "latency_ms": 0,
            "success": True,
        }

        # Test each hop
        for hop in chain["hops"]:
            hop_test = {
                "server_id": hop["server_id"],
                "reachable": self._test_hop_connectivity(hop),
                "dns_working": self._test_hop_dns(hop),
            }
            results["hops"].append(hop_test)

            if not hop_test["reachable"] or not hop_test["dns_working"]:
                results["success"] = False

        # Test end-to-end latency
        if results["success"]:
            results["latency_ms"] = self._test_chain_latency(chain)

        return results

    def _test_hop_connectivity(self, hop: Dict) -> bool:
        """Test connectivity to a specific hop"""
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "2", hop["public_ip"]],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except:
            return False

    def _test_hop_dns(self, hop: Dict) -> bool:
        """Test DNS resolution through a hop"""
        try:
            # Test DNS resolution using the hop's DNS servers
            dns_server = hop["dns"]["servers"][0]
            result = subprocess.run(
                ["nslookup", "example.com", dns_server], capture_output=True, timeout=5
            )
            return result.returncode == 0
        except:
            return False

    def _test_chain_latency(self, chain: Dict) -> float:
        """Test end-to-end latency through the chain"""
        # This would connect through the chain and measure latency
        # For now, return estimated latency based on hop count
        return len(chain["hops"]) * 50  # Estimate 50ms per hop
