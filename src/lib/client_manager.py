#!/usr/bin/env python3
"""
Advanced Client Management System for ProxyGen
Handles client lifecycle, IP allocation, and access control
"""

import json
import ipaddress
import subprocess
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import qrcode
from cryptography.hazmat.backends import default_backend


class ClientManager:
    """Advanced client management with database backing"""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.db_path = base_dir / "state" / "clients.db"
        self.configs_dir = base_dir / "configs"
        self.init_database()

    def init_database(self):
        """Initialise client database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create clients table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                email TEXT,
                public_key TEXT NOT NULL,
                private_key TEXT NOT NULL,
                preshared_key TEXT,
                ip_address TEXT NOT NULL,
                server_region TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP,
                enabled BOOLEAN DEFAULT 1,
                data_limit_gb INTEGER,
                data_used_gb REAL DEFAULT 0,
                expires_at TIMESTAMP,
                device_type TEXT,
                notes TEXT
            )
        """
        )

        # Create connections log table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS connection_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                disconnected_at TIMESTAMP,
                data_transferred_mb REAL,
                server_region TEXT,
                FOREIGN KEY (client_id) REFERENCES clients (id)
            )
        """
        )

        # Create IP allocations table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ip_allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subnet TEXT NOT NULL,
                ip_address TEXT UNIQUE NOT NULL,
                client_id INTEGER,
                allocated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES clients (id)
            )
        """
        )

        conn.commit()
        conn.close()

    def allocate_ip(self, subnet: str, server_region: str) -> Optional[str]:
        """Allocate next available IP address from subnet"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        network = ipaddress.ip_network(subnet)

        # Get all allocated IPs for this subnet
        cursor.execute(
            "SELECT ip_address FROM ip_allocations WHERE subnet = ?", (subnet,)
        )
        allocated_ips = {row[0] for row in cursor.fetchall()}

        # Find first available IP (skip .0 and .1)
        for ip in network.hosts():
            ip_str = str(ip)
            if ip_str.endswith(".0") or ip_str.endswith(".1"):
                continue
            if ip_str not in allocated_ips:
                conn.close()
                return ip_str

        conn.close()
        return None

    def generate_keys(self) -> Dict[str, str]:
        """Generate WireGuard key pair and preshared key"""
        # Generate private key
        private_key_cmd = subprocess.run(
            ["wg", "genkey"], capture_output=True, text=True
        )
        private_key = private_key_cmd.stdout.strip()

        # Generate public key
        public_key_cmd = subprocess.run(
            ["wg", "pubkey"], input=private_key, capture_output=True, text=True
        )
        public_key = public_key_cmd.stdout.strip()

        # Generate preshared key
        preshared_key_cmd = subprocess.run(
            ["wg", "genpsk"], capture_output=True, text=True
        )
        preshared_key = preshared_key_cmd.stdout.strip()

        return {
            "private": private_key,
            "public": public_key,
            "preshared": preshared_key,
        }

    def add_client(
        self,
        name: str,
        server_region: str,
        email: Optional[str] = None,
        device_type: Optional[str] = None,
        data_limit_gb: Optional[int] = None,
        expires_days: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> Dict:
        """Add a new client with advanced options"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check if client already exists
        cursor.execute("SELECT id FROM clients WHERE name = ?", (name,))
        if cursor.fetchone():
            conn.close()
            raise ValueError(f"Client {name} already exists")

        # Load server configuration
        server_config = self.load_server_config(server_region)
        if not server_config:
            conn.close()
            raise ValueError(f"Server configuration not found for {server_region}")

        # Generate keys
        keys = self.generate_keys()

        # Allocate IP address
        client_ip = self.allocate_ip(server_config["subnet"], server_region)
        if not client_ip:
            conn.close()
            raise ValueError("No available IP addresses in subnet")

        # Calculate expiry date if specified
        expires_at = None
        if expires_days:
            expires_at = datetime.now() + timedelta(days=expires_days)

        # Insert client record
        cursor.execute(
            """
            INSERT INTO clients (
                name, email, public_key, private_key, preshared_key,
                ip_address, server_region, device_type, data_limit_gb,
                expires_at, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                name,
                email,
                keys["public"],
                keys["private"],
                keys["preshared"],
                client_ip,
                server_region,
                device_type,
                data_limit_gb,
                expires_at,
                notes,
            ),
        )

        client_id = cursor.lastrowid

        # Record IP allocation
        cursor.execute(
            """
            INSERT INTO ip_allocations (subnet, ip_address, client_id)
            VALUES (?, ?, ?)
        """,
            (server_config["subnet"], client_ip, client_id),
        )

        conn.commit()
        conn.close()

        # Generate configuration file
        config_content = self.generate_client_config(
            name, keys, client_ip, server_config
        )

        # Save configuration
        config_file = self.configs_dir / f"client-{name}.conf"
        with open(config_file, "w") as f:
            f.write(config_content)

        # Generate QR code
        self.generate_qr_code(config_file)

        # Update server configuration
        self.update_server_config(server_region, name, keys["public"], client_ip)

        return {
            "name": name,
            "ip_address": client_ip,
            "config_file": str(config_file),
            "qr_code": str(config_file.with_suffix(".png")),
            "expires_at": expires_at.isoformat() if expires_at else None,
        }

    def generate_client_config(
        self, name: str, keys: Dict, client_ip: str, server_config: Dict
    ) -> str:
        """Generate WireGuard client configuration"""
        config = f"""# ProxyGen Client Configuration
# Name: {name}
# Generated: {datetime.now().isoformat()}

[Interface]
PrivateKey = {keys['private']}
Address = {client_ip}/32
DNS = {', '.join(server_config.get('dns', ['1.1.1.1', '1.0.0.1']))}

[Peer]
PublicKey = {server_config['public_key']}
PresharedKey = {keys['preshared']}
Endpoint = {server_config['public_ip']}:{server_config['wireguard_port']}
AllowedIPs = 0.0.0.0/0, ::/0
PersistentKeepalive = 25
"""
        return config

    def load_server_config(self, server_region: str) -> Optional[Dict]:
        """Load server configuration from file"""
        for config_file in self.configs_dir.glob("*-server.json"):
            if server_region in config_file.name:
                with open(config_file, "r") as f:
                    return json.load(f)
        return None

    def update_server_config(
        self,
        server_region: str,
        client_name: str,
        client_public_key: str,
        client_ip: str,
    ):
        """Update server's WireGuard configuration with new client"""
        # This would typically use Ansible to update the server
        # For now, we'll create a peer configuration file
        peer_config = f"""
# Client: {client_name}
[Peer]
PublicKey = {client_public_key}
AllowedIPs = {client_ip}/32
"""

        peer_file = self.configs_dir / f"peer-{server_region}-{client_name}.conf"
        with open(peer_file, "w") as f:
            f.write(peer_config)

    def generate_qr_code(self, config_file: Path):
        """Generate QR code for configuration file"""
        with open(config_file, "r") as f:
            config_text = f.read()

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(config_text)
        qr.make(fit=True)

        img = qr.make_image(fill_colour="black", back_colour="white")
        qr_file = config_file.with_suffix(".png")
        img.save(qr_file)

    def revoke_client(self, name: str) -> bool:
        """Revoke client access"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("UPDATE clients SET enabled = 0 WHERE name = ?", (name,))

        affected = cursor.rowcount
        conn.commit()
        conn.close()

        return affected > 0

    def list_clients(self, active_only: bool = False) -> List[Dict]:
        """List all clients with their status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = """
            SELECT name, email, ip_address, server_region, created_at,
                   last_seen, enabled, data_limit_gb, data_used_gb,
                   expires_at, device_type
            FROM clients
        """

        if active_only:
            query += " WHERE enabled = 1"

        cursor.execute(query)

        clients = []
        for row in cursor.fetchall():
            clients.append(
                {
                    "name": row[0],
                    "email": row[1],
                    "ip_address": row[2],
                    "server_region": row[3],
                    "created_at": row[4],
                    "last_seen": row[5],
                    "enabled": bool(row[6]),
                    "data_limit_gb": row[7],
                    "data_used_gb": row[8],
                    "expires_at": row[9],
                    "device_type": row[10],
                }
            )

        conn.close()
        return clients

    def get_client_stats(self, name: str) -> Dict:
        """Get detailed statistics for a client"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get client details
        cursor.execute(
            """
            SELECT * FROM clients WHERE name = ?
        """,
            (name,),
        )

        client = cursor.fetchone()
        if not client:
            conn.close()
            return {}

        # Get connection history
        cursor.execute(
            """
            SELECT connected_at, disconnected_at, data_transferred_mb
            FROM connection_logs
            WHERE client_id = ?
            ORDER BY connected_at DESC
            LIMIT 10
        """,
            (client[0],),
        )

        connections = cursor.fetchall()

        conn.close()

        return {
            "client": {
                "name": client[1],
                "ip_address": client[5],
                "created_at": client[7],
                "last_seen": client[8],
                "data_used_gb": client[10],
            },
            "connections": [
                {
                    "connected_at": conn[0],
                    "disconnected_at": conn[1],
                    "data_transferred_mb": conn[2],
                }
                for conn in connections
            ],
        }

    def cleanup_expired_clients(self):
        """Remove expired client configurations"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE clients
            SET enabled = 0
            WHERE expires_at IS NOT NULL
            AND expires_at < datetime('now')
        """
        )

        affected = cursor.rowcount
        conn.commit()
        conn.close()

        return affected

    def export_clients(self, format: str = "json") -> str:
        """Export client configurations"""
        clients = self.list_clients()

        if format == "json":
            return json.dumps(clients, indent=2, default=str)
        elif format == "csv":
            import csv
            import io

            output = io.StringIO()
            if clients:
                writer = csv.DictWriter(output, fieldnames=clients[0].keys())
                writer.writeheader()
                writer.writerows(clients)
            return output.getvalue()
        else:
            raise ValueError(f"Unsupported format: {format}")
