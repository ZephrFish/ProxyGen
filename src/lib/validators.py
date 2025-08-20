"""
Input validation utilities for ProxyGen.
Provides comprehensive validation for all user inputs.
"""

import re
import ipaddress
from typing import List, Dict, Any, Optional, Union
from pathlib import Path

try:
    from .exceptions import ValidationError, SecurityError
except ImportError:
    # For direct module loading
    from exceptions import ValidationError, SecurityError


class Validators:
    """Collection of validation functions."""
    
    # Valid cloud providers
    VALID_PROVIDERS = {"aws", "azure", "digitalocean", "hetzner"}
    
    # Valid regions per provider
    VALID_REGIONS = {
        "aws": {
            "us-east-1", "us-east-2", "us-west-1", "us-west-2",
            "eu-west-1", "eu-west-2", "eu-west-3", "eu-central-1",
            "ap-southeast-1", "ap-southeast-2", "ap-northeast-1",
            "ap-northeast-2", "ap-south-1", "ca-central-1",
            "sa-east-1", "ap-east-1", "me-south-1", "af-south-1"
        },
        "azure": {
            "eastus", "eastus2", "westus", "westus2", "westus3",
            "centralus", "northcentralus", "southcentralus",
            "westeurope", "northeurope", "uksouth", "ukwest",
            "eastasia", "southeastasia", "japaneast", "japanwest",
            "australiaeast", "australiasoutheast", "centralindia",
            "southindia", "westindia", "brazilsouth", "canadacentral",
            "canadaeast", "francecentral", "germanywestcentral",
            "koreacentral", "norwayeast", "southafricanorth",
            "switzerlandnorth", "uaenorth"
        },
        "digitalocean": {
            "nyc1", "nyc3", "sfo1", "sfo2", "sfo3",
            "ams2", "ams3", "sgp1", "lon1", "fra1",
            "tor1", "blr1", "syd1"
        },
        "hetzner": {
            "fsn1", "nbg1", "hel1", "ash", "hil"
        }
    }
    
    # Valid instance types per provider
    VALID_INSTANCE_TYPES = {
        "aws": {
            "t3.nano", "t3.micro", "t3.small", "t3.medium", "t3.large",
            "t3.xlarge", "t3.2xlarge", "t2.nano", "t2.micro", "t2.small",
            "m5.large", "m5.xlarge", "c5.large", "c5.xlarge"
        },
        "azure": {
            "Standard_B1s", "Standard_B1ms", "Standard_B2s", "Standard_B2ms",
            "Standard_B4ms", "Standard_B8ms", "Standard_D2s_v3", "Standard_D4s_v3",
            "Standard_A1_v2", "Standard_A2_v2"
        },
        "digitalocean": {
            "s-1vcpu-1gb", "s-1vcpu-2gb", "s-2vcpu-2gb", "s-2vcpu-4gb",
            "s-4vcpu-8gb", "c-2", "c-4", "c-8"
        },
        "hetzner": {
            "cx11", "cx21", "cx31", "cx41", "cx51",
            "cpx11", "cpx21", "cpx31", "cpx41", "cpx51"
        }
    }
    
    @staticmethod
    def validate_provider(provider: str) -> str:
        """Validate cloud provider."""
        if not provider:
            raise ValidationError(
                "Provider is required",
                field="provider",
                suggestions=["Use one of: aws, azure, digitalocean, hetzner"]
            )
        
        provider = provider.lower().strip()
        if provider not in Validators.VALID_PROVIDERS:
            raise ValidationError(
                f"Invalid provider '{provider}'",
                field="provider",
                suggestions=[
                    f"Valid providers are: {', '.join(sorted(Validators.VALID_PROVIDERS))}",
                    "Check spelling and use lowercase"
                ]
            )
        
        return provider
    
    @staticmethod
    def validate_regions(provider: str, regions: Union[str, List[str]]) -> List[str]:
        """Validate regions for a provider."""
        if not regions:
            raise ValidationError(
                "At least one region is required",
                field="regions",
                suggestions=["Specify regions as comma-separated list"]
            )
        
        # Convert string to list
        if isinstance(regions, str):
            regions = [r.strip() for r in regions.split(",") if r.strip()]
        
        if not regions:
            raise ValidationError(
                "No valid regions found",
                field="regions",
                suggestions=["Check region format and try again"]
            )
        
        # Validate provider first
        provider = Validators.validate_provider(provider)
        
        valid_regions = Validators.VALID_REGIONS.get(provider, set())
        invalid_regions = []
        
        for region in regions:
            region = region.strip()
            if not region:
                continue
                
            # Basic format validation
            if not re.match(r'^[a-z0-9\-]+$', region):
                invalid_regions.append(region)
                continue
            
            # Check against known regions
            if region not in valid_regions:
                invalid_regions.append(region)
        
        if invalid_regions:
            valid_examples = list(valid_regions)[:5]
            raise ValidationError(
                f"Invalid regions for {provider}: {', '.join(invalid_regions)}",
                field="regions",
                suggestions=[
                    f"Valid {provider} regions include: {', '.join(valid_examples)}",
                    "Check region names for typos",
                    "Use lowercase with hyphens only"
                ]
            )
        
        return regions
    
    @staticmethod
    def validate_instance_type(provider: str, instance_type: Optional[str]) -> Optional[str]:
        """Validate instance type for a provider."""
        if not instance_type:
            return None
        
        provider = Validators.validate_provider(provider)
        valid_types = Validators.VALID_INSTANCE_TYPES.get(provider, set())
        
        if instance_type not in valid_types:
            examples = list(valid_types)[:5]
            raise ValidationError(
                f"Invalid instance type '{instance_type}' for {provider}",
                field="instance_type",
                suggestions=[
                    f"Valid {provider} instance types include: {', '.join(examples)}",
                    "Check instance type format",
                    "Use exact case-sensitive names"
                ]
            )
        
        return instance_type
    
    @staticmethod
    def validate_deployment_id(deployment_id: str) -> str:
        """Validate deployment ID format."""
        if not deployment_id:
            raise ValidationError(
                "Deployment ID is required",
                field="deployment_id",
                suggestions=["Use format: provider-region-uid (e.g., aws-us-east-1-123456)"]
            )
        
        # Check basic format: provider-region-uid
        pattern = r'^(aws|azure|digitalocean|hetzner)-[a-z0-9\-]+$'
        if not re.match(pattern, deployment_id):
            raise ValidationError(
                f"Invalid deployment ID format: {deployment_id}",
                field="deployment_id",
                suggestions=[
                    "Use format: provider-region-uid",
                    "Example: aws-us-east-1-123456",
                    "Use only lowercase letters, numbers, and hyphens"
                ]
            )
        
        parts = deployment_id.split('-')
        if len(parts) < 3:
            raise ValidationError(
                f"Deployment ID must have at least 3 parts: {deployment_id}",
                field="deployment_id",
                suggestions=["Format: provider-region-uid"]
            )
        
        # Validate provider part
        provider = parts[0]
        Validators.validate_provider(provider)
        
        return deployment_id
    
    @staticmethod
    def validate_client_name(name: str) -> str:
        """Validate client name."""
        if not name:
            raise ValidationError(
                "Client name is required",
                field="name",
                suggestions=["Use alphanumeric characters and underscores only"]
            )
        
        name = name.strip()
        
        # Check length
        if len(name) < 1 or len(name) > 50:
            raise ValidationError(
                f"Client name must be 1-50 characters: {name}",
                field="name",
                suggestions=["Use shorter, descriptive names"]
            )
        
        # Check format
        if not re.match(r'^[a-zA-Z0-9_\-]+$', name):
            raise ValidationError(
                f"Invalid client name format: {name}",
                field="name",
                suggestions=[
                    "Use only letters, numbers, underscores, and hyphens",
                    "No spaces or special characters allowed"
                ]
            )
        
        return name
    
    @staticmethod
    def validate_file_path(path: Union[str, Path], must_exist: bool = False) -> Path:
        """Validate file path."""
        if not path:
            raise ValidationError(
                "File path is required",
                field="path",
                suggestions=["Provide a valid file path"]
            )
        
        path = Path(path).resolve()
        
        # Security check - prevent path traversal
        try:
            # This will raise ValueError if path tries to escape
            path.relative_to(Path.cwd().parent)
        except ValueError:
            raise SecurityError(
                f"Path traversal detected: {path}",
                suggestions=["Use paths within the project directory"]
            )
        
        if must_exist and not path.exists():
            raise ValidationError(
                f"File does not exist: {path}",
                field="path",
                suggestions=[
                    "Check the file path is correct",
                    "Verify file permissions",
                    "Create the file if it should exist"
                ]
            )
        
        return path
    
    @staticmethod
    def validate_ip_address(ip: str) -> str:
        """Validate IP address format."""
        if not ip:
            raise ValidationError(
                "IP address is required",
                field="ip",
                suggestions=["Provide a valid IPv4 or IPv6 address"]
            )
        
        try:
            ipaddress.ip_address(ip)
            return ip
        except ValueError:
            raise ValidationError(
                f"Invalid IP address: {ip}",
                field="ip",
                suggestions=[
                    "Use valid IPv4 format (e.g., 192.168.1.1)",
                    "Use valid IPv6 format (e.g., 2001:db8::1)",
                    "Check for typos in the IP address"
                ]
            )
    
    @staticmethod
    def validate_port(port: Union[int, str]) -> int:
        """Validate port number."""
        try:
            port = int(port)
        except (ValueError, TypeError):
            raise ValidationError(
                f"Invalid port number: {port}",
                field="port",
                suggestions=["Use a number between 1 and 65535"]
            )
        
        if port < 1 or port > 65535:
            raise ValidationError(
                f"Port number out of range: {port}",
                field="port",
                suggestions=["Use a port between 1 and 65535"]
            )
        
        # Check for common restricted ports
        restricted_ports = {22, 23, 25, 53, 80, 110, 143, 443, 993, 995}
        if port in restricted_ports:
            raise ValidationError(
                f"Port {port} is commonly restricted",
                field="port",
                suggestions=[
                    "Consider using a different port",
                    "Default WireGuard port is 51820",
                    "Use ports above 1024 for better compatibility"
                ]
            )
        
        return port
    
    @staticmethod
    def validate_email(email: str) -> str:
        """Validate email address format."""
        if not email:
            raise ValidationError(
                "Email address is required",
                field="email",
                suggestions=["Provide a valid email address"]
            )
        
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, email):
            raise ValidationError(
                f"Invalid email format: {email}",
                field="email",
                suggestions=[
                    "Use format: user@domain.com",
                    "Check for typos in email address"
                ]
            )
        
        return email.lower()
    
    @staticmethod
    def sanitize_input(input_str: str, max_length: int = 1000) -> str:
        """Sanitize user input to prevent injection attacks."""
        if not input_str:
            return ""
        
        # Truncate if too long
        if len(input_str) > max_length:
            input_str = input_str[:max_length]
        
        # Remove null bytes
        input_str = input_str.replace('\x00', '')
        
        # Remove control characters except common whitespace
        import unicodedata
        cleaned = ""
        for char in input_str:
            if unicodedata.category(char) in ('Cc', 'Cf') and char not in '\t\n\r ':
                continue
            cleaned += char
        
        return cleaned.strip()
    
    @staticmethod
    def validate_command_args(args: Dict[str, Any]) -> Dict[str, Any]:
        """Validate command arguments comprehensively."""
        validated = {}
        
        # Validate provider if present
        if 'provider' in args and args['provider']:
            validated['provider'] = Validators.validate_provider(args['provider'])
        
        # Validate regions if present
        if 'regions' in args and args['regions']:
            provider = validated.get('provider') or args.get('provider')
            if provider:
                validated['regions'] = Validators.validate_regions(provider, args['regions'])
        
        # Validate instance type if present
        if 'instance_type' in args and args['instance_type']:
            provider = validated.get('provider') or args.get('provider')
            if provider:
                validated['instance_type'] = Validators.validate_instance_type(
                    provider, args['instance_type']
                )
        
        # Validate deployment ID if present
        if 'deployment_id' in args and args['deployment_id']:
            validated['deployment_id'] = Validators.validate_deployment_id(args['deployment_id'])
        
        # Validate client name if present
        if 'client_name' in args and args['client_name']:
            validated['client_name'] = Validators.validate_client_name(args['client_name'])
        
        # Copy other validated args
        for key, value in args.items():
            if key not in validated and value is not None:
                validated[key] = value
        
        return validated


def validate_input(validator_func):
    """Decorator to validate function inputs."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                # Apply validation
                validated_kwargs = validator_func(kwargs)
                return func(*args, **validated_kwargs)
            except ValidationError:
                raise
            except Exception as e:
                raise ValidationError(
                    f"Validation failed: {str(e)}",
                    suggestions=["Check input parameters and try again"]
                )
        return wrapper
    return decorator