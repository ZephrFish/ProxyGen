#!/usr/bin/env python3
"""
Advanced Configuration Features for ProxyGen
DNS-over-HTTPS, split tunneling, and custom routing
"""

import ipaddress
from typing import Dict, List, Optional


class AdvancedConfig:
    """Advanced WireGuard configuration features"""

    def __init__(self):
        self.dns_providers = {
            "cloudflare": {
                "servers": ["1.1.1.1", "1.0.0.1"],
                "doh_url": "https://cloudflare-dns.com/dns-query",
                "dot_hostname": "one.one.one.one",
            },
            "google": {
                "servers": ["8.8.8.8", "8.8.4.4"],
                "doh_url": "https://dns.google/dns-query",
                "dot_hostname": "dns.google",
            },
            "quad9": {
                "servers": ["9.9.9.9", "149.112.112.112"],
                "doh_url": "https://dns.quad9.net/dns-query",
                "dot_hostname": "dns.quad9.net",
            },
            "nextdns": {
                "servers": ["45.90.28.0", "45.90.30.0"],
                "doh_url": "https://dns.nextdns.io",
                "dot_hostname": "dns.nextdns.io",
            },
            "adguard": {
                "servers": ["94.140.14.14", "94.140.15.15"],
                "doh_url": "https://dns.adguard.com/dns-query",
                "dot_hostname": "dns.adguard.com",
            },
        }

        self.split_tunnel_presets = {
            "corporate": {
                "description": "Route only corporate traffic through Proxy",
                "include": ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"],
                "exclude": ["0.0.0.0/0"],
            },
            "streaming": {
                "description": "Exclude streaming services from Proxy",
                "include": ["0.0.0.0/0"],
                "exclude": self._get_streaming_cidrs(),
            },
            "gaming": {
                "description": "Exclude gaming services from Proxy",
                "include": ["0.0.0.0/0"],
                "exclude": self._get_gaming_cidrs(),
            },
            "privacy": {
                "description": "Route all traffic through Proxy except local",
                "include": ["0.0.0.0/0"],
                "exclude": ["192.168.0.0/16", "10.0.0.0/8"],
            },
            "custom": {
                "description": "Custom split tunneling configuration",
                "include": [],
                "exclude": [],
            },
        }

    def _get_streaming_cidrs(self) -> List[str]:
        """Get CIDR blocks for major streaming services"""
        return [
            # Netflix
            "45.57.0.0/17",
            "64.120.128.0/17",
            "66.197.128.0/17",
            "108.175.32.0/20",
            "185.2.220.0/22",
            "185.9.188.0/22",
            "192.173.64.0/18",
            "198.38.96.0/19",
            "198.45.48.0/20",
            "208.75.76.0/22",
            # YouTube
            "172.217.0.0/16",
            "172.253.0.0/16",
            "142.250.0.0/15",
            # Amazon Prime
            "52.0.0.0/8",
            "54.0.0.0/8",
            # Disney+
            "104.16.0.0/12",
            "172.64.0.0/13",
        ]

    def _get_gaming_cidrs(self) -> List[str]:
        """Get CIDR blocks for major gaming services"""
        return [
            # Steam
            "103.10.124.0/23",
            "103.28.54.0/23",
            "146.66.152.0/21",
            "155.133.224.0/19",
            "162.254.192.0/21",
            "185.25.180.0/22",
            "192.69.96.0/22",
            "205.185.194.0/24",
            "205.196.6.0/24",
            "208.64.200.0/22",
            # Xbox Live
            "40.0.0.0/8",
            "52.0.0.0/8",
            # PlayStation
            "108.160.0.0/12",
            "199.16.0.0/14",
            # Epic Games
            "3.0.0.0/8",
            "18.0.0.0/8",
        ]

    def configure_dns_over_https(self, provider: str = "cloudflare") -> Dict:
        """Configure DNS-over-HTTPS settings"""
        if provider not in self.dns_providers:
            raise ValueError(f"Unknown DNS provider: {provider}")

        dns_config = self.dns_providers[provider]

        # Generate systemd-resolved configuration
        resolved_config = f"""[Resolve]
DNS={' '.join(dns_config['servers'])}
FallbackDNS=1.1.1.1 8.8.8.8
Domains=~.
DNSSEC=yes
DNSOverTLS=yes
DNSStubListener=no
"""

        # Generate stubby configuration for DNS-over-TLS
        stubby_config = f"""resolution_type: GETDNS_RESOLUTION_STUB
dns_transport_list:
  - GETDNS_TRANSPORT_TLS
tls_authentication: GETDNS_AUTHENTICATION_REQUIRED
tls_query_padding_blocksize: 128
edns_client_subnet_private: 1
round_robin_upstreams: 1
idle_timeout: 10000
listen_addresses:
  - 127.0.0.1@53
  - 0::1@53
upstream_recursive_servers:
  - address_data: {dns_config['servers'][0]}
    tls_auth_name: "{dns_config['dot_hostname']}"
  - address_data: {dns_config['servers'][1]}
    tls_auth_name: "{dns_config['dot_hostname']}"
"""

        # Generate dnscrypt-proxy configuration
        dnscrypt_config = {
            "server_names": [f"{provider}-doh"],
            "listen_addresses": ["127.0.0.1:53"],
            "max_clients": 250,
            "ipv4_servers": True,
            "ipv6_servers": False,
            "dnscrypt_servers": True,
            "doh_servers": True,
            "require_dnssec": True,
            "require_nolog": True,
            "require_nofilter": True,
            "force_tcp": False,
            "timeout": 5000,
            "keepalive": 30,
            "cache": True,
            "cache_size": 4096,
            "cache_min_ttl": 2400,
            "cache_max_ttl": 86400,
            "sources": {
                "public-resolvers": {
                    "urls": [
                        "https://raw.githubusercontent.com/DNSCrypt/dnscrypt-resolvers/master/v3/public-resolvers.md"
                    ],
                    "cache_file": "/var/cache/dnscrypt-proxy/public-resolvers.md",
                    "minisign_key": "RWQf6LRCGA9i53mlYecO4IzT51TGPpvWucNSCh1CBM0QTaLn73Y7GFO3",
                }
            },
        }

        return {
            "provider": provider,
            "dns_servers": dns_config["servers"],
            "doh_url": dns_config["doh_url"],
            "resolved_config": resolved_config,
            "stubby_config": stubby_config,
            "dnscrypt_config": dnscrypt_config,
        }

    def configure_split_tunnel(
        self,
        mode: str = "corporate",
        custom_include: Optional[List[str]] = None,
        custom_exclude: Optional[List[str]] = None,
    ) -> Dict:
        """Configure split tunneling"""
        if mode not in self.split_tunnel_presets:
            raise ValueError(f"Unknown split tunnel mode: {mode}")

        config = self.split_tunnel_presets[mode].copy()

        if mode == "custom":
            config["include"] = custom_include or []
            config["exclude"] = custom_exclude or []

        # Validate CIDR blocks
        for cidr_list in [config["include"], config["exclude"]]:
            for cidr in cidr_list:
                try:
                    ipaddress.ip_network(cidr)
                except ValueError:
                    raise ValueError(f"Invalid CIDR block: {cidr}")

        # Generate routing rules
        routing_rules = self._generate_routing_rules(
            config["include"], config["exclude"]
        )

        return {
            "mode": mode,
            "description": config["description"],
            "include": config["include"],
            "exclude": config["exclude"],
            "routing_rules": routing_rules,
        }

    def _generate_routing_rules(self, include: List[str], exclude: List[str]) -> Dict:
        """Generate platform-specific routing rules"""
        # Linux routing rules
        linux_rules = {"up": [], "down": []}

        # Add routes for included networks
        for cidr in include:
            linux_rules["up"].append(f"ip route add {cidr} dev %i")
            linux_rules["down"].append(f"ip route del {cidr} dev %i")

        # Add exceptions for excluded networks
        for cidr in exclude:
            linux_rules["up"].append(
                f"ip route add {cidr} via $(ip route | grep default | awk '{{print $3}}')"
            )
            linux_rules["down"].append(f"ip route del {cidr}")

        # Windows routing rules
        windows_rules = {"up": [], "down": []}

        for cidr in include:
            windows_rules["up"].append(f"route add {cidr} 0.0.0.0 IF %i")
            windows_rules["down"].append(f"route delete {cidr}")

        # macOS routing rules
        macos_rules = {"up": [], "down": []}

        for cidr in include:
            macos_rules["up"].append(f"route add {cidr} -interface utun0")
            macos_rules["down"].append(f"route delete {cidr}")

        return {"linux": linux_rules, "windows": windows_rules, "macos": macos_rules}

    def generate_advanced_client_config(
        self,
        base_config: str,
        dns_config: Optional[Dict] = None,
        split_tunnel: Optional[Dict] = None,
        mtu: int = 1420,
        persistent_keepalive: int = 25,
    ) -> str:
        """Generate client configuration with advanced features"""
        lines = base_config.strip().split("\n")
        config_sections = {"interface": [], "peer": []}
        current_section = None

        # Parse existing configuration
        for line in lines:
            if line.startswith("[Interface]"):
                current_section = "interface"
            elif line.startswith("[Peer]"):
                current_section = "peer"
            elif current_section and line.strip():
                config_sections[current_section].append(line)

        # Update interface section
        interface_lines = ["[Interface]"]

        # Add existing interface settings
        for line in config_sections["interface"]:
            if not line.startswith(("DNS", "MTU", "PostUp", "PostDown")):
                interface_lines.append(line)

        # Add DNS configuration
        if dns_config:
            interface_lines.append(f"DNS = {', '.join(dns_config['dns_servers'])}")

        # Add MTU
        interface_lines.append(f"MTU = {mtu}")

        # Add split tunneling rules
        if split_tunnel and split_tunnel.get("routing_rules"):
            rules = split_tunnel["routing_rules"]["linux"]
            if rules["up"]:
                interface_lines.append(f"PostUp = {'; '.join(rules['up'])}")
            if rules["down"]:
                interface_lines.append(f"PostDown = {'; '.join(rules['down'])}")

        # Update peer section
        peer_lines = ["\n[Peer]"]

        # Add existing peer settings
        for line in config_sections["peer"]:
            if not line.startswith(("AllowedIPs", "PersistentKeepalive")):
                peer_lines.append(line)

        # Add AllowedIPs based on split tunneling
        if split_tunnel:
            allowed_ips = split_tunnel.get("include", ["0.0.0.0/0"])
        else:
            allowed_ips = ["0.0.0.0/0", "::/0"]

        peer_lines.append(f"AllowedIPs = {', '.join(allowed_ips)}")
        peer_lines.append(f"PersistentKeepalive = {persistent_keepalive}")

        # Combine sections
        return "\n".join(interface_lines + peer_lines)

    def create_kill_switch(self) -> Dict:
        """Create kill switch configuration"""
        # Linux iptables rules
        linux_rules = {
            "enable": [
                "iptables -I OUTPUT ! -o %i -m mark ! --mark $(wg show %i fwmark) -m addrtype ! --dst-type LOCAL -j REJECT",
                "ip6tables -I OUTPUT ! -o %i -m mark ! --mark $(wg show %i fwmark) -m addrtype ! --dst-type LOCAL -j REJECT",
            ],
            "disable": [
                "iptables -D OUTPUT ! -o %i -m mark ! --mark $(wg show %i fwmark) -m addrtype ! --dst-type LOCAL -j REJECT",
                "ip6tables -D OUTPUT ! -o %i -m mark ! --mark $(wg show %i fwmark) -m addrtype ! --dst-type LOCAL -j REJECT",
            ],
        }

        # Windows firewall rules
        windows_rules = {
            "enable": [
                'netsh advfirewall firewall add rule name="Proxy Kill Switch" dir=out action=block enable=yes',
                'netsh advfirewall firewall add rule name="Proxy Allow" dir=out action=allow enable=yes remoteip=%i',
            ],
            "disable": [
                'netsh advfirewall firewall delete rule name="Proxy Kill Switch"',
                'netsh advfirewall firewall delete rule name="Proxy Allow"',
            ],
        }

        # macOS pf rules
        macos_rules = {
            "enable": [
                'echo "block out all\\npass out on utun0" | sudo pfctl -f -',
                "sudo pfctl -e",
            ],
            "disable": ["sudo pfctl -d"],
        }

        return {"linux": linux_rules, "windows": windows_rules, "macos": macos_rules}

    def configure_multi_hop(self, entry_server: Dict, exit_server: Dict) -> Dict:
        """Configure multi-hop Proxy connection"""
        # Generate configuration for connecting through multiple servers
        config = {
            "entry": {
                "endpoint": f"{entry_server['public_ip']}:{entry_server['port']}",
                "public_key": entry_server["public_key"],
                "allowed_ips": [f"{exit_server['public_ip']}/32"],
            },
            "exit": {
                "endpoint": f"{exit_server['internal_ip']}:{exit_server['port']}",
                "public_key": exit_server["public_key"],
                "allowed_ips": ["0.0.0.0/0", "::/0"],
            },
        }

        return config
