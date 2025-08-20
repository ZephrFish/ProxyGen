# ProxyGen

Multi-cloud secure proxy/endpoint deployment tool for AWS, Azure, DigitalOcean, and Hetzner. Allowing traffic routing through cloud providers

> **Provider Status**: DigitalOcean and Hetzner Cloud support are currently in **ALPHA** - semi-tested and may require manual intervention. AWS and Azure are fully supported.

_Blog post coming soon_

## Quick Start

```bash
# Interactive wizard deployment (recommended)
./proxygen deploy --provider aws --wizard

# Or deploy directly with regions
./proxygen deploy --provider aws --regions us-east-1

# Add a client
./proxygen client add --name laptop --server us-east-1

# Get client config
cat configs/client-laptop.conf

# List deployments
./proxygen list

# Destroy deployment
./proxygen destroy --id aws-us-east-1-abc123
```

## Installation

### Prerequisites

- **Operating System**: Linux or macOS
- **Python**: 3.7+
- **Terraform**: 1.0+
- **Ansible**: 2.9+

### Install on Ubuntu/Debian

```bash
# Install dependencies
sudo apt update
sudo apt install -y python3 python3-pip terraform ansible awscli

# Install Azure CLI
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
```

### Install on macOS

```bash
# Install Homebrew if needed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install tools
brew install python@3.11 terraform ansible awscli azure-cli
```

### Setup ProxyGen

```bash
# Clone repository
git clone https://github.com/ZephrFish/ProxyGen
cd proxygen

# Make executable
chmod +x proxygen

# Setup environment and credentials
./proxygen setup --all
```

## Cloud Provider Setup

### AWS Setup

```bash
# Configure credentials
aws configure  # or use: ./proxygen setup --credentials

# Enter when prompted:
# AWS Access Key ID: [your-key]
# AWS Secret Access Key: [your-secret]
# Default region: us-east-1
# Default output: json
```

**Required IAM Permissions:**
- EC2 Full Access
- VPC Full Access
- IAM role creation

### Azure Setup

```bash
# Login
az login

# Set subscription
az account list --output table
az account set --subscription "Your-Subscription"

# Create service principal
az ad sp create-for-rbac --name "proxygen-terraform" --role="Contributor"

# Set environment variables
export AZURE_SUBSCRIPTION_ID="your-subscription-id"
export AZURE_TENANT_ID="your-tenant-id"
export AZURE_CLIENT_ID="your-client-id"
export AZURE_CLIENT_SECRET="your-client-secret"
```

### DigitalOcean Setup

> **ALPHA Warning**: DigitalOcean support is experimental and may require manual intervention.

```bash
# Install CLI
brew install doctl  # macOS
sudo snap install doctl  # Linux

# Create API token at https://cloud.digitalocean.com/account/api/tokens

# Authenticate
doctl auth init

# Set environment
export DIGITALOCEAN_TOKEN="your-api-token"
```

### Hetzner Setup

> **ALPHA Warning**: Hetzner support is experimental and may require manual intervention.

```bash
# Install CLI
brew install hcloud  # macOS
# Or download from https://github.com/hetznercloud/cli/releases

# Create API token at https://console.hetzner.cloud/projects

# Configure
hcloud context create proxygen

# Set environment
export HCLOUD_TOKEN="your-api-token"
```

## Commands Reference

### Available Commands

- **`deploy`** - Deploy proxy infrastructure to cloud providers
- **`list`** - List, manage, and sync deployments
- **`setup`** - Setup environment and cloud credentials
- **`client`** - Manage client configurations
- **`destroy`** - Destroy proxy infrastructure
- **`multihop`** - Create and manage multi-hop proxy chains
- **`examples`** - Show usage examples

### Deploy Command

```bash
# Interactive wizard mode (recommended for beginners)
./proxygen deploy --provider aws --wizard
./proxygen deploy --provider azure --wizard

# Basic deployment
./proxygen deploy --provider aws --regions us-east-1

# Multi-region
./proxygen deploy --provider aws --regions us-east-1,eu-west-1,ap-southeast-1

# With instance type
./proxygen deploy --provider azure --regions uksouth --instance-type Standard_B2s

# DigitalOcean deployment
./proxygen deploy --provider digitalocean --regions nyc1

# Hetzner deployment
./proxygen deploy --provider hetzner --regions fsn1

# Dry run
./proxygen deploy --provider digitalocean --regions nyc1 --dry-run
```

#### Wizard Mode

The `--wizard` flag launches an interactive deployment wizard that guides you through:

- **Region Selection**: Choose from all available regions for your provider
- **Instance Type**: Use defaults or specify custom instance types
- **Deployment Mode**: Choose between real deployment or dry-run
- **Provider Status**: Clear indication of alpha vs. stable providers
- **Cost Information**: See pricing estimates before deployment

Example wizard session:
```bash
./proxygen deploy --provider aws --wizard

ProxyGen Deployment Wizard - AWS
============================================================
Provider: Amazon Web Services
Status: Fully Supported
Default Instance: t3.nano (~$3.80/month)

Available Regions:
------------------------------
 1. us-east-1          - US East (N. Virginia)
 2. us-west-2          - US West (Oregon)
 3. eu-west-1          - EU (Ireland)
 4. eu-central-1       - EU (Frankfurt)
 5. ap-southeast-1     - Asia Pacific (Singapore)
 6. ap-northeast-1     - Asia Pacific (Tokyo)
 7. ca-central-1       - Canada (Montreal)
 8. sa-east-1          - South America (São Paulo)
 9. ap-south-1         - Asia Pacific (Mumbai)
10. eu-north-1         - EU (Stockholm)

Select regions (enter numbers separated by commas, or 'all' for all regions):
Regions: 1,3
```

### Client Management

```bash
# Add client
./proxygen client add --name laptop --server us-east-1

# List clients
./proxygen client list
./proxygen client list --server us-east-1

# Remove client
./proxygen client remove --name laptop --server us-east-1

# Get config
cat configs/client-laptop.conf
```

### List and Manage Deployments

```bash
# Basic list
./proxygen list

# Detailed view with full information
./proxygen list --detailed

# Export to different formats
./proxygen list --export json
./proxygen list --export csv
./proxygen list --export yaml

# Clean up old destroyed deployments
./proxygen list --cleanup --days 30

# Combine operations
./proxygen list --detailed --export json
```

### Destroy Deployments

```bash
# By provider and region
./proxygen destroy --provider aws --regions us-east-1

# By deployment ID
./proxygen destroy --id aws-us-east-1-abc123

# Force destroy
./proxygen destroy --provider aws --regions us-east-1 --force

# Multiple regions
./proxygen destroy --provider aws --regions us-east-1,eu-west-1
```

### Setup Command

```bash
# Setup everything (SSH keys + cloud credentials)
./proxygen setup --all

# Setup SSH configuration only
./proxygen setup --ssh

# Setup cloud provider credentials only
./proxygen setup --credentials

# Show cloud setup commands
./proxygen setup --help
```

### Remote Discovery and Sync

```bash
# Discover all cloud deployments
./proxygen list --remote

# Sync local state with cloud
./proxygen list --sync

# Discover specific provider
./proxygen list --remote --provider aws
./proxygen list --remote --provider azure
```

## Instance Types and Pricing

### AWS Instance Types

| Type | vCPUs | Memory | Storage | Monthly Cost | Use Case |
|------|-------|--------|---------|--------------|----------|
| **t3.nano** | 2 | 0.5 GB | EBS only | ~$3.80 | Personal (1-5 users) |
| t3.micro | 2 | 1 GB | EBS only | ~$7.59 | Personal (5-10 users) |
| t3.small | 2 | 2 GB | EBS only | ~$15.18 | Small team (10-20 users) |
| t3.medium | 2 | 4 GB | EBS only | ~$30.37 | Team (20-50 users) |
| t3.large | 2 | 8 GB | EBS only | ~$60.74 | Business (50-100 users) |

### Azure Instance Types

| Type | vCPUs | Memory | Storage | Monthly Cost | Use Case |
|------|-------|--------|---------|--------------|----------|
| **Standard_B1s** | 1 | 1 GB | 4 GB | ~$3.80 | Personal (1-5 users) |
| Standard_B1ms | 1 | 2 GB | 4 GB | ~$7.59 | Personal (5-10 users) |
| Standard_B2s | 2 | 4 GB | 8 GB | ~$30.37 | Small team (10-25 users) |
| Standard_B2ms | 2 | 8 GB | 16 GB | ~$60.74 | Team (25-50 users) |
| Standard_D2s_v3 | 2 | 8 GB | 16 GB | ~$70.08 | Business (50-100 users) |

### DigitalOcean Instance Types

> **ALPHA**: DigitalOcean deployment is experimental

| Type | vCPUs | Memory | Storage | Monthly Cost | Use Case |
|------|-------|--------|---------|--------------|----------|
| **s-1vcpu-1gb** | 1 | 1 GB | 25 GB | ~$6.00 | Personal (1-5 users) |
| s-1vcpu-2gb | 1 | 2 GB | 50 GB | ~$12.00 | Personal (5-10 users) |
| s-2vcpu-2gb | 2 | 2 GB | 60 GB | ~$18.00 | Small team (10-20 users) |
| s-2vcpu-4gb | 2 | 4 GB | 80 GB | ~$24.00 | Team (20-50 users) |
| s-4vcpu-8gb | 4 | 8 GB | 160 GB | ~$48.00 | Business (50-100 users) |

### Hetzner Instance Types

> **ALPHA**: Hetzner deployment is experimental

| Type | vCPUs | Memory | Storage | Monthly Cost | Use Case |
|------|-------|--------|---------|--------------|----------|
| **cx11** | 1 | 2 GB | 20 GB | ~€3.29 (~$3.60) | Personal (1-5 users) |
| cx21 | 2 | 4 GB | 40 GB | ~€5.83 (~$6.40) | Personal (5-10 users) |
| cx31 | 2 | 8 GB | 80 GB | ~€10.59 (~$11.60) | Small team (10-25 users) |
| cx41 | 4 | 16 GB | 160 GB | ~€20.09 (~$22.00) | Team (25-50 users) |
| cx51 | 8 | 32 GB | 240 GB | ~€39.19 (~$43.00) | Business (50-100 users) |

### Total Monthly Costs

Costs include: Instance + Public IP (~$3.65/month) + Storage (20GB ~$2/month)

| Users | Recommended | AWS | Azure | DigitalOcean* | Hetzner* |
|-------|-------------|-----|-------|---------------|----------|
| 1-5 | Nano/Micro | ~$10 | ~$10 | ~$6 | ~$4 |
| 5-20 | Small | ~$23 | ~$38 | ~$18 | ~$7 |
| 20-50 | Medium | ~$38 | ~$68 | ~$24 | ~$12 |
| 50-100 | Large | ~$68 | ~$78 | ~$48 | ~$22 |

*Alpha providers - use at your own risk

## Client Configuration

### WireGuard Client Setup

#### Windows

1. Download WireGuard: https://www.wireguard.com/install/
2. Install WireGuard client
3. Import config file: `client-laptop.conf`
4. Activate tunnel

#### macOS

```bash
# Install WireGuard
brew install wireguard-tools

# Option 1: Use GUI app from WireGuard website

# Option 2: Command line
sudo wg-quick up /path/to/client-laptop.conf
```

#### Linux

```bash
# Install WireGuard
sudo apt install wireguard  # Debian/Ubuntu
sudo yum install wireguard  # RHEL/CentOS
sudo pacman -S wireguard    # Arch

# Copy config
sudo cp client-laptop.conf /etc/wireguard/wg0.conf

# Start connection
sudo wg-quick up wg0

# Enable auto-start
sudo systemctl enable wg-quick@wg0
```


### Configuration File Format

```ini
[Interface]
PrivateKey = <client_private_key>
Address = 10.0.0.2/32
DNS = 1.1.1.1, 1.0.0.1

[Peer]
PublicKey = <server_public_key>
Endpoint = <server_ip>:51820
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
```

## Multi-Hop Proxy

### Create Chain

```bash
# Simple chain
./proxygen multihop create --name privacy-chain \
    --providers aws,azure,digitalocean \
    --regions us-east-1,uksouth,nyc1

# Maximum privacy
./proxygen multihop create --name max-privacy \
    --providers aws,aws,azure,hetzner \
    --regions us-west-2,eu-west-1,uksouth,fsn1 \
    --preset paranoid
```

### Presets

- **standard**: 3 hops, mixed regions
- **paranoid**: 4+ hops, maximum geographic distribution
- **performance**: 2 hops, optimised for speed
- **balanced**: 3 hops, balance of privacy and performance

### Test Chain

```bash
# Test connectivity
./proxygen multihop test --name privacy-chain

# Show route
./proxygen multihop show --name privacy-chain

# List all chains
./proxygen multihop list
```

## File Structure

```
proxygen/
├── proxygen                  # Main CLI executable
├── README.md                # This documentation
├── config/                  # Configuration files
│   ├── config.yaml         # Main configuration
│   └── requirements.txt    # Python dependencies
├── src/
│   ├── proxygen.py         # Main application
│   ├── lib/                # Core modules (12 files)
│   │   ├── progress_bar.py # Progress tracking
│   │   ├── exceptions.py   # Error handling
│   │   ├── validators.py   # Input validation
│   │   └── ...            # Other core modules
│   ├── lib_enterprise/     # Enterprise modules (optional)
│   ├── terraform/          # Infrastructure as code
│   │   ├── aws/           # AWS deployments
│   │   ├── azure/         # Azure deployments
│   │   ├── digitalocean/  # DigitalOcean deployments
│   │   └── hetzner/       # Hetzner deployments
│   ├── ansible/           # Configuration management
│   ├── scripts/           # Setup and utility scripts
│   └── tests/             # Test suite (dev only)
├── state/                 # Deployment state and SSH keys
├── configs/               # Generated client configurations
└── docker/                # Container support
```

## State Management

- **Terraform State**: `state/*.tfstate`
- **SSH Keys**: `state/proxygen-{region}-key.pem`
- **Deployment Tracking**: `state/deployment_inventory.json`
- **Client Configs**: `configs/client-*.conf`

### Backup and Recovery

```bash
# Backup state
tar -czf proxygen-backup.tar.gz state/ configs/

# Restore state
tar -xzf proxygen-backup.tar.gz

# Import existing resources
cd terraform/aws
terraform import aws_instance.vpn i-1234567890
```

## Common Errors

### Invalid Provider
```
Invalid provider 'invalid_provider'
```
**Solution**: Use `aws`, `azure`, `digitalocean`, or `hetzner`

### Invalid Region
```
Invalid regions for aws: invalid-region
```
**Solution**: Check valid regions for your provider

### No Active Deployments
```
No active deployments found
```
**Solution**: Deploy a server first with `./proxygen deploy`

### SSH Connection Failed
```
Failed to establish SSH connection
```
**Solution**: 
- Check security groups allow port 22
- Verify instance is running
- Wait for instance initialisation

### Terraform State Locked
```
Terraform state is locked
```
**Solution**: 
- Wait for other operations
- Force unlock: `terraform force-unlock <lock-id>`

### Authentication Failed
```
Authentication failed for provider
```
**Solution**:
- AWS: Run `aws configure`
- Azure: Run `az login`
- DigitalOcean: Run `doctl auth init`
- Hetzner: Run `hcloud context create`

### Error Severity Levels

- **CRITICAL**: Security violations, stop immediately
- **HIGH**: Authentication/network issues, review and retry
- **MEDIUM**: Input validation, correct and retry
- **LOW**: Warnings, note for future

## Troubleshooting

### Connection Issues

```bash
# Check server status
ssh -i state/proxygen-us-east-1-key.pem ubuntu@<server-ip>
sudo systemctl status proxygen-quick@proxy0
sudo proxygen show

# Check firewall
sudo iptables -L -n -v

# Test DNS
systemd-resolve --status
```

### State Issues

```bash
# Reset state
rm state/*.tfstate*
./proxygen deploy --provider aws --regions us-east-1

# Import existing
terraform import aws_instance.vpn <instance-id>
```

### Cloud Provider Issues

```bash
# Verify AWS credentials
aws sts get-caller-identity

# Verify Azure login
az account show

# Verify DigitalOcean auth
doctl auth list

# Verify Hetzner auth
hcloud context list
```

### Logs

```bash
# View logs
tail -f proxygen.log

# Check terraform logs
cat state/*.tflog

# Check ansible logs
cat ansible/*.log
```

### Performance

```bash
# Check server load
ssh -i state/key.pem ubuntu@<ip>
htop
iostat -x 1
iftop

# WireGuard stats
sudo wg show
```

## Project Architecture

### Core Features

ProxyGen provides a clean, focused codebase with essential proxy deployment features:

- **Multi-cloud deployment**: AWS, Azure, DigitalOcean (Alpha), Hetzner (Alpha)
- **Client management**: Add, remove, and configure WireGuard clients
- **Multi-hop proxy chains**: Create privacy-focused proxy chains
- **Cost tracking**: Monitor deployment costs across providers
- **Resource discovery**: Automatic cloud resource detection
- **Error handling**: Comprehensive error management with suggestions
- **Progress tracking**: Real-time feedback during operations

### Architecture Benefits

1. **Simplified Core**: Only essential modules for basic functionality
2. **Clean Structure**: Clear separation between core and enterprise features
3. **Reduced Complexity**: Focused codebase with 12 core Python modules
4. **Easy Maintenance**: Well-organised code with comprehensive testing
5. **Optional Extensions**: Enterprise features available when needed
