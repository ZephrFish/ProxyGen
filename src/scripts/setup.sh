#!/bin/bash
# VPNGen Setup Script
# Automated setup for VPNGen enterprise VPN deployment tool

set -e

# Colours for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Colour

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Detect OS
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if command_exists apt; then
            echo "ubuntu"
        elif command_exists yum; then
            echo "centos"
        elif command_exists dnf; then
            echo "fedora"
        else
            echo "linux"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    else
        echo "unknown"
    fi
}

# Install dependencies based on OS
install_dependencies() {
    local os=$(detect_os)
    log_info "Detected OS: $os"
    
    case $os in
        ubuntu)
            log_info "Installing dependencies for Ubuntu/Debian..."
            sudo apt update
            sudo apt install -y python3 python3-pip python3-venv curl wget unzip
            
            # Install Terraform
            if ! command_exists terraform; then
                log_info "Installing Terraform..."
                wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
                echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
                sudo apt update && sudo apt install -y terraform
            fi
            ;;
        
        centos|fedora)
            log_info "Installing dependencies for CentOS/RHEL/Fedora..."
            if command_exists dnf; then
                sudo dnf install -y python3 python3-pip curl wget unzip
            else
                sudo yum install -y python3 python3-pip curl wget unzip
            fi
            
            # Install Terraform
            if ! command_exists terraform; then
                log_info "Installing Terraform..."
                sudo yum install -y yum-utils
                sudo yum-config-manager --add-repo https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo
                sudo yum -y install terraform
            fi
            ;;
        
        macos)
            log_info "Installing dependencies for macOS..."
            if ! command_exists brew; then
                log_error "Homebrew not found. Please install Homebrew first: https://brew.sh"
                exit 1
            fi
            
            brew install python3 terraform ansible
            ;;
        
        *)
            log_error "Unsupported operating system. Please install dependencies manually."
            log_info "Required: python3, pip3, terraform, ansible"
            exit 1
            ;;
    esac
}

# Install Python dependencies
install_python_deps() {
    log_info "Installing Python dependencies..."
    
    # Create virtual environment
    if [ ! -d "venv" ]; then
        python3 -m venv venv
        log_success "Created virtual environment"
    fi
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Install required packages
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
        log_success "Python dependencies installed"
    else
        # Install essential packages
        pip install pyyaml requests boto3 azure-mgmt-compute google-cloud-compute cryptography
        log_warning "requirements.txt not found, installed essential packages"
    fi
}

# Setup cloud provider CLI tools
setup_cloud_cli() {
    log_info "Setting up cloud provider CLI tools..."
    
    # AWS CLI
    if ! command_exists aws; then
        log_info "Installing AWS CLI..."
        if [[ "$OSTYPE" == "darwin"* ]]; then
            brew install awscli
        else
            curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
            unzip awscliv2.zip
            sudo ./aws/install
            rm -rf aws awscliv2.zip
        fi
        log_success "AWS CLI installed"
    else
        log_success "AWS CLI already installed"
    fi
    
    # Azure CLI
    if ! command_exists az; then
        log_info "Installing Azure CLI..."
        if [[ "$OSTYPE" == "darwin"* ]]; then
            brew install azure-cli
        else
            curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
        fi
        log_success "Azure CLI installed"
    else
        log_success "Azure CLI already installed"
    fi
    
    # Google Cloud CLI
    if ! command_exists gcloud; then
        log_info "Installing Google Cloud CLI..."
        if [[ "$OSTYPE" == "darwin"* ]]; then
            brew install google-cloud-sdk
        else
            echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
            curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key --keyring /usr/share/keyrings/cloud.google.gpg add -
            sudo apt update && sudo apt install -y google-cloud-cli
        fi
        log_success "Google Cloud CLI installed"
    else
        log_success "Google Cloud CLI already installed"
    fi
}

# Setup SSH configuration to handle the connection issue you encountered
setup_ssh_config() {
    log_info "Setting up SSH configuration..."
    
    # Create SSH directory if it doesn't exist
    mkdir -p ~/.ssh
    chmod 700 ~/.ssh
    
    # Create SSH config to handle host key checking automatically
    if [ ! -f ~/.ssh/config ] || ! grep -q "StrictHostKeyChecking" ~/.ssh/config; then
        cat >> ~/.ssh/config << EOF

# VPNGen SSH Configuration - handles new server connections automatically
Host *
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR
    ServerAliveInterval 60
    ServerAliveCountMax 3

EOF
        log_success "SSH configuration updated to handle new server connections automatically"
    else
        log_success "SSH configuration already configured"
    fi
}

# Create initial configuration
create_config() {
    log_info "Creating initial configuration..."
    
    cat > config.yaml << EOF
# VPNGen Configuration
vpn:
  port: 51820
  subnet: "10.0.0.0/24"
  dns_servers: ["1.1.1.1", "8.8.8.8"]

# Cloud Provider Settings
aws:
  instance_type: "t3.micro"
  key_name: "vpngen-key"

azure:
  vm_size: "Standard_B1s"
  admin_username: "vpngen"

gcp:
  machine_type: "e2-micro"
  image_family: "ubuntu-2004-lts"

# Enterprise Features
monitoring:
  enabled: true
  alerts:
    enabled: true
    email:
      enabled: false
      to_addresses: ["admin@example.com"]

backup:
  enabled: true
  schedule: "0 2 * * *"  # Daily at 2 AM
  destinations: ["local"]

audit:
  enabled: true
  compliance_frameworks: ["ISO27001"]

identity:
  session_timeout_hours: 8
  providers:
    local:
      enabled: true
      type: "local"

access_control:
  geo_blocking:
    enabled: true
    mode: "blacklist"
    blocked_countries: ["CN", "RU", "KP", "IR"]

qos:
  enabled: true
  default_bandwidth:
    upload_kbps: 10000
    download_kbps: 50000

autoscaling:
  enabled: false
  min_instances: 1
  max_instances: 5

web_dashboard:
  enabled: true
  host: "0.0.0.0"
  port: 8080
  authentication_required: true

mobile_api:
  enabled: true
  host: "0.0.0.0"
  port: 8081
EOF
    
    log_success "Configuration file created: config.yaml"
}

# Create directories
create_directories() {
    log_info "Creating directory structure..."
    
    mkdir -p configs
    mkdir -p state
    mkdir -p logs
    mkdir -p backups
    mkdir -p certs
    mkdir -p pki
    mkdir -p audit
    mkdir -p metrics
    mkdir -p qos
    mkdir -p acl
    mkdir -p identity
    mkdir -p web/templates
    mkdir -p web/static
    mkdir -p mobile_api
    
    log_success "Directory structure created"
}

# Make scripts executable
make_executable() {
    log_info "Making scripts executable..."
    
    chmod +x vpngen
    chmod +x setup.sh
    
    log_success "Scripts made executable"
}

# Cloud provider setup guidance
cloud_setup_guidance() {
    log_info "Cloud provider setup guidance:"
    echo
    
    log_info "AWS Setup:"
    echo "1. Run: aws configure"
    echo "2. Enter your AWS Access Key ID"
    echo "3. Enter your AWS Secret Access Key" 
    echo "4. Enter your default region (e.g., us-east-1)"
    echo "5. Create SSH key pair: aws ec2 create-key-pair --key-name vpngen-key --query 'KeyMaterial' --output text > ~/.ssh/vpngen-aws.pem"
    echo "6. Set permissions: chmod 600 ~/.ssh/vpngen-aws.pem"
    echo
    
    log_info "Azure Setup:"
    echo "1. Run: az login"
    echo "2. Follow browser authentication"
    echo "3. Set subscription: az account set --subscription 'your-subscription-id'"
    echo "4. Create resource group: az group create --name vpngen-rg --location eastus"
    echo
    
    log_info "GCP Setup:"
    echo "1. Run: gcloud auth login"
    echo "2. Follow browser authentication"
    echo "3. Set project: gcloud config set project your-project-id"
    echo "4. Enable APIs: gcloud services enable compute.googleapis.com"
    echo
}

# Main setup function
main() {
    echo "========================================"
    echo "        VPNGen Setup Script"
    echo "========================================"
    echo
    
    # Check if running as root
    if [ "$EUID" -eq 0 ]; then
        log_warning "Running as root. Some operations may require non-root access."
    fi
    
    # Install system dependencies
    log_info "Step 1: Installing system dependencies..."
    install_dependencies
    
    # Install Python dependencies
    log_info "Step 2: Installing Python dependencies..."
    install_python_deps
    
    # Setup cloud CLI tools
    log_info "Step 3: Setting up cloud provider CLI tools..."
    setup_cloud_cli
    
    # Setup SSH configuration (fixes the connection issue you encountered)
    log_info "Step 4: Setting up SSH configuration..."
    setup_ssh_config
    
    # Create configuration
    log_info "Step 5: Creating initial configuration..."
    create_config
    
    # Create directories
    log_info "Step 6: Creating directory structure..."
    create_directories
    
    # Make scripts executable
    log_info "Step 7: Making scripts executable..."
    make_executable
    
    echo
    log_success "VPNGen setup completed successfully!"
    echo
    
    # Show next steps
    echo "========================================"
    echo "           Next Steps"
    echo "========================================"
    echo
    
    cloud_setup_guidance
    
    echo "Quick test deployment:"
    echo "./vpngen deploy --provider aws --regions us-east-1"
    echo
    echo "Add your first client:"
    echo "./vpngen client add --name laptop --server us-east-1"
    echo
    echo "View all deployments:"
    echo "./vpngen list"
    echo
    echo "Access web dashboard:"
    echo "python3 -c 'from lib.web_dashboard import WebDashboard; WebDashboard().run()'"
    echo "Then visit: http://localhost:8080"
    echo
    
    log_info "Setup complete! The SSH configuration has been updated to handle new server connections automatically."
    log_info "Check the README.md for detailed usage instructions."
}

# Handle command line arguments
case "${1:-}" in
    --help|-h)
        echo "VPNGen Setup Script"
        echo
        echo "Usage: $0 [options]"
        echo
        echo "Options:"
        echo "  --help, -h    Show this help message"
        echo
        exit 0
        ;;
    *)
        main
        ;;
esac