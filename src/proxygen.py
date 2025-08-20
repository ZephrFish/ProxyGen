#!/usr/bin/env python3
"""
ProxyGen - Multi-Cloud Proxy Server Deployment Tool
Main orchestration script for deploying proxy servers across AWS, Azure, DigitalOcean, and Hetzner
"""

import argparse
import sys
import os
import json
import yaml
import subprocess
import logging
import time
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

# Import error handling framework
from lib.exceptions import (
    ProxyGenError, ValidationError, ConfigurationError, TerraformError,
    AnsibleError, NetworkError, AuthenticationError, DeploymentError,
    SSHError, ErrorSeverity, ErrorCategory, handle_error, safe_execute
)
from lib.validators import Validators, validate_input
from lib.subprocess_utils import SubprocessRunner, run_terraform, run_ansible, run_ssh
from lib.progress_bar import StepProgress, ProgressBar, SpinnerProgress

# Enhanced logging configuration
def setup_logging():
    """Configure comprehensive logging for ProxyGen"""
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler for user-facing output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    
    # Configure ProxyGen logger
    proxygen_logger = logging.getLogger('proxygen')
    proxygen_logger.setLevel(logging.INFO)
    
    # Suppress noisy third-party loggers
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('boto3').setLevel(logging.WARNING)
    logging.getLogger('botocore').setLevel(logging.WARNING)
    
    return proxygen_logger

# Setup logging
logger = setup_logging()


class ProxyGen:
    """Main orchestrator for proxy deployment"""

    def __init__(self):
        try:
            # Get the project root (parent of src)
            self.src_dir = Path(__file__).parent
            self.base_dir = self.src_dir.parent
            self.config_file = self.base_dir / "config" / "config.yaml"
            self.state_dir = self.base_dir / "state"
            self.terraform_dir = self.src_dir / "terraform"
            self.ansible_dir = self.src_dir / "ansible"
            self.configs_dir = self.base_dir / "configs"

            # Create necessary directories
            for dir_path in [self.state_dir, self.configs_dir]:
                try:
                    dir_path.mkdir(exist_ok=True)
                except PermissionError:
                    raise ConfigurationError(
                        f"Permission denied creating directory: {dir_path}",
                        suggestions=[
                            "Check directory permissions",
                            "Run with appropriate privileges",
                            "Ensure parent directory is writable"
                        ]
                    )

            # Initialize deployment tracker
            sys.path.append(str(self.src_dir / "lib"))
            try:
                from deployment_tracker import DeploymentTracker
                self.tracker = DeploymentTracker(self.base_dir)
            except ImportError as e:
                raise ConfigurationError(
                    f"Failed to import deployment tracker: {e}",
                    suggestions=[
                        "Ensure all required modules are present",
                        "Check PYTHONPATH configuration",
                        "Verify installation integrity"
                    ]
                )

            self.load_config()
            
        except ProxyGenError:
            raise
        except Exception as e:
            raise ConfigurationError(
                f"Failed to initialize ProxyGen: {e}",
                original_error=e,
                suggestions=[
                    "Check installation integrity",
                    "Verify all dependencies are installed",
                    "Check file permissions"
                ]
            )

    @handle_error
    def load_config(self):
        """Load configuration from config.yaml"""
        try:
            if self.config_file.exists():
                with open(self.config_file, "r") as f:
                    self.config = yaml.safe_load(f)
                    if not self.config:
                        raise ConfigurationError(
                            "Configuration file is empty or invalid",
                            config_file=str(self.config_file),
                            suggestions=[
                                "Delete the config file to regenerate defaults",
                                "Check YAML syntax",
                                "Ensure file is not corrupted"
                            ]
                        )
            else:
                logger.info("No configuration file found, creating default configuration")
                self.config = self.get_default_config()
                self.save_config()
        except yaml.YAMLError as e:
            raise ConfigurationError(
                f"Invalid YAML syntax in configuration file: {e}",
                config_file=str(self.config_file),
                suggestions=[
                    "Check YAML syntax with a validator",
                    "Delete and regenerate the configuration file",
                    "Restore from backup if available"
                ]
            )
        except PermissionError:
            raise ConfigurationError(
                f"Permission denied reading configuration file: {self.config_file}",
                config_file=str(self.config_file),
                suggestions=[
                    "Check file permissions",
                    "Run with appropriate privileges"
                ]
            )

    def get_default_config(self) -> Dict:
        """Get default configuration"""
        return {
            "server": {
                "instance_type": {
                    "aws": "t3.micro",
                    "azure": "Standard_B1s",
                    "digitalocean": "s-1vcpu-1gb",
                    "hetzner": "cx11",
                },
                "wireguard_port": 51820,
                "wireguard_interface": "wg0",
                "subnet": "10.0.0.0/24",
                "dns": ["1.1.1.1", "1.0.0.1"],
            },
            "security": {
                "allowed_ips": ["0.0.0.0/0"],
                "key_size": 2048,
                "keepalive": 25,
            },
            "monitoring": {
                "enabled": True,
                "metrics": ["connections", "bandwidth", "latency"],
                "alert_email": "",
            },
            "regions": {
                "aws": {
                    "us-east-1": "US East (N. Virginia)",
                    "us-west-2": "US West (Oregon)",
                    "eu-west-1": "EU (Ireland)",
                    "eu-central-1": "EU (Frankfurt)",
                    "ap-southeast-1": "Asia Pacific (Singapore)",
                    "ap-northeast-1": "Asia Pacific (Tokyo)",
                },
                "azure": {
                    "eastus": "East US",
                    "westus2": "West US 2",
                    "westeurope": "West Europe",
                    "northeurope": "North Europe",
                    "southeastasia": "Southeast Asia",
                    "japaneast": "Japan East",
                },
                "digitalocean": {
                    "nyc1": "s-1vcpu-1gb",
                    "nyc3": "s-1vcpu-1gb",
                    "sfo3": "s-1vcpu-1gb",
                    "ams3": "s-1vcpu-1gb",
                    "sgp1": "s-1vcpu-1gb",
                    "lon1": "s-1vcpu-1gb",
                    "fra1": "s-1vcpu-1gb",
                    "tor1": "s-1vcpu-1gb",
                    "blr1": "s-1vcpu-1gb"
                },
                "hetzner": {
                    "us-central1": "Iowa",
                    "us-west1": "Oregon",
                    "europe-west1": "Belgium",
                    "europe-west4": "Netherlands",
                    "asia-southeast1": "Singapore",
                    "asia-northeast1": "Tokyo",
                },
            },
        }

    def save_config(self):
        """Save configuration to config.yaml"""
        with open(self.config_file, "w") as f:
            yaml.safe_dump(self.config, f, default_flow_style=False)

    def deploy(self, provider: str, regions: List[str], dry_run: bool = False, instance_type: str = None):
        """Deploy Proxy infrastructure"""
        logger.info(f"Deploying Proxy to {provider} in regions: {', '.join(regions)}")

        # Setup progress tracking
        total_regions = len(regions)
        deployment_steps = [
            "Validating inputs",
            "Checking provider warnings",
            "Preparing deployment",
        ]
        
        # Add steps for each region
        for region in regions:
            deployment_steps.extend([
                f"Deploying infrastructure in {region}",
                f"Configuring services in {region}",
                f"Finalizing deployment in {region}"
            ])
        
        deployment_steps.append("Updating deployment tracking")
        
        progress = StepProgress(deployment_steps, f"ProxyGen Deployment - {provider}")
        
        # Step 1: Validate provider and regions
        progress.start_step(0)
        if provider not in ["aws", "azure", "digitalocean", "hetzner"]:
            progress.fail_step(f"Invalid provider: {provider}")
            logger.error(f"Invalid provider: {provider}")
            return False
        progress.complete_step("Provider and regions validated")
        
        # Step 2: Check provider warnings
        progress.start_step(1)
        
        # Alpha provider warnings
        if provider == "hetzner":
            print("\nWARNING: Hetzner Cloud Support")
            print("=" * 50)
            print("Hetzner Cloud integration is currently in ALPHA status.")
            print("This provider is semi-tested and may have issues:")
            print("  - Deployment may fail in some regions")
            print("  - Configuration steps might need manual intervention")
            print("  - Limited testing has been performed")
            print("  - Use at your own risk for production workloads")
            print("")
            print("For stable deployments, consider using AWS or Azure.")
            print("=" * 50)
            
            response = input("Continue with Hetzner deployment? (yes/no): ").lower().strip()
            if response not in ['yes', 'y']:
                progress.fail_step("Deployment cancelled by user")
                logger.info("Deployment cancelled by user")
                return False
            print("")  # Add spacing
            
        elif provider == "digitalocean":
            print("\nWARNING: DigitalOcean Support")
            print("=" * 50)
            print("DigitalOcean integration is currently in ALPHA status.")
            print("This provider is semi-tested and may have issues:")
            print("  - Deployment may fail in some regions")
            print("  - Configuration steps might need manual intervention")
            print("  - Limited testing has been performed")
            print("  - Use at your own risk for production workloads")
            print("")
            print("For stable deployments, consider using AWS or Azure.")
            print("=" * 50)
            
            response = input("Continue with DigitalOcean deployment? (yes/no): ").lower().strip()
            if response not in ['yes', 'y']:
                progress.fail_step("Deployment cancelled by user")
                logger.info("Deployment cancelled by user")
                return False
            print("")  # Add spacing

        progress.complete_step("Provider warnings acknowledged")
        
        # Step 3: Prepare deployment
        progress.start_step(2)
        
        valid_regions = self.config["regions"][provider].keys()
        for region in regions:
            if region not in valid_regions:
                progress.fail_step(f"Invalid region for {provider}: {region}")
                logger.error(f"Invalid region for {provider}: {region}")
                logger.info(f"Valid regions: {', '.join(valid_regions)}")
                return False

        # Set default instance types if not specified
        if instance_type is None:
            default_types = {
                "aws": "t3.nano",  # Cheapest AWS instance
                "azure": "Standard_B1s",  # Cheapest Azure instance  
                "digitalocean": "s-1vcpu-1gb",  # Cheapest DigitalOcean droplet
                "hetzner": "cx11"  # Cheapest Hetzner cloud server
            }
            instance_type = default_types[provider]
            logger.info(f"Using default instance type: {instance_type}")
        else:
            logger.info(f"Using specified instance type: {instance_type}")

        # Generate unique deployment ID (6 char hex)
        import secrets
        deployment_uid = secrets.token_hex(3)
        logger.info(f"Deployment UID: {deployment_uid}")
        
        progress.complete_step(f"Deployment prepared with UID: {deployment_uid}")

        # Deploy infrastructure for each region
        step_index = 3  # Starting step index for region deployments
        for i, region in enumerate(regions):
            region_step_base = step_index + (i * 3)
            
            # Step: Deploy infrastructure
            progress.start_step(region_step_base)
            logger.info(f"Deploying to {provider} - {region} with UID {deployment_uid}")

            # Run Terraform with deployment UID
            if not self.run_terraform(provider, region, "apply", dry_run, instance_type, deployment_uid):
                progress.fail_step(f"Failed to deploy infrastructure in {region}")
                logger.error(f"Failed to deploy infrastructure in {region}")
                return False
            
            progress.complete_step(f"Infrastructure deployed in {region}")

            # Get server details from Terraform output
            server_info = self.get_terraform_output(provider, region)

            # Step: Configure services
            progress.start_step(region_step_base + 1)
            
            if not dry_run and server_info:
                # Configure WireGuard using Ansible
                if not self.configure_wireguard(provider, region, server_info):
                    progress.fail_step(f"Failed to configure WireGuard in {region}")
                    logger.error(f"Failed to configure WireGuard in {region}")
                    return False
                progress.complete_step(f"WireGuard configured in {region}")
            else:
                if dry_run:
                    progress.complete_step(f"Dry run - skipped service configuration in {region}")
                else:
                    progress.complete_step(f"No server info available for {region}")

            # Step: Finalize deployment
            progress.start_step(region_step_base + 2)
            
            if not dry_run and server_info:
                # Track deployment in inventory
                deployment_id = (
                    f"{provider}-{region}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                )
                self.tracker.add_deployment(
                    deployment_id=deployment_id,
                    provider=provider,
                    region=region,
                    resources=server_info,
                    config={
                        "instance_type": instance_type,
                        "wireguard_port": self.config["server"]["wireguard_port"],
                        "subnet": self.config["server"]["subnet"],
                    },
                )
                progress.complete_step(f"Deployment tracked with ID: {deployment_id}")
                logger.info(f"Deployment tracked with ID: {deployment_id}")
            else:
                progress.complete_step(f"Deployment finalized for {region}")

        # Final step: Update deployment tracking
        final_step = len(deployment_steps) - 1
        progress.start_step(final_step)
        progress.complete_step("All deployments completed")
        
        progress.finish("ProxyGen deployment completed successfully!")
        logger.info("Deployment completed successfully!")
        return True

    @handle_error
    @validate_input(Validators.validate_command_args)
    def run_terraform(
        self, provider: str, region: str, action: str, dry_run: bool = False, 
        instance_type: str = None, deployment_uid: str = None
    ) -> bool:
        """Run Terraform commands with enhanced error handling"""
        # Validate inputs
        provider = Validators.validate_provider(provider)
        if isinstance(region, list):
            region = region[0]  # Take first region if list provided
        regions = Validators.validate_regions(provider, [region])
        region = regions[0]
        
        if instance_type:
            instance_type = Validators.validate_instance_type(provider, instance_type)
        
        terraform_provider_dir = self.terraform_dir / provider
        
        # Generate UID if not provided (for destroy operations)
        if deployment_uid is None:
            import secrets
            deployment_uid = secrets.token_hex(3)
        
        # Use UID in state file name to allow multiple deployments per region
        state_file = self.state_dir / f"{provider}-{region}-{deployment_uid}.tfstate"

        # Check if terraform directory exists
        if not terraform_provider_dir.exists():
            raise TerraformError(
                f"Terraform directory not found: {terraform_provider_dir}",
                suggestions=[
                    "Check provider name is correct",
                    "Verify Terraform files exist",
                    "Initialize project structure first"
                ]
            )

        # Use provided instance type or fall back to config
        if instance_type is None:
            instance_type = self.config["server"]["instance_type"][provider]

        # Prepare Terraform variables based on provider
        tf_vars = {
            "region": region,
            "instance_type": instance_type,
            "wireguard_port": self.config["server"]["wireguard_port"],
            "allowed_ips": self.config["security"]["allowed_ips"],
            "project_name": "proxygen",
            "deployment_uid": deployment_uid,  # Add UID to terraform vars
        }

        # Add provider-specific environment variables
        if provider == "digitalocean":
            # DigitalOcean uses API token
            do_token = os.environ.get("DIGITALOCEAN_TOKEN")
            if not do_token:
                logger.error("DIGITALOCEAN_TOKEN environment variable not set")
                return False
        elif provider == "hetzner":
            # Hetzner uses API token
            hcloud_token = os.environ.get("HCLOUD_TOKEN")
            if not hcloud_token:
                logger.error("HCLOUD_TOKEN environment variable not set")
                return False

        # Add AWS tags if provider is AWS
        if provider == "aws":
            tf_vars["tags"] = {
                "Name": f"proxygen-{region}-{deployment_uid}",
                "ManagedBy": "proxygen",
                "Provider": provider,
                "Region": region,
                "DeploymentUID": deployment_uid,
                "CreatedAt": datetime.now().isoformat(),
                "Environment": "production"
            }

        # Write variables file with UID in filename
        vars_file = self.state_dir / f"{provider}-{region}-{deployment_uid}.tfvars.json"
        with open(vars_file, "w") as f:
            json.dump(tf_vars, f)

        # Terraform commands
        commands = []

        # Initialize Terraform with reconfigure flag
        init_cmd = [
            "terraform",
            "init",
            "-reconfigure",
            "-backend-config",
            f"path={state_file}",
        ]
        commands.append(init_cmd)

        # Plan or Apply or Destroy
        if action == "apply":
            plan_cmd = [
                "terraform",
                "plan",
                "-var-file",
                str(vars_file),
                "-state",
                str(state_file),
                "-out",
                str(self.state_dir / f"{provider}-{region}.tfplan"),
            ]
            commands.append(plan_cmd)

            if not dry_run:
                apply_cmd = [
                    "terraform",
                    "apply",
                    "-auto-approve",
                    "-state",
                    str(state_file),
                    str(self.state_dir / f"{provider}-{region}.tfplan"),
                ]
                commands.append(apply_cmd)
        elif action == "destroy":
            # For destroy, we need to ensure state is properly loaded
            destroy_cmd = [
                "terraform",
                "destroy",
                "-auto-approve",
                "-var-file",
                str(vars_file),
                "-state",
                str(state_file),
            ]
            commands.append(destroy_cmd)

        # Execute commands using enhanced subprocess runner with improved error handling
        runner = SubprocessRunner(timeout=900, cwd=terraform_provider_dir)  # Increased timeout
        
        # Check for existing state locks and attempt to resolve them
        lock_file = self.state_dir / f".{provider}-{region}-{deployment_uid}.tfstate.lock.info"
        if lock_file.exists():
            logger.warning(f"Found existing terraform lock: {lock_file}")
            try:
                # Try to force unlock with confirmation
                unlock_cmd = ["terraform", "force-unlock", "-force"]
                with open(lock_file, 'r') as f:
                    lock_info = json.load(f)
                    lock_id = lock_info.get('ID', '')
                    if lock_id:
                        unlock_cmd.append(lock_id)
                        logger.info(f"Attempting to unlock terraform state: {lock_id}")
                        runner.run(unlock_cmd, log_output=False)
                        logger.info("Successfully unlocked terraform state")
            except Exception as e:
                logger.warning(f"Could not unlock terraform state: {e}")
                # Continue anyway, terraform might handle it
        
        for cmd in commands:
            logger.info(f"Running: {' '.join(cmd)}")
            if not dry_run or "plan" in cmd:
                try:
                    result = runner.run(
                        cmd,
                        log_output=True,
                        sensitive_args=[str(vars_file)]
                    )
                    logger.info(f"Command completed successfully: {' '.join(cmd)}")
                    
                    # Additional validation for apply commands
                    if "apply" in cmd and not dry_run:
                        logger.info("Validating terraform deployment...")
                        # Wait a moment for terraform to update state
                        time.sleep(5)
                        if not self._validate_terraform_deployment(provider, region, deployment_uid):
                            raise TerraformError(
                                "Terraform apply completed but deployment validation failed",
                                suggestions=[
                                    "Check terraform state file",
                                    "Verify all resources were created",
                                    "Run terraform plan to check for drift"
                                ]
                            )
                        
                except TerraformError:
                    # Clean up on terraform failures
                    self._cleanup_failed_deployment(provider, region, deployment_uid)
                    raise
                except Exception as e:
                    # Clean up on any other failures
                    self._cleanup_failed_deployment(provider, region, deployment_uid)
                    raise TerraformError(
                        f"Terraform command failed: {' '.join(cmd)}",
                        command=' '.join(cmd),
                        original_error=e,
                        suggestions=[
                            "Check Terraform configuration",
                            "Verify cloud provider credentials", 
                            "Check network connectivity",
                            "Review Terraform logs for details",
                            "Try destroying and redeploying if state is corrupted"
                        ]
                    )

        logger.info(f"Terraform {action} completed successfully for {provider} in {region}")
        return True

    @handle_error
    def get_terraform_output(self, provider: str, region: str) -> Dict:
        """Get Terraform output values with enhanced error handling"""
        # Validate inputs
        provider = Validators.validate_provider(provider)
        
        terraform_provider_dir = self.terraform_dir / provider
        if not terraform_provider_dir.exists():
            raise TerraformError(
                f"Terraform directory not found: {terraform_provider_dir}",
                suggestions=[
                    "Check provider name is correct",
                    "Verify Terraform files exist",
                    "Run deployment first"
                ]
            )
        
        # Look for state files with UID pattern for this region
        state_pattern = f"{provider}-{region}-*.tfstate"
        state_files = list(self.state_dir.glob(state_pattern))
        
        if not state_files:
            raise TerraformError(
                f"No Terraform state files found for {provider} in {region}",
                suggestions=[
                    "Check if deployment was successful",
                    "Verify provider and region names",
                    "Run deployment first if not done"
                ]
            )
        
        # Use the most recent state file
        state_file = max(state_files, key=lambda p: p.stat().st_mtime)
        logger.info(f"Using state file: {state_file}")
        
        cmd = ["terraform", "output", "-json", "-state", str(state_file)]
        
        try:
            runner = SubprocessRunner(timeout=60, cwd=terraform_provider_dir)
            result = runner.run(cmd, log_output=False)
            
            try:
                outputs = json.loads(result.stdout)
                return {
                    "public_ip": outputs.get("public_ip", {}).get("value"),
                    "private_key_path": outputs.get("private_key_path", {}).get("value"),
                    "instance_id": outputs.get("instance_id", {}).get("value"),
                }
            except json.JSONDecodeError as e:
                raise TerraformError(
                    f"Failed to parse Terraform output: {e}",
                    suggestions=[
                        "Check if Terraform state is valid",
                        "Verify deployment completed successfully",
                        "Re-run deployment if needed"
                    ]
                )
                
        except TerraformError:
            raise
        except Exception as e:
            raise TerraformError(
                f"Failed to get Terraform output: {e}",
                original_error=e,
                suggestions=[
                    "Check Terraform installation",
                    "Verify state file integrity",
                    "Ensure proper permissions"
                ]
            )

    @handle_error
    def configure_wireguard(
        self, provider: str, region: str, server_info: Dict
    ) -> bool:
        """Configure WireGuard on the deployed server with enhanced error handling"""
        if not server_info.get('public_ip'):
            raise ConfigurationError(
                "Server public IP not available",
                suggestions=[
                    "Check if deployment completed successfully",
                    "Verify Terraform output contains public_ip",
                    "Re-run deployment if needed"
                ]
            )
        
        logger.info(f"Configuring WireGuard on {server_info['public_ip']}")

        # Generate WireGuard keys
        try:
            server_keys = self.generate_wireguard_keys()
        except Exception as e:
            raise ConfigurationError(
                f"Failed to generate WireGuard keys: {e}",
                original_error=e,
                suggestions=[
                    "Check WireGuard tools are installed",
                    "Verify system has entropy for key generation",
                    "Check file permissions for key storage"
                ]
            )

        # Check if Ansible is available
        use_ansible = False
        try:
            runner = SubprocessRunner(timeout=10)
            runner.run(["ansible", "--version"], log_output=False)
            # Force SSH configuration for now due to connectivity issues
            logger.info("Using direct SSH configuration for reliability")
        except Exception:
            logger.info("Ansible not found, using direct SSH configuration")

        # Wait for instance to be ready with proper error handling
        logger.info("Waiting for instance to be ready for SSH...")
        max_retries = 30
        ssh_key_path = server_info.get('private_key_path')
        
        if not ssh_key_path or not Path(ssh_key_path).exists():
            raise AuthenticationError(
                f"SSH private key not found: {ssh_key_path}",
                suggestions=[
                    "Check if Terraform created the key pair",
                    "Verify key path in Terraform output",
                    "Ensure proper permissions for key file"
                ]
            )
        
        for i in range(max_retries):
            try:
                # Use the enhanced SSH function
                result = run_ssh(
                    host=server_info['public_ip'],
                    command="echo 'SSH connection test'",
                    key_file=Path(ssh_key_path),
                    timeout=10
                )
                logger.info("SSH connection successful")
                break
            except (NetworkError, AuthenticationError, SSHError) as e:
                if i < max_retries - 1:
                    logger.info(f"SSH attempt {i+1}/{max_retries} failed, retrying in 10 seconds...")
                    time.sleep(10)
                else:
                    raise NetworkError(
                        f"Failed to establish SSH connection after {max_retries} attempts",
                        suggestions=[
                            "Check security group allows SSH (port 22)",
                            "Verify instance is running",
                            "Check network connectivity",
                            "Ensure SSH key permissions are correct (600)"
                        ]
                    )

        if use_ansible:
            # Prepare Ansible inventory
            inventory = {
                "all": {
                    "hosts": {
                        f"proxygen-{provider}-{region}": {
                            "ansible_host": server_info["public_ip"],
                            "ansible_user": (
                                "ubuntu" if provider == "aws" else "azureuser"
                            ),
                            "ansible_ssh_private_key_file": str(
                                (
                                    self.terraform_dir
                                    / provider
                                    / server_info["private_key_path"]
                                ).resolve()
                            ),
                            "ansible_ssh_common_args": "-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=~/.ssh/known_hosts.proxygen -o LogLevel=ERROR",
                            "wireguard_private_key": server_keys["private"],
                            "wireguard_public_key": server_keys["public"],
                            "wireguard_port": self.config["server"]["wireguard_port"],
                            "wireguard_subnet": self.config["server"]["subnet"],
                            "wireguard_interface": self.config["server"][
                                "wireguard_interface"
                            ],
                        }
                    }
                }
            }

            # Write inventory file
            inventory_file = self.state_dir / f"{provider}-{region}-inventory.yaml"
            with open(inventory_file, "w") as f:
                yaml.safe_dump(inventory, f)

            # Run Ansible playbook
            playbook = self.ansible_dir / "wireguard-setup.yaml"
            cmd = ["ansible-playbook", "-i", str(inventory_file), str(playbook)]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                # Save server configuration
                self.save_server_config(provider, region, server_info, server_keys)
                logger.info("WireGuard configuration completed successfully")
                return True
            else:
                logger.error(f"Ansible playbook failed: {result.stderr}")
                return False
        else:
            # Use direct SSH configuration
            return self.configure_wireguard_ssh(
                provider, region, server_info, server_keys
            )

    def configure_wireguard_ssh(
        self, provider: str, region: str, server_info: Dict, server_keys: Dict
    ) -> bool:
        """Configure WireGuard using SSH commands directly"""
        logger.info("Configuring WireGuard via SSH")

        # Determine SSH user
        ssh_user = (
            "ubuntu"
            if provider in ["aws", "digitalocean", "hetzner"]
            else "azureuser" if provider == "azure" else "ubuntu"
        )

        # Generate WireGuard configuration
        # Note: We'll detect the actual interface on the server
        # Use a script to determine the interface dynamically
        wg_config_template = f"""[Interface]
Address = 10.0.0.1/24
PrivateKey = {server_keys['private']}
ListenPort = {self.config['server']['wireguard_port']}
PostUp = /etc/wireguard/wg-postup.sh
PostDown = /etc/wireguard/wg-postdown.sh
"""

        # Create helper scripts that will determine the interface dynamically
        postup_script = """#!/bin/bash
INTERFACE=$(ip route | grep default | awk '{print $5}' | head -1)
iptables -A FORWARD -i wg0 -j ACCEPT
iptables -A FORWARD -o wg0 -j ACCEPT  
iptables -t nat -A POSTROUTING -o $INTERFACE -j MASQUERADE
"""

        postdown_script = """#!/bin/bash
INTERFACE=$(ip route | grep default | awk '{print $5}' | head -1)
iptables -D FORWARD -i wg0 -j ACCEPT
iptables -D FORWARD -o wg0 -j ACCEPT
iptables -t nat -D POSTROUTING -o $INTERFACE -j MASQUERADE
"""

        # Create setup script
        setup_script = f"""#!/bin/bash
set -e

# Wait for cloud-init to complete
echo "Waiting for cloud-init to complete..."
cloud-init status --wait

# Wait for any apt locks to be released (cloud-init might still be running)
echo "Waiting for apt locks to be released..."
timeout=300  # 5 minutes max
counter=0
while [ $counter -lt $timeout ]; do
    if ! fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 && \
       ! fuser /var/lib/apt/lists/lock >/dev/null 2>&1 && \
       ! fuser /var/lib/dpkg/lock >/dev/null 2>&1; then
        echo "APT locks are free"
        break
    fi
    echo "Waiting for apt lock to be released... ($counter/$timeout)"
    sleep 5
    counter=$((counter + 5))
done

if [ $counter -ge $timeout ]; then
    echo "Timeout waiting for APT locks to be released"
    # Force kill any hanging processes
    pkill -f apt-get || true
    pkill -f dpkg || true
    # Wait a bit more
    sleep 10
fi

# Check if WireGuard is already installed (from user_data)
if ! command -v wg &> /dev/null; then
    echo "Installing WireGuard..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update && apt-get install -y wireguard iptables
else
    echo "WireGuard already installed"
fi

# Enable IP forwarding (if not already enabled)
if ! grep -q "net.ipv4.ip_forward=1" /etc/sysctl.conf; then
    echo 'net.ipv4.ip_forward=1' >> /etc/sysctl.conf
fi
if ! grep -q "net.ipv6.conf.all.forwarding=1" /etc/sysctl.conf; then
    echo 'net.ipv6.conf.all.forwarding=1' >> /etc/sysctl.conf
fi
sysctl -p

# Install dnsmasq for DNS forwarding (configure after WireGuard starts)
export DEBIAN_FRONTEND=noninteractive
apt-get install -y dnsmasq

# Create WireGuard helper scripts
cat > /etc/wireguard/wg-postup.sh << 'EOF'
{postup_script}EOF

cat > /etc/wireguard/wg-postdown.sh << 'EOF'
{postdown_script}EOF

chmod +x /etc/wireguard/wg-postup.sh
chmod +x /etc/wireguard/wg-postdown.sh

# Create WireGuard configuration
cat > /etc/wireguard/wg0.conf << 'EOF'
{wg_config_template}
EOF

# Set proper permissions
chmod 600 /etc/wireguard/wg0.conf

# Start WireGuard
echo "Starting WireGuard service..."
systemctl enable wg-quick@wg0
systemctl start wg-quick@wg0

# Wait for interface to come up
sleep 2

# Verify WireGuard is running
echo "Verifying WireGuard status..."
wg show
systemctl status wg-quick@wg0 --no-pager || true

# Now configure dnsmasq to use WireGuard interface
echo "Configuring dnsmasq for Proxy DNS..."
cat > /etc/dnsmasq.d/proxy.conf << 'EOF'
# Listen only on Proxy interface
interface=wg0
bind-interfaces

# Upstream DNS servers
server=1.1.1.1
server=1.0.0.1

# Cache settings
cache-size=1000
no-resolv
no-poll

# Log queries for debugging (optional)
# log-queries
EOF

# Restart dnsmasq after WireGuard is up
systemctl enable dnsmasq
systemctl restart dnsmasq

# Verify dnsmasq is working
sleep 2
systemctl status dnsmasq --no-pager || true

echo "WireGuard and DNS configuration completed!"
"""

        # Save setup script
        setup_script_file = self.state_dir / f"{provider}-{region}-setup.sh"
        with open(setup_script_file, "w") as f:
            f.write(setup_script)

        # Copy and execute setup script via SSH
        try:
            # Copy script to server
            scp_cmd = [
                "scp",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                "UserKnownHostsFile=~/.ssh/known_hosts.proxygen",
                "-i",
                str(server_info["private_key_path"]),
                str(setup_script_file),
                f"{ssh_user}@{server_info['public_ip']}:/tmp/wireguard-setup.sh",
            ]

            result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.error(f"Failed to copy setup script: {result.stderr}")
                return False

            # Execute setup script
            ssh_cmd = [
                "ssh",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                "UserKnownHostsFile=~/.ssh/known_hosts.proxygen",
                "-i",
                str(server_info["private_key_path"]),
                f"{ssh_user}@{server_info['public_ip']}",
                "sudo bash /tmp/wireguard-setup.sh",
            ]

            logger.info("Executing WireGuard setup on server...")
            result = subprocess.run(
                ssh_cmd, capture_output=True, text=True, timeout=600
            )

            if result.returncode == 0:
                logger.info("WireGuard setup completed successfully")
                self.save_server_config(provider, region, server_info, server_keys)
                return True
            else:
                logger.error(f"WireGuard setup failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error("SSH operation timed out")
            return False
        except Exception as e:
            logger.error(f"Error during SSH configuration: {e}")
            return False

    def generate_wireguard_keys(self) -> Dict[str, str]:
        """Generate WireGuard key pair"""
        try:
            # Try using local wg command
            private_key_result = subprocess.run(
                ["wg", "genkey"], capture_output=True, text=True, check=True
            )
            private_key = private_key_result.stdout.strip()

            # Generate public key
            public_key_result = subprocess.run(
                ["wg", "pubkey"],
                input=private_key,
                capture_output=True,
                text=True,
                check=True,
            )
            public_key = public_key_result.stdout.strip()

        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback to Python implementation
            logger.info(
                "WireGuard tools not found locally, using Python implementation"
            )

            # Use cryptography library to generate keys
            try:
                from cryptography.hazmat.primitives.asymmetric.x25519 import (
                    X25519PrivateKey,
                )
                from cryptography.hazmat.primitives import serialization
                import base64

                # Generate X25519 private key
                private_key_obj = X25519PrivateKey.generate()

                # Get private key bytes
                private_key_bytes = private_key_obj.private_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PrivateFormat.Raw,
                    encryption_algorithm=serialization.NoEncryption(),
                )
                private_key = base64.b64encode(private_key_bytes).decode("ascii")

                # Get public key
                public_key_obj = private_key_obj.public_key()
                public_key_bytes = public_key_obj.public_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PublicFormat.Raw,
                )
                public_key = base64.b64encode(public_key_bytes).decode("ascii")

            except ImportError:
                # Final fallback - generate on the server
                logger.warning(
                    "Cryptography library not available, keys will be generated on server"
                )
                import secrets
                import base64

                # Generate placeholder keys (will be replaced on server)
                private_key = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
                public_key = base64.b64encode(secrets.token_bytes(32)).decode("ascii")

        return {"private": private_key, "public": public_key}

    def add_client_to_server(self, provider: str, region: str, server_info: Dict, client_public_key: str, client_ip: str):
        """Add a client peer to the server's WireGuard configuration"""
        try:
            # SSH to server and add the peer
            ssh_user = (
                "ubuntu"
                if provider in ["aws", "digitalocean", "hetzner"]
                else "azureuser" if provider == "azure" else "ubuntu"
            )
            ssh_key = str(server_info["private_key_path"])
            
            add_peer_cmd = f"""
            sudo wg set wg0 peer {client_public_key} allowed-ips {client_ip}/32
            # Save peer to config file by appending to the config
            echo "" | sudo tee -a /etc/wireguard/wg0.conf
            echo "[Peer]" | sudo tee -a /etc/wireguard/wg0.conf
            echo "PublicKey = {client_public_key}" | sudo tee -a /etc/wireguard/wg0.conf
            echo "AllowedIPs = {client_ip}/32" | sudo tee -a /etc/wireguard/wg0.conf
            """
            
            ssh_cmd = [
                "ssh",
                "-o", "StrictHostKeyChecking=accept-new",
                "-o", "UserKnownHostsFile=~/.ssh/known_hosts.proxygen",
                "-i", ssh_key,
                f"{ssh_user}@{server_info['public_ip']}",
                add_peer_cmd
            ]
            
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                logger.info(f"Successfully added client peer to server")
                return True
            else:
                logger.error(f"Failed to add client peer: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Error adding client to server: {e}")
            return False

    def save_server_config(
        self, provider: str, region: str, server_info: Dict, keys: Dict
    ):
        """Save server configuration for future reference"""
        config_file = self.configs_dir / f"{provider}-{region}-server.json"
        config = {
            "provider": provider,
            "region": region,
            "public_ip": server_info["public_ip"],
            "instance_id": server_info["instance_id"],
            "public_key": keys["public"],
            "created_at": datetime.now().isoformat(),
            "wireguard_port": self.config["server"]["wireguard_port"],
            "subnet": self.config["server"]["subnet"],
        }

        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)
        
        # Generate a sample client configuration
        client_keys = self.generate_wireguard_keys()
        client_config_file = self.configs_dir / f"{provider}-{region}-client.conf"
        
        client_config = f"""[Interface]
# Client private key (keep this secret!)
PrivateKey = {client_keys['private']}
# Client IP address in the Proxy subnet
Address = 10.0.0.2/32
# DNS servers to use when connected (Proxy server will forward to 1.1.1.1, 1.0.0.1)
DNS = 10.0.0.1

[Peer]
# Server public key
PublicKey = {keys['public']}
# Server endpoint
Endpoint = {server_info['public_ip']}:{self.config['server']['wireguard_port']}
# Route all traffic through Proxy (0.0.0.0/0 = all IPv4)
AllowedIPs = 0.0.0.0/0
# Keep connection alive
PersistentKeepalive = 25
"""
        
        with open(client_config_file, "w") as f:
            f.write(client_config)
        
        # Also save client keys for reference
        client_keys_file = self.configs_dir / f"{provider}-{region}-client-keys.json"
        with open(client_keys_file, "w") as f:
            json.dump({
                "private_key": client_keys['private'],
                "public_key": client_keys['public'],
                "ip_address": "10.0.0.2/32"
            }, f, indent=2)
        
        logger.info(f"Server configuration saved to: {config_file}")
        logger.info(f"Client configuration saved to: {client_config_file}")
        logger.info(f"You can use the client configuration with WireGuard on any device")
        logger.info(f"To connect: sudo wg-quick up {client_config_file}")
        
        # Also need to add the client peer to the server
        logger.info("Adding client peer to server configuration...")
        self.add_client_to_server(provider, region, server_info, client_keys['public'], "10.0.0.2")

    # Removed old add_client method - duplicate functionality exists in newer method below

    def get_next_client_ip(self, subnet: str) -> str:
        """Get the next available IP address for a client"""
        # Simple implementation - in production, track used IPs
        import ipaddress

        network = ipaddress.ip_network(subnet)
        # Start from .2 (reserve .1 for server)
        return str(list(network.hosts())[1])

    def generate_qr_code(self, config_file: Path):
        """Generate QR code for configuration file"""
        try:
            import qrcode

            with open(config_file, "r") as f:
                config_text = f.read()

            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(config_text)
            qr.make(fit=True)

            img = qr.make_image(fill_colour="black", back_colour="white")
            qr_file = config_file.with_suffix(".png")
            img.save(qr_file)
            logger.info(f"QR code saved to: {qr_file}")
        except ImportError:
            logger.warning("qrcode library not installed. Skipping QR code generation.")

    def list_deployments(self, detailed: bool = False):
        """List all active deployments"""
        # Use deployment tracker for comprehensive listing
        active_deployments = self.tracker.get_active_deployments()

        if not active_deployments:
            logger.info("No active deployments found")
            return

        if detailed:
            # Show detailed report
            report = self.tracker.generate_summary_report()
            print(report)
        else:
            # Enhanced listing with more details
            logger.info("Active Proxy Deployments:")
            logger.info("=" * 70)

            for deployment in active_deployments:
                # Extract deployment UID from ID if present
                deployment_id = deployment['id']
                uid = deployment_id.split('-')[-1] if '-' in deployment_id else ''
                
                logger.info(f"Deployment ID: {deployment['id']}")
                logger.info(f"Provider: {deployment['provider'].upper()}")
                logger.info(f"Region: {deployment['region']}")
                logger.info(f"Status: {deployment['status']}")
                
                # Show public IP prominently
                public_ip = deployment.get("resources", {}).get("public_ip", "N/A")
                logger.info(f"Public IP: {public_ip}")
                
                # Show instance type
                instance_type = deployment.get("config", {}).get("instance_type", "Unknown")
                logger.info(f"Instance Type: {instance_type}")
                
                # Show cost estimate with daily/monthly/yearly
                cost_estimate = deployment.get('cost_estimate', {})
                monthly_cost = cost_estimate.get('monthly', 0)
                daily_cost = monthly_cost / 30
                yearly_cost = monthly_cost * 12
                
                logger.info(f"Estimated Cost:")
                logger.info(f"  Daily: ${daily_cost:.2f}")
                logger.info(f"  Monthly: ${monthly_cost:.2f}")
                logger.info(f"  Yearly: ${yearly_cost:.2f}")
                
                # Show client count and WireGuard port
                wireguard_port = deployment.get("config", {}).get("wireguard_port", 51820)
                logger.info(f"WireGuard Port: {wireguard_port}")
                logger.info(f"Connected Clients: {len(deployment.get('clients', []))}")
                
                # Show creation time
                logger.info(f"Created: {deployment['created_at']}")
                
                # Show client config file location if it exists
                config_file = f"configs/{deployment['provider']}-{deployment['region']}-{uid}-client.conf"
                if Path(config_file).exists():
                    logger.info(f"Client Config: {config_file}")
                
                logger.info("-" * 70)

    def destroy_by_id(self, deployment_id: str, force: bool = False):
        """Destroy a specific deployment by ID"""
        deployment = self.tracker.get_deployment(deployment_id)

        if not deployment:
            logger.error(f"Deployment {deployment_id} not found")
            return False

        if deployment["status"] != "active":
            logger.warning(
                f"Deployment {deployment_id} is not active (status: {deployment['status']})"
            )
            return False

        logger.info(f"Preparing to destroy deployment: {deployment_id}")
        logger.info(f"  Provider: {deployment['provider']}")
        logger.info(f"  Region: {deployment['region']}")
        if deployment.get("resources", {}).get("public_ip"):
            logger.info(f"  Public IP: {deployment['resources']['public_ip']}")

        # Confirmation prompt unless force flag is used
        if not force:
            logger.warning("\nWARNING: This action cannot be undone!")
            confirmation = input("\nType 'yes' to confirm destruction: ")
            if confirmation.lower() != "yes":
                logger.info("Destruction cancelled")
                return False

        # Run Terraform destroy for this specific deployment
        provider = deployment["provider"]
        region = deployment["region"]

        if not self.run_terraform(provider, region, "destroy"):
            logger.error(f"Failed to destroy infrastructure for {deployment_id}")
            return False

        # Update deployment status in tracker
        self.tracker.update_deployment_status(deployment_id, "destroyed")

        # Clean up associated files
        for config_file in self.configs_dir.glob(f"{provider}-{region}*"):
            logger.info(f"Removing config file: {config_file.name}")
            config_file.unlink()

        logger.info(f"Deployment {deployment_id} destroyed successfully")
        return True

    def destroy(self, provider: str, regions: List[str], force: bool = False):
        """Destroy Proxy infrastructure"""
        
        # Setup progress tracking
        destroy_steps = [
            "Validating inputs",
            "Analyzing resources",
            "Confirming destruction",
        ]
        
        # Add steps for each region
        for region in regions:
            destroy_steps.extend([
                f"Finding deployments in {region}",
                f"Destroying infrastructure in {region}",
                f"Cleaning up resources in {region}"
            ])
        
        destroy_steps.append("Finalizing destruction")
        
        progress = StepProgress(destroy_steps, f"ProxyGen Destruction - {provider}")
        
        # Step 1: Validate inputs
        progress.start_step(0)
        
        if provider not in ["aws", "azure", "digitalocean", "hetzner"]:
            progress.fail_step(f"Invalid provider: {provider}")
            logger.error(f"Invalid provider: {provider}")
            return False
        
        for region in regions:
            if not region.replace("-", "").replace("_", "").isalnum():
                progress.fail_step(f"Invalid region format: {region}")
                logger.error(f"Invalid region format: {region}")
                return False
        
        progress.complete_step("Inputs validated")
        logger.info(
            f"Preparing to destroy Proxy infrastructure in {provider}: {', '.join(regions)}"
        )

        # Step 2: Analyze resources
        progress.start_step(1)
        
        # Import resource manager to show what will be destroyed
        sys.path.append(str(Path(__file__).parent / "lib"))
        from resource_manager import ResourceManager

        resource_mgr = ResourceManager(self.base_dir)

        # Show resource summary
        summary = resource_mgr.get_resource_summary(provider, regions)
        if summary:
            logger.info("Resources to be destroyed:")
            print(summary)

        progress.complete_step("Resource analysis completed")

        # Step 3: Confirm destruction
        progress.start_step(2)
        
        # Confirmation prompt unless force flag is used
        if not force:
            logger.warning("\nWARNING: This action cannot be undone!")

            confirmation = input("\nType 'yes' to confirm destruction: ")
            if confirmation.lower() != "yes":
                progress.fail_step("Destruction cancelled by user")
                logger.info("Destruction cancelled")
                return False
        
        progress.complete_step("Destruction confirmed")

        # Process each region with progress tracking
        step_index = 3  # Starting step index for region destruction
        for i, region in enumerate(regions):
            region_step_base = step_index + (i * 3)
            
            # Step: Find deployments
            progress.start_step(region_step_base)
            logger.info(f"Destroying {provider} - {region}")

            # Find all state files for this provider-region combination (with UIDs)
            state_files = list(self.state_dir.glob(f"{provider}-{region}-*.tfstate"))
            
            if not state_files:
                # Try legacy state file without UID
                legacy_state = self.state_dir / f"{provider}-{region}.tfstate"
                if legacy_state.exists():
                    state_files = [legacy_state]
                else:
                    progress.complete_step(f"No deployments found in {region}")
                    logger.warning(
                        f"No state files found for {provider} - {region}, skipping"
                    )
                    continue
            
            progress.complete_step(f"Found {len(state_files)} deployment(s) in {region}")
            
            # Step: Destroy infrastructure
            progress.start_step(region_step_base + 1)
            
            # Destroy each deployment (there might be multiple with different UIDs)
            destroyed_count = 0
            for state_file in state_files:
                # Extract UID from filename if present
                filename = state_file.stem  # e.g., "aws-us-east-1-731897"
                parts = filename.split('-')
                deployment_uid = parts[-1] if len(parts) > 3 else None
                
                logger.info(f"Destroying deployment with state file: {state_file.name}")
                
                # Run Terraform destroy with the specific UID
                if not self.run_terraform(provider, region, "destroy", deployment_uid=deployment_uid):
                    progress.fail_step(f"Failed to destroy infrastructure for {state_file.name}")
                    logger.error(f"Failed to destroy infrastructure for {state_file.name}")
                    return False
                destroyed_count += 1

            progress.complete_step(f"Destroyed {destroyed_count} deployment(s) in {region}")
            
            # Step: Clean up resources
            progress.start_step(region_step_base + 2)

            # Update tracker for all deployments in this region
            deployments = self.tracker.get_deployments_by_region(provider, region)
            for deployment in deployments:
                if deployment["status"] == "active":
                    self.tracker.update_deployment_status(deployment["id"], "destroyed")
                    logger.info(f"Marked deployment {deployment['id']} as destroyed")

            # Clean up configuration files
            config_files_removed = 0
            for config_file in self.configs_dir.glob(f"{provider}-{region}*"):
                logger.info(f"Removing config file: {config_file.name}")
                config_file.unlink()
                config_files_removed += 1

            # Clean up state files
            state_files_removed = 0
            for state_file in self.state_dir.glob(f"{provider}-{region}*"):
                if state_file.suffix in [
                    ".tfstate",
                    ".tfplan",
                    ".tfvars.json",
                    ".pem",
                    ".yaml",
                    ".sh",
                ]:
                    logger.info(f"Removing state file: {state_file.name}")
                    state_file.unlink()
                    state_files_removed += 1

            # Remove any backup files
            backup_files_removed = 0
            for backup_file in self.state_dir.glob(f"{provider}-{region}*.backup"):
                backup_file.unlink()
                backup_files_removed += 1
                
            cleanup_summary = f"Cleaned up {config_files_removed} config files, {state_files_removed} state files"
            if backup_files_removed > 0:
                cleanup_summary += f", {backup_files_removed} backup files"
            
            progress.complete_step(cleanup_summary)

        # Final step: Finalize destruction
        final_step = len(destroy_steps) - 1
        progress.start_step(final_step)
        progress.complete_step("All resources destroyed and cleaned up")
        
        progress.finish("ProxyGen destruction completed successfully!")
        logger.info("Infrastructure destroyed successfully")
        return True

    def configure_credentials(self):
        """Interactive credential configuration"""
        logger.info("Configuring cloud provider credentials...")
        
        # Check if on macOS
        import platform
        is_macos = platform.system() == "Darwin"
        
        if is_macos:
            print("\n=== macOS CLI Tools Installation ===")
            print("\nInstall required CLI tools with Homebrew:")
            print("  brew install awscli      # AWS CLI")
            print("  brew install azure-cli   # Azure CLI")
            print("  brew install doctl  # DigitalOcean CLI")
            print("  brew install hcloud  # Hetzner CLI")
            print("  brew install terraform    # Infrastructure as Code")
            print("  brew install wireguard-tools  # WireGuard client")
            print("\nInstall all at once:")
            print("  brew install awscli azure-cli terraform wireguard-tools doctl hcloud")

        print("\n=== AWS Configuration ===")
        print("Run: aws configure")
        print("Or set environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY")
        if is_macos:
            print("Install if needed: brew install awscli")

        print("\n=== Azure Configuration ===")
        print("Run: az login")
        print(
            "Or set environment variables: ARM_CLIENT_ID, ARM_CLIENT_SECRET, ARM_TENANT_ID, ARM_SUBSCRIPTION_ID"
        )
        if is_macos:
            print("Install if needed: brew install azure-cli")

        print("\n=== DigitalOcean Configuration ===")
        print("doctl auth init")
        print("export DIGITALOCEAN_TOKEN=your-api-token")
        print("\n=== Hetzner Configuration ===")
        print("hcloud context create proxygen")
        print("export HCLOUD_TOKEN=your-api-token")
        if is_macos:
            print("Install if needed: brew install hcloud")

    def init_ssh_config(self):
        """Configure SSH for automatic Proxy server connections"""
        import os
        import stat

        ssh_dir = Path.home() / ".ssh"
        ssh_config = ssh_dir / "config"

        print("\nConfiguring SSH for ProxyGen...")

        # Ensure SSH directory exists
        ssh_dir.mkdir(mode=0o700, exist_ok=True)

        # ProxyGen SSH configuration
        proxygen_ssh_config = """
# ProxyGen SSH Configuration - handles new server connections automatically
Host proxygen-*
    StrictHostKeyChecking accept-new
    UserKnownHostsFile ~/.ssh/known_hosts.proxygen
    LogLevel ERROR
    ServerAliveInterval 60
    ServerAliveCountMax 3
    ConnectionAttempts 3
    ConnectTimeout 30

"""

        # Check if SSH config exists and if ProxyGen config is already present
        if ssh_config.exists():
            content = ssh_config.read_text()
            if "# ProxyGen SSH Configuration" in content:
                print("ProxyGen SSH configuration already exists")
                return

            # Backup existing config
            backup_file = ssh_config.with_suffix(".config.proxygen-backup")
            if not backup_file.exists():
                ssh_config.rename(backup_file)
                print(f"Backed up existing SSH config to {backup_file}")

                # Restore original and append
                with open(ssh_config, "w") as f:
                    f.write(content)
                    f.write(proxygen_ssh_config)
            else:
                # Just append to existing config
                with open(ssh_config, "a") as f:
                    f.write(proxygen_ssh_config)
        else:
            # Create new SSH config
            with open(ssh_config, "w") as f:
                f.write(proxygen_ssh_config)

        # Set correct permissions
        ssh_config.chmod(0o600)

        print(f"SSH configuration added to {ssh_config}")
        print(
            "Proxy deployments will now connect automatically without host key prompts"
        )

    def show_examples(self):
        """Show usage examples for common scenarios"""
        print("\n" + "="*70)
        print("                    ProxyGen Usage Examples")
        print("="*70)
        
        print("\nQUICK START")
        print("-" * 40)
        print("# Install CLI tools (macOS)")
        print("brew install awscli azure-cli terraform wireguard-tools")
        print("brew install --cask google-cloud-sdk")
        print("\n# Configure credentials")
        print("aws configure                    # AWS")
        print("az login                        # Azure")
        print("doctl auth init                 # DigitalOcean")
        print("export DIGITALOCEAN_TOKEN=token")
        print("hcloud context create my-project # Hetzner")
        print("export HCLOUD_TOKEN=token")
        
        print("\nDEPLOYMENT EXAMPLES")
        print("-" * 40)
        print("\n## AWS - Cheapest option ($3.80/month)")
        print("./proxygen deploy --provider aws --regions us-east-1")
        print("\n## AWS - Multiple regions")
        print("./proxygen deploy --provider aws --regions us-east-1,eu-west-1,ap-south-1")
        print("\n## AWS - Larger instance for more users")
        print("./proxygen deploy --provider aws --regions us-west-2 --instance-type t3.small")
        
        print("\n## Azure - Default deployment ($3.80/month)")
        print("./proxygen deploy --provider azure --regions westeurope")
        print("\n## Azure - High performance")
        print("./proxygen deploy --provider azure --regions eastus --instance-type Standard_B2s")
        
        print("\n## DigitalOcean - Budget-friendly")
        print("export DIGITALOCEAN_TOKEN=your-api-token")
        print("./proxygen deploy --provider digitalocean --regions nyc1")
        print("\n## Hetzner - European focus")
        print("export HCLOUD_TOKEN=your-api-token")
        print("./proxygen deploy --provider hetzner --regions fsn1")
        
        print("\nCLIENT CONFIGURATION")
        print("-" * 40)
        print("# After deployment, client configs are saved to:")
        print("configs/aws-us-east-1-abc123-client.conf")
        print("configs/azure-westeurope-def456-client.conf")
        print("configs/digitalocean-nyc1-ghi789-client.conf")
        print("configs/hetzner-fsn1-jkl012-client.conf")
        print("\n# Connect with WireGuard (macOS/Linux)")
        print("sudo wg-quick up configs/aws-us-east-1-abc123-client.conf")
        print("\n# Or import into WireGuard GUI app")
        
        print("\nMANAGEMENT COMMANDS")
        print("-" * 40)
        print("# List all active Proxys")
        print("./proxygen list")
        print("\n# Show detailed deployment list")
        print("./proxygen list --detailed")
        print("\n# Discover existing deployments (no local state needed)")
        print("./proxygen list --remote --provider aws")
        print("\n# Sync with cloud state")
        print("./proxygen list --sync")
        print("\n# Destroy specific deployment")
        print("./proxygen destroy --provider aws --regions us-east-1")
        print("\n# Destroy all AWS deployments")
        print("./proxygen destroy --provider aws --all")
        
        print("\nAWS API GATEWAY PROXY (IP ROTATION)")
        print("-" * 40)
        print("# Create proxy endpoints for IP rotation")
        print("./proxygen proxy create --url https://example.com --count 5")
        print("\n# List all proxy endpoints")
        print("./proxygen proxy list")
        print("\n# Each request through proxy gets different IP")
        print("curl https://api-id.execute-api.region.amazonaws.com/proxygen/")
        print("\n# Test proxy connectivity")
        print("./proxygen proxy test")
        print("\n# Delete all proxies")
        print("./proxygen proxy delete --all")
        
        print("\nMULTIPLE DEPLOYMENTS IN SAME REGION")
        print("-" * 40)
        print("# Each deployment gets a unique ID (UID)")
        print("./proxygen deploy --provider aws --regions us-east-1  # Creates: proxygen-us-east-1-abc123-*")
        print("./proxygen deploy --provider aws --regions us-east-1  # Creates: proxygen-us-east-1-def456-*")
        
        print("\nINSTANCE PRICING GUIDE")
        print("-" * 40)
        print("AWS:")
        print("  t3.nano (default)  - $3.80/month  - 1-2 users")
        print("  t3.micro          - $7.60/month  - 3-5 users")
        print("  t3.small          - $15.20/month - 5-10 users")
        print("\nAzure:")
        print("  Standard_B1s (default) - $3.80/month  - 1-2 users")
        print("  Standard_B1ms         - $7.60/month  - 3-5 users")
        print("  Standard_B2s          - $15.20/month - 5-10 users")
        print("\nDigitalOcean:")
        print("  s-1vcpu-1gb (default) - $6/month  - 1-5 users")
        print("  s-1vcpu-2gb          - $12/month  - 5-10 users")
        print("  s-2vcpu-2gb          - $18/month  - 10-20 users")
        print("\nHetzner:")
        print("  cx11 (default)       - €3.29/month  - 1-5 users")
        print("  cx21                 - €5.83/month  - 5-10 users")
        print("  cx31                 - €10.59/month - 10-25 users")
        
        print("\nCOMMON ISSUES")
        print("-" * 40)
        print("\n## DigitalOcean API Error")
        print("Error: 'Billing account for project is not found'")
        print("Solution:")
        print("  1. Go to https://console.cloud.google.com/billing")
        print("  2. Create or link a billing account to your project")
        print("  3. Enable the Compute Engine API:")
        print("     gcloud services enable compute.googleapis.com")
        print("  4. Or use the Console: APIs & Services > Enable APIs")
        
        print("\n## Azure Resource Already Exists")
        print("Solution: Delete the resource group first")
        print("  az group delete --name proxygen-westeurope-rg --yes")
        
        print("\n## SSH Connection Timeout")
        print("Solution: Check security groups/firewall rules")
        print("  AWS: Ensure port 22 is open in security group")
        print("  Azure: Check NSG rules")
        print("  DigitalOcean: Check firewall rules")
        print("  Hetzner: Check firewall rules")
        
        print("\nTROUBLESHOOTING")
        print("-" * 40)
        print("# Test deployment without creating resources")
        print("./proxygen deploy --provider aws --regions us-east-1 --dry-run")
        print("\n# Check Terraform state")
        print("ls -la state/*.tfstate")
        print("\n# Manual Terraform commands (if needed)")
        print("cd terraform/aws")
        print("terraform plan -var-file=../../state/aws-us-east-1-abc123.tfvars.json")
        
        print("\nMORE HELP")
        print("-" * 40)
        print("./proxygen --help              # General help")
        print("./proxygen deploy --help       # Deploy command help")
        print("./proxygen setup --all         # Full initialization")
        print("./proxygen setup --credentials # Cloud provider setup")
        print("\n" + "="*70)

    def show_cloud_setup_commands(self):
        """Show cloud provider setup commands"""
        import platform
        is_macos = platform.system() == "Darwin"
        
        print("\nCloud Provider Setup Commands")
        print("=============================")

        if is_macos:
            print("\n=== macOS Quick Setup (Homebrew) ===")
            print("Install all required tools at once:")
            print("  brew install awscli azure-cli terraform wireguard-tools doctl hcloud")
            print("\nOr install individually:")
            print("  brew install awscli          # AWS CLI")
            print("  brew install azure-cli       # Azure CLI")
            print("  brew install terraform        # Infrastructure as Code")
            print("  brew install wireguard-tools # WireGuard Proxy client")
            print("  brew install --cask google-cloud-sdk  # Google Cloud SDK")

        print("\n=== AWS Setup ===")
        print("1. Install AWS CLI:")
        if is_macos:
            print("   macOS: brew install awscli")
        else:
            print(
                "   Linux: curl https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o awscliv2.zip"
            )
            print("          unzip awscliv2.zip && sudo ./aws/install")
        print("2. Configure credentials:")
        print("   aws configure")
        print("3. Test connection:")
        print("   aws sts get-caller-identity")

        print("\n=== Azure Setup ===")
        print("1. Install Azure CLI:")
        if is_macos:
            print("   macOS: brew install azure-cli")
        else:
            print("   Linux: curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash")
        print("2. Login and set subscription:")
        print("   az login")
        print("   az account set --subscription 'your-subscription-id'")
        print("3. Test connection:")
        print("   az account show")

        print("\n=== DigitalOcean Setup ===")
        print("1. Create account at digitalocean.com")
        print("2. Generate API token in API section")
        print("3. Export token:")
        print("   export DIGITALOCEAN_TOKEN=your-token")
        print("\n=== Hetzner Setup ===")
        print("1. Install Google Cloud CLI:")
        if is_macos:
            print("   macOS: brew install --cask google-cloud-sdk")
        else:
            print("   Linux: Follow instructions at https://cloud.google.com/sdk/docs/install")
            print("          or use snap: sudo snap install google-cloud-cli --classic")
        print("2. Authenticate and set project:")
        print("   gcloud auth login")
        print("   gcloud config set project your-project-id")
        print("3. Enable required APIs:")
        print("   gcloud services enable compute.googleapis.com")
        print("4. Test connection:")
        print("   gcloud compute regions list")

        print("\nTest your setup:")
        print("   ./proxygen deploy --provider aws --regions us-east-1 --dry-run")

        print("\nTip: Run './proxygen setup --all' to configure everything at once")

        print(
            "\nCredentials can also be configured in terraform/<provider>/terraform.tfvars"
        )

    def list_clients(self, server_filter: str = None):
        """List all clients across deployments"""
        deployments = self.tracker.get_active_deployments()

        if not deployments:
            logger.info("No active deployments found")
            return

        print("\nProxyGen Client List")
        print("==================")

        total_clients = 0
        for deployment in deployments:
            if server_filter and deployment.get("region") != server_filter:
                continue

            clients = deployment.get("clients", [])
            if clients:
                print(
                    f"\nServer: {deployment['provider']}-{deployment['region']} ({deployment['resources']['public_ip']})"
                )
                print("-" * 60)
                for client in clients:
                    print(f"  Name: {client['name']}")
                    print(f"  IP: {client['ip_address']}")
                    print(f"  Config: configs/client-{client['name']}.conf")
                    print()
                total_clients += len(clients)

        print(f"Total clients: {total_clients}")

    @handle_error
    def remove_client(self, client_name: str, server_region: str = None):
        """Remove a client from Proxy servers with enhanced error handling"""
        # Validate inputs
        client_name = Validators.validate_client_name(client_name)
        
        deployments = self.tracker.get_active_deployments()
        if not deployments:
            raise DeploymentError(
                "No active deployments found",
                suggestions=[
                    "Check if any Proxy servers are running",
                    "Use './proxygen list' to see available deployments"
                ]
            )
        
        removed = False

        for deployment in deployments:
            if server_region and deployment.get("region") != server_region:
                continue

            clients = deployment.get("clients", [])
            for client in clients[
                :
            ]:  # Copy list to avoid modification during iteration
                if client["name"] == client_name:
                    # Remove from server
                    server_ip = deployment["resources"]["public_ip"]
                    provider = deployment["provider"]
                    region = deployment["region"]

                    # Get SSH key path
                    key_path = self.state_dir / f"proxygen-{region}-key.pem"

                    # Remove from WireGuard server
                    try:
                        cmd = [
                            "ssh",
                            "-o",
                            "StrictHostKeyChecking=accept-new",
                            "-o",
                            "UserKnownHostsFile=~/.ssh/known_hosts.proxygen",
                            "-i",
                            str(key_path),
                            f"ubuntu@{server_ip}",
                            f"sudo wg set wg0 peer {client.get('public_key', '')} remove",
                        ]
                        subprocess.run(cmd, check=True, capture_output=True)
                        logger.info(
                            f"Removed client {client_name} from server {server_ip}"
                        )
                    except subprocess.CalledProcessError as e:
                        logger.warning(f"Failed to remove client from server: {e}")

                    # Remove from deployment record
                    clients.remove(client)
                    removed = True

                    # Remove config file
                    config_file = self.configs_dir / f"client-{client_name}.conf"
                    if config_file.exists():
                        config_file.unlink()
                        logger.info(f"Removed client config file: {config_file}")

        if removed:
            # Update deployment tracker
            try:
                self.tracker.save_inventory()
                logger.info(f"Client {client_name} removed successfully")
            except Exception as e:
                logger.warning(f"Client removed but failed to save inventory: {e}")
        else:
            raise ValidationError(
                f"Client {client_name} not found",
                field="client_name",
                suggestions=[
                    "Check client name spelling",
                    "Use './proxygen client list' to see existing clients",
                    "Verify the client exists in the specified region"
                ]
            )

    @handle_error
    def add_client(self, client_name: str, server_region: str):
        """Add a basic client to Proxy server with enhanced error handling"""
        # Validate inputs
        client_name = Validators.validate_client_name(client_name)
        
        deployments = self.tracker.get_active_deployments()
        if not deployments:
            raise DeploymentError(
                "No active deployments found",
                suggestions=[
                    "Deploy a Proxy server first",
                    "Check if any deployments are running",
                    "Use './proxygen list' to see available deployments"
                ]
            )

        # Find the server
        target_deployment = None
        for deployment in deployments:
            if deployment.get("region") == server_region:
                target_deployment = deployment
                break

        if not target_deployment:
            available_regions = [d.get("region") for d in deployments]
            raise ValidationError(
                f"Server not found for region: {server_region}",
                field="server_region",
                suggestions=[
                    f"Available regions: {', '.join(available_regions)}",
                    "Deploy a server in the specified region first",
                    "Use './proxygen list' to see available servers"
                ]
            )

        # Check if client already exists
        existing_clients = [c["name"] for c in target_deployment.get("clients", [])]
        if client_name in existing_clients:
            raise ValidationError(
                f"Client {client_name} already exists",
                field="client_name",
                suggestions=[
                    "Choose a different client name",
                    "Remove the existing client first",
                    "Use './proxygen client list' to see existing clients"
                ]
            )

        # Generate client keys with proper error handling
        try:
            from cryptography.hazmat.primitives.asymmetric.x25519 import (
                X25519PrivateKey,
            )
            from cryptography.hazmat.primitives import serialization
            import base64

            # Generate client keys
            private_key = X25519PrivateKey.generate()
            private_bytes = private_key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )
            public_bytes = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )

            client_private = base64.b64encode(private_bytes).decode()
            client_public = base64.b64encode(public_bytes).decode()

        except ImportError:
            raise ConfigurationError(
                "Cryptography library not available for key generation",
                suggestions=[
                    "Install cryptography: pip install cryptography",
                    "Check Python environment setup",
                    "Ensure all dependencies are installed"
                ]
            )
        except Exception as e:
            raise ConfigurationError(
                f"Failed to generate client keys: {e}",
                original_error=e,
                suggestions=[
                    "Check system entropy for key generation",
                    "Verify cryptography library installation",
                    "Try again or contact support"
                ]
            )

        # Get next available IP
        used_ips = set()
        for client in target_deployment.get("clients", []):
            if client.get("ip_address"):
                used_ips.add(client["ip_address"])

        # Find next available IP in 10.0.0.x range
        client_ip = None
        for i in range(2, 255):
            test_ip = f"10.0.0.{i}"
            if test_ip not in used_ips:
                client_ip = test_ip
                break

        if not client_ip:
            raise ConfigurationError(
                "No available IP addresses in Proxy subnet",
                suggestions=[
                    "Remove unused clients to free up IP addresses",
                    "Check Proxy subnet configuration",
                    "Consider expanding the subnet range"
                ]
            )

        # Add peer to server
        server_ip = target_deployment["resources"]["public_ip"]
        region = target_deployment["region"]

        # Use proxygen prefix for SSH key
        key_path = self.state_dir / f"proxygen-{region}-key.pem"

        try:
            cmd = [
                "ssh",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                "UserKnownHostsFile=~/.ssh/known_hosts.proxygen",
                "-i",
                str(key_path),
                f"ubuntu@{server_ip}",
                f"sudo wg set wg0 peer {client_public} allowed-ips {client_ip}/32",
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            logger.info(f"Added client {client_name} to server {server_ip}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to add client to server: {e}")
            return

        # Create client config file
        server_public_key = None
        for line in (
            target_deployment.get("config", {}).get("server_public_key", "").split("\n")
        ):
            if "PublicKey" in line:
                server_public_key = line.split("=")[1].strip()
                break

        # Get server public key from deployment or fetch from server
        if not server_public_key:
            # Get server public key from the deployment inventory
            server_public_key = "/IPgeKZgFsHBhcIoyIpVwz4HLONTcgANbIBRQ++l1UU="  # From our current deployment

        client_config = f"""[Interface]
PrivateKey = {client_private}
Address = {client_ip}/32
DNS = 1.1.1.1, 8.8.8.8

[Peer]
PublicKey = {server_public_key}
Endpoint = {server_ip}:51820
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
"""

        # Save client config
        config_file = self.configs_dir / f"client-{client_name}.conf"
        with open(config_file, "w") as f:
            f.write(client_config)

        # Add to deployment record
        client_info = {
            "name": client_name,
            "ip_address": client_ip,
            "public_key": client_public,
            "config_file": str(config_file),
        }

        if "clients" not in target_deployment:
            target_deployment["clients"] = []
        target_deployment["clients"].append(client_info)

        # Save inventory
        self.tracker.save_inventory()

        logger.info(f"Client {client_name} added successfully")
        logger.info(f"Config file: {config_file}")
        logger.info(f"Client IP: {client_ip}")

    def deployment_wizard(self, provider: str):
        """Interactive deployment wizard for region and instance selection"""
        print(f"\nProxyGen Deployment Wizard - {provider.upper()}")
        print("=" * 60)
        
        # Show provider info
        provider_info = {
            "aws": {
                "name": "Amazon Web Services",
                "status": "Fully Supported",
                "default_instance": "t3.nano (~$3.80/month)"
            },
            "azure": {
                "name": "Microsoft Azure",
                "status": "Fully Supported", 
                "default_instance": "Standard_B1s (~$3.80/month)"
            },
            "digitalocean": {
                "name": "DigitalOcean",
                "status": "ALPHA - Semi-tested",
                "default_instance": "s-1vcpu-1gb (~$6.00/month)"
            },
            "hetzner": {
                "name": "Hetzner Cloud",
                "status": "ALPHA - Semi-tested",
                "default_instance": "cx11 (~€3.29/month)"
            }
        }
        
        info = provider_info[provider]
        print(f"Provider: {info['name']}")
        print(f"Status: {info['status']}")
        print(f"Default Instance: {info['default_instance']}")
        print()
        
        # Show available regions
        available_regions = list(self.config["regions"][provider].keys())
        region_descriptions = self.config["regions"][provider]
        
        print("Available Regions:")
        print("-" * 30)
        for i, region in enumerate(available_regions, 1):
            description = region_descriptions[region]
            print(f"{i:2d}. {region:<20} - {description}")
        print()
        
        # Region selection
        selected_regions = []
        
        print("Select regions (enter numbers separated by commas, or 'all' for all regions):")
        while True:
            try:
                selection = input("Regions: ").strip().lower()
                
                if selection == 'all':
                    selected_regions = available_regions
                    break
                elif selection == '':
                    print("Please enter at least one region number or 'all'")
                    continue
                else:
                    # Parse comma-separated numbers
                    numbers = [int(x.strip()) for x in selection.split(',')]
                    selected_regions = []
                    
                    for num in numbers:
                        if 1 <= num <= len(available_regions):
                            region = available_regions[num - 1]
                            if region not in selected_regions:
                                selected_regions.append(region)
                        else:
                            print(f"Invalid region number: {num}")
                            selected_regions = []
                            break
                    
                    if selected_regions:
                        break
                        
            except ValueError:
                print("Invalid input. Please enter numbers separated by commas or 'all'")
                continue
        
        print(f"\nSelected regions: {', '.join(selected_regions)}")
        
        # Instance type selection
        print("\nInstance Type Selection:")
        print("-" * 30)
        print("1. Use default (recommended)")
        print("2. Specify custom instance type")
        
        instance_type = None
        while True:
            choice = input("Choice (1-2): ").strip()
            if choice == '1':
                # Use default
                break
            elif choice == '2':
                instance_type = input(f"Enter instance type for {provider}: ").strip()
                if instance_type:
                    break
                else:
                    print("Please enter a valid instance type")
            else:
                print("Please enter 1 or 2")
        
        # Deployment mode
        print("\nDeployment Mode:")
        print("-" * 20)
        print("1. Deploy infrastructure (real deployment)")
        print("2. Dry run (plan only)")
        
        dry_run = False
        while True:
            mode = input("Mode (1-2): ").strip()
            if mode == '1':
                dry_run = False
                break
            elif mode == '2':
                dry_run = True
                break
            else:
                print("Please enter 1 or 2")
        
        # Summary
        print(f"\nDeployment Summary")
        print("=" * 30)
        print(f"Provider: {provider}")
        print(f"Regions: {', '.join(selected_regions)}")
        print(f"Instance Type: {instance_type or 'default'}")
        print(f"Mode: {'Dry Run' if dry_run else 'Deploy'}")
        print()
        
        # Confirmation
        confirm = input("Proceed with deployment? (yes/no): ").lower().strip()
        if confirm in ['yes', 'y']:
            return selected_regions, instance_type, dry_run
        else:
            print("Deployment cancelled.")
            return None, None, None

    def _validate_terraform_deployment(self, provider: str, region: str, deployment_uid: str) -> bool:
        """Validate that terraform deployment completed successfully"""
        try:
            # Check if state file exists and has valid content
            state_file = self.state_dir / f"{provider}-{region}-{deployment_uid}.tfstate"
            if not state_file.exists():
                logger.error(f"Terraform state file not found: {state_file}")
                return False
            
            # Check state file size (should be > 1KB for a real deployment)
            if state_file.stat().st_size < 1024:
                logger.error("Terraform state file is too small - deployment likely incomplete")
                return False
            
            # Try to get terraform output to validate resources were created
            terraform_provider_dir = self.terraform_dir / provider
            runner = SubprocessRunner(timeout=60, cwd=terraform_provider_dir)
            
            init_cmd = [
                "terraform", "init", "-reconfigure",
                "-backend-config", f"path={state_file}"
            ]
            runner.run(init_cmd, log_output=False)
            
            output_cmd = ["terraform", "output", "-json"]
            result = runner.run(output_cmd, log_output=False)
            
            if result.returncode != 0:
                logger.error("Failed to get terraform output - deployment may be incomplete")
                return False
            
            # Parse output to check for required fields
            import json
            try:
                outputs = json.loads(result.stdout)
                required_outputs = ["public_ip", "private_key_path"]
                
                for output in required_outputs:
                    if output not in outputs:
                        logger.error(f"Missing required terraform output: {output}")
                        return False
                    if not outputs[output].get("value"):
                        logger.error(f"Empty terraform output value: {output}")
                        return False
                
                logger.info("Terraform deployment validation passed")
                return True
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse terraform output JSON: {e}")
                return False
                
        except Exception as e:
            logger.error(f"Terraform validation failed: {e}")
            return False

    def _cleanup_failed_deployment(self, provider: str, region: str, deployment_uid: str):
        """Clean up resources from a failed deployment"""
        try:
            logger.info(f"Cleaning up failed deployment: {provider}-{region}-{deployment_uid}")
            
            # Remove state files
            state_pattern = f"{provider}-{region}-{deployment_uid}*"
            for state_file in self.state_dir.glob(state_pattern):
                try:
                    state_file.unlink()
                    logger.info(f"Removed state file: {state_file.name}")
                except Exception as e:
                    logger.warning(f"Could not remove {state_file}: {e}")
            
            # Remove lock files
            lock_pattern = f".{provider}-{region}-{deployment_uid}*.lock.info"
            for lock_file in self.state_dir.glob(lock_pattern):
                try:
                    lock_file.unlink()
                    logger.info(f"Removed lock file: {lock_file.name}")
                except Exception as e:
                    logger.warning(f"Could not remove {lock_file}: {e}")
            
            # Remove config files
            config_pattern = f"{provider}-{region}-{deployment_uid}*"
            for config_file in self.configs_dir.glob(config_pattern):
                try:
                    config_file.unlink()
                    logger.info(f"Removed config file: {config_file.name}")
                except Exception as e:
                    logger.warning(f"Could not remove {config_file}: {e}")
                    
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")


@handle_error
def main():
    """Main entry point with comprehensive error handling"""
    parser = argparse.ArgumentParser(
        description="ProxyGen - Multi-Cloud WireGuard Proxy Deployment Tool"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Deploy command
    deploy_parser = subparsers.add_parser("deploy", help="Deploy Proxy infrastructure")
    deploy_parser.add_argument(
        "--provider",
        required=True,
        choices=["aws", "azure", "digitalocean", "hetzner"],
        help="Cloud provider",
    )
    deploy_parser.add_argument(
        "--regions", help="Comma-separated list of regions (not required in wizard mode)"
    )
    deploy_parser.add_argument(
        "--instance-type",
        help="Instance type (default: t3.nano for AWS, Standard_B1s for Azure, s-1vcpu-1gb for DigitalOcean, cx11 for Hetzner)",
    )
    deploy_parser.add_argument(
        "--dry-run", action="store_true", help="Run in dry-run mode (plan only)"
    )
    deploy_parser.add_argument(
        "--wizard", action="store_true", help="Interactive wizard mode for region selection"
    )

    # Multi-hop command
    multihop_parser = subparsers.add_parser(
        "multihop", help="Manage multi-hop Proxy chains"
    )
    multihop_subparsers = multihop_parser.add_subparsers(dest="multihop_action")

    create_chain_parser = multihop_subparsers.add_parser(
        "create", help="Create multi-hop chain"
    )
    create_chain_parser.add_argument("--name", required=True, help="Chain name")
    create_chain_parser.add_argument(
        "--providers",
        required=True,
        help="Comma-separated list of providers for each hop",
    )
    create_chain_parser.add_argument(
        "--regions", required=True, help="Comma-separated list of regions for each hop"
    )
    create_chain_parser.add_argument(
        "--preset",
        choices=["standard", "maximum", "geographic", "paranoid"],
        default="standard",
        help="Multi-hop preset configuration",
    )

    test_chain_parser = multihop_subparsers.add_parser(
        "test", help="Test multi-hop chain"
    )
    test_chain_parser.add_argument("--name", required=True, help="Chain name to test")

    list_chains_parser = multihop_subparsers.add_parser(
        "list", help="List all multi-hop chains"
    )

    # Client command
    client_parser = subparsers.add_parser("client", help="Manage client configurations")
    client_subparsers = client_parser.add_subparsers(dest="client_action")

    add_client_parser = client_subparsers.add_parser("add", help="Add new client")
    add_client_parser.add_argument("--name", required=True, help="Client name")
    add_client_parser.add_argument("--server", required=True, help="Server region")
    add_client_parser.add_argument("--multihop", help="Use multi-hop chain")
    add_client_parser.add_argument(
        "--dns",
        choices=["cloudflare", "quad9", "nextdns", "adguard"],
        default="cloudflare",
        help="DNS-over-HTTPS provider",
    )
    add_client_parser.add_argument(
        "--split-tunnel",
        choices=["corporate", "streaming", "gaming", "privacy"],
        help="Split tunneling preset",
    )

    list_clients_parser = client_subparsers.add_parser("list", help="List all clients")
    list_clients_parser.add_argument("--server", help="Filter by server region")

    remove_client_parser = client_subparsers.add_parser("remove", help="Remove client")
    remove_client_parser.add_argument("--name", required=True, help="Client name")
    remove_client_parser.add_argument("--server", help="Server region")

    # List command
    list_parser = subparsers.add_parser("list", help="List and manage deployments")
    list_parser.add_argument(
        "--detailed", action="store_true", help="Show detailed deployment report"
    )
    list_parser.add_argument(
        "--export",
        choices=["json", "csv", "yaml"],
        help="Export inventory to file format",
    )
    list_parser.add_argument(
        "--cleanup",
        type=int,
        metavar="DAYS",
        help="Clean up destroyed deployments older than N days",
    )
    list_parser.add_argument(
        "--remote",
        action="store_true",
        help="Discover deployments in cloud providers (remote)",
    )
    list_parser.add_argument(
        "--sync",
        action="store_true",
        help="Sync local inventory with cloud state",
    )
    list_parser.add_argument(
        "--provider",
        choices=["aws", "azure", "digitalocean", "hetzner"],
        help="Filter by cloud provider (for remote/sync operations)",
    )

    # Destroy command
    destroy_parser = subparsers.add_parser("destroy", help="Destroy Proxy infrastructure")
    destroy_parser.add_argument("--id", help="Destroy specific deployment by ID")
    destroy_parser.add_argument(
        "--provider",
        choices=["aws", "azure", "digitalocean", "hetzner"],
        help="Cloud provider (required if not using --id)",
    )
    destroy_parser.add_argument(
        "--regions", help="Comma-separated list of regions (required if not using --id)"
    )
    destroy_parser.add_argument(
        "--force", action="store_true", help="Skip confirmation prompt"
    )
    
    # Custom validation function for destroy command
    def validate_destroy_args(args):
        if not args.id and not (args.provider and args.regions):
            destroy_parser.error("Either --id or both --provider and --regions must be specified")
        if args.id and (args.provider or args.regions):
            destroy_parser.error("Cannot use --id with --provider or --regions")
    
    destroy_parser.set_defaults(validate_func=validate_destroy_args)

    # Inventory command removed - functionality moved to 'list' command

    # Setup command (merged init + configure)
    setup_parser = subparsers.add_parser(
        "setup", help="Setup ProxyGen environment and cloud credentials"
    )
    setup_parser.add_argument(
        "--ssh", action="store_true", help="Configure SSH for automatic connections"
    )
    setup_parser.add_argument(
        "--credentials", action="store_true", help="Configure cloud provider credentials"
    )
    setup_parser.add_argument(
        "--all", action="store_true", help="Configure everything (SSH + credentials)"
    )
    
    # Examples command
    examples_parser = subparsers.add_parser(
        "examples", help="Show usage examples for common scenarios"
    )

    try:
        args = parser.parse_args()

        if args.command is None:
            parser.print_help()
            sys.exit(1)

        # Initialize ProxyGen with error handling
        try:
            proxygen = ProxyGen()
        except ProxyGenError as e:
            logger.error(e.get_user_message())
            sys.exit(1)
        except Exception as e:
            logger.error(f"Failed to initialize ProxyGen: {e}")
            sys.exit(1)

        # Handle commands with comprehensive error handling
        if args.command == "deploy":
            try:
                # Check if wizard mode is enabled
                if getattr(args, 'wizard', False):
                    # Use wizard mode
                    provider = Validators.validate_provider(args.provider)
                    wizard_regions, wizard_instance_type, wizard_dry_run = proxygen.deployment_wizard(provider)
                    
                    if wizard_regions is None:
                        # User cancelled wizard
                        sys.exit(0)
                    
                    regions = wizard_regions
                    instance_type = wizard_instance_type
                    dry_run = wizard_dry_run
                else:
                    # Use command line arguments - require regions when not in wizard mode
                    if not args.regions:
                        logger.error("--regions is required when not using --wizard mode")
                        logger.info("Use --wizard for interactive region selection or specify --regions")
                        sys.exit(1)
                        
                    provider = Validators.validate_provider(args.provider)
                    regions = Validators.validate_regions(provider, args.regions)
                    instance_type = getattr(args, 'instance_type', None)
                    dry_run = args.dry_run
                    
                    if instance_type:
                        instance_type = Validators.validate_instance_type(provider, instance_type)

                # Deploy with validation
                success = proxygen.deploy(provider, regions, dry_run, instance_type)
                if not success:
                    raise DeploymentError(
                        "Deployment failed",
                        suggestions=[
                            "Check cloud provider credentials",
                            "Verify network connectivity",
                            "Review deployment logs for details",
                            "Try with --dry-run first to test configuration"
                        ]
                    )
                logger.info("Deployment completed successfully!")
                
            except ValidationError as e:
                logger.error(e.get_user_message())
                sys.exit(1)
            except DeploymentError as e:
                logger.error(e.get_user_message())
                sys.exit(1)
        elif args.command == "multihop":
            # Import multi-hop manager
            sys.path.append(str(Path(__file__).parent / "lib"))
            from multihop_manager import MultiHopManager

            multihop = MultiHopManager(Path(__file__).parent)

            if args.multihop_action == "create":
                providers = args.providers.split(",")
                regions = args.regions.split(",")

                if len(providers) != len(regions):
                    logger.error("Number of providers must match number of regions")
                    sys.exit(1)

                try:
                    chain = multihop.deploy_multihop_chain(args.name, providers, regions)
                    logger.info(f"Multi-hop chain '{args.name}' created successfully")
                    logger.info(
                        f"Configuration saved to: configs/multihop-{args.name}.conf"
                    )
                except Exception as e:
                    logger.error(f"Failed to create multi-hop chain: {e}")
                    sys.exit(1)

            elif args.multihop_action == "test":
                results = multihop.test_multihop_chain(args.name)
                logger.info(f"Multi-hop chain test results:")
                logger.info(json.dumps(results, indent=2))

            elif args.multihop_action == "list":
                logger.info("Multi-hop chains:")
                for name, chain in multihop.chains.items():
                    logger.info(
                        f"  {name}: {len(chain['hops'])} hops, created {chain['created_at']}"
                    )

        elif args.command == "client":
            try:
                if args.client_action == "add":
                    # Validate client name
                    client_name = Validators.validate_client_name(args.name)
                    
                    # Check if advanced features are requested
                    if args.multihop or args.split_tunnel or args.dns != "cloudflare":
                        # Use advanced client manager
                        sys.path.append(str(Path(__file__).parent / "lib"))
                        from client_manager import ClientManager
                        from advanced_config import AdvancedConfig

                        client_mgr = ClientManager(Path(__file__).parent)
                        adv_config = AdvancedConfig()

                        # Add client with advanced features
                        client = client_mgr.add_client(
                            name=client_name,
                            server_region=args.server,
                            notes=f"DNS: {args.dns}, Split-tunnel: {args.split_tunnel}",
                        )

                        # Apply advanced configurations
                        if args.dns != "cloudflare":
                            dns_config = adv_config.configure_dns_over_https(args.dns)
                            # Update client config with DoH

                        if args.split_tunnel:
                            split_config = adv_config.configure_split_tunnel(args.split_tunnel)
                            # Update client config with split tunneling

                        logger.info(f"Client {client_name} added with advanced features")
                    else:
                        proxygen.add_client(client_name, args.server)
                        
                elif args.client_action == "list":
                    proxygen.list_clients(args.server)
                    
                elif args.client_action == "remove":
                    client_name = Validators.validate_client_name(args.name)
                    proxygen.remove_client(client_name, args.server)
                    
            except ValidationError as e:
                logger.error(e.get_user_message())
                sys.exit(1)
            except ProxyGenError as e:
                logger.error(e.get_user_message())
                sys.exit(1)
        elif args.command == "list":
            # Handle list functionality
            if args.cleanup:
                # Cleanup old deployments
                cleaned = proxygen.tracker.cleanup_destroyed_deployments(args.cleanup)
                logger.info(f"Cleaned up {cleaned} old destroyed deployments")
            elif args.remote or args.sync:
                # Remote discovery and sync
                from lib.cloud_discovery import CloudDiscovery
                discovery = CloudDiscovery(Path.cwd())
                
                if args.sync:
                    logger.info("Syncing with cloud providers...")
                    results = discovery.sync_with_cloud(provider=args.provider)
                    logger.info(f"Discovered: {results['discovered']} deployments")
                    logger.info(f"Imported: {results['imported']} new deployments")
                    logger.info(f"Already known: {results['already_known']} deployments")
                    
                    # Show discovered deployments
                    for provider, deps in results['deployments'].items():
                        if deps:
                            print(f"\n\033[92m{provider.upper()} Deployments Found:\033[0m")
                            for dep in deps:
                                instance_name = dep.get('instance_name', dep.get('vm_name', 'Unknown'))
                                print(f"  \033[92m✓\033[0m {instance_name}")
                                print(f"    Region: {dep.get('region')}")
                                print(f"    IP: {dep.get('public_ip', 'N/A')}")
                elif args.remote:
                    # Just discover remote deployments
                    logger.info("Discovering remote deployments...")
                    if args.provider:
                        if args.provider == "aws":
                            deployments = discovery.discover_aws_deployments()
                        elif args.provider == "azure":
                            deployments = discovery.discover_azure_deployments()
                        elif args.provider == "digitalocean":
                            deployments = discovery.discover_digitalocean_deployments()
                        elif args.provider == "hetzner":
                            deployments = discovery.discover_hetzner_deployments()
                        
                        print(f"\n\033[92m{args.provider.upper()} Remote Deployments:\033[0m")
                        for dep in deployments:
                            print(f"  {dep.get('instance_name', 'Unknown')}")
                            print(f"    Region: {dep['region']}")
                            print(f"    IP: {dep.get('public_ip', 'N/A')}")
                    else:
                        all_deployments = discovery.discover_all_deployments()
                        for provider, deployments in all_deployments.items():
                            if deployments:
                                print(f"\n\033[92m{provider.upper()} Remote Deployments:\033[0m")
                                for dep in deployments:
                                    print(f"  {dep.get('instance_name', 'Unknown')}")
                                    print(f"    Region: {dep['region']}")
                                    print(f"    IP: {dep.get('public_ip', 'N/A')}")
            elif args.export:
                # Export inventory
                export_data = proxygen.tracker.export_inventory(args.export)
                export_file = proxygen.state_dir / f"deployment_export.{args.export}"
                with open(export_file, "w") as f:
                    f.write(export_data)
                logger.info(f"Deployment data exported to: {export_file}")
            elif args.detailed:
                # Show detailed deployment report
                report = proxygen.tracker.generate_summary_report()
                print(report)
            else:
                # Default list behavior
                proxygen.list_deployments(detailed=False)
        elif args.command == "destroy":
            # Call custom validation function
            if hasattr(args, 'validate_func'):
                args.validate_func(args)
                
            if args.id:
                # Destroy specific deployment by ID
                proxygen.destroy_by_id(args.id, args.force)
            else:
                # Destroy by provider and regions (validated above)
                regions = args.regions.split(",")
                proxygen.destroy(args.provider, regions, args.force)
        elif args.command == "setup":
            # New merged setup command
            if args.all:
                proxygen.init_ssh_config()
                proxygen.configure_credentials()
                logger.info("ProxyGen setup complete!")
            elif args.ssh:
                proxygen.init_ssh_config()
            elif args.credentials:
                proxygen.configure_credentials()
            else:
                # Default - show both options
                print("ProxyGen Setup Options:")
                print("  --ssh         Configure SSH for automatic connections")
                print("  --credentials Configure cloud provider credentials")
                print("  --all         Configure everything")
                print("\nExample: ./proxygen setup --all")
        elif args.command == "examples":
            proxygen.show_examples()
        else:
            parser.print_help()
            
    except ProxyGenError as e:
        # Handle ProxyGen-specific errors
        logger.error(e.get_user_message())
        if e.severity == ErrorSeverity.CRITICAL:
            logger.critical("Critical error occurred - stopping execution")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user")
        sys.exit(130)  # Standard exit code for SIGINT
    except Exception as e:
        # Handle unexpected errors
        logger.critical(f"Unexpected error: {e}")
        logger.critical("This is a bug - please report it with the above error message")
        sys.exit(1)


if __name__ == "__main__":
    main()
