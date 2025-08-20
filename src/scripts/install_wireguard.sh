#!/bin/bash

# Script to install WireGuard tools locally (optional)
# Not required for deployment, but useful for local key generation

echo "========================================="
echo "WireGuard Tools Installation (Optional)"
echo "========================================="
echo ""
echo "Note: WireGuard tools are NOT required for deploying VPN servers."
echo "VPNGen can generate keys using Python cryptography library."
echo "This script is only if you want to use native WireGuard tools locally."
echo ""

# Detect OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "Detected macOS"
    echo "Installing WireGuard tools using Homebrew..."
    
    # Check if Homebrew is installed
    if ! command -v brew &> /dev/null; then
        echo "Homebrew not found. Please install Homebrew first:"
        echo "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        exit 1
    fi
    
    # Install wireguard-tools
    brew install wireguard-tools
    
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "Detected Linux"
    
    # Detect distribution
    if [ -f /etc/debian_version ]; then
        echo "Installing WireGuard tools on Debian/Ubuntu..."
        sudo apt-get update
        sudo apt-get install -y wireguard-tools
        
    elif [ -f /etc/redhat-release ]; then
        echo "Installing WireGuard tools on RHEL/CentOS/Fedora..."
        sudo yum install -y epel-release
        sudo yum install -y wireguard-tools
        
    elif [ -f /etc/arch-release ]; then
        echo "Installing WireGuard tools on Arch Linux..."
        sudo pacman -S wireguard-tools
        
    else
        echo "Unsupported Linux distribution"
        echo "Please install wireguard-tools manually using your package manager"
        exit 1
    fi
    
else
    echo "Unsupported operating system: $OSTYPE"
    exit 1
fi

echo ""
echo "Installation complete!"
echo ""

# Test installation
if command -v wg &> /dev/null; then
    echo "WireGuard tools successfully installed:"
    wg version
else
    echo "Warning: WireGuard tools not found in PATH"
fi