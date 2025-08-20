#!/bin/bash
# Terraform wrapper script with IP conflict checking and cost analysis
# Usage: ./terraform_wrapper.sh apply aws eu-west-1 [options]

set -e

COMMAND="$1"
PROVIDER="$2" 
REGION="$3"

# Parse optional flags
FORCE_NEW_IP=false
COST_ANALYSIS=false
COST_BUDGET=""
SKIP_CHECKS=false

shift 3  # Remove first 3 arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --force-new-ip)
            FORCE_NEW_IP=true
            shift
            ;;
        --cost-analysis)
            COST_ANALYSIS=true
            shift
            ;;
        --budget)
            COST_BUDGET="$2"
            COST_ANALYSIS=true
            shift 2
            ;;
        --skip-checks)
            SKIP_CHECKS=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

if [ -z "$COMMAND" ] || [ -z "$PROVIDER" ] || [ -z "$REGION" ]; then
    echo "Usage: $0 <plan|apply|destroy> <provider> <region> [options]"
    echo ""
    echo "Options:"
    echo "  --force-new-ip     Force allocation of new IP address"
    echo "  --cost-analysis    Run detailed cost analysis before deployment"
    echo "  --budget AMOUNT    Run cost analysis with budget constraint (implies --cost-analysis)"
    echo "  --skip-checks      Skip pre-deployment checks (not recommended)"
    echo ""
    echo "Examples:"
    echo "  $0 apply aws eu-west-1"
    echo "  $0 apply aws eu-west-1 --force-new-ip"
    echo "  $0 apply aws eu-west-1 --cost-analysis"
    echo "  $0 apply aws eu-west-1 --budget 50.00"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
TERRAFORM_DIR="$BASE_DIR/terraform/$PROVIDER"

echo "VPNGen Terraform Wrapper"
echo "================================"
echo "Command: $COMMAND"
echo "Provider: $PROVIDER"
echo "Region: $REGION"
echo ""

# Pre-deployment checks for apply command
if [ "$COMMAND" = "apply" ] && [ "$SKIP_CHECKS" = false ]; then
    echo "Running pre-deployment checks..."
    
    # Run cost analysis if requested
    if [ "$COST_ANALYSIS" = true ]; then
        echo "Running cost analysis..."
        
        if [ -n "$COST_BUDGET" ]; then
            python3 "$SCRIPT_DIR/cost_analyzer.py" --provider "$PROVIDER" --region "$REGION" --budget "$COST_BUDGET" --interactive
        else
            python3 "$SCRIPT_DIR/cost_analyzer.py" --provider "$PROVIDER" --region "$REGION" --interactive
        fi
        
        COST_EXIT_CODE=$?
        if [ $COST_EXIT_CODE -eq 1 ]; then
            echo "Cost analysis indicates deployment should not proceed"
            exit 1
        elif [ $COST_EXIT_CODE -eq 2 ]; then
            echo "Cost analysis completed with warnings"
            read -p "Do you want to continue? (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                echo "Deployment cancelled by user"
                exit 1
            fi
        fi
        echo ""
    fi
    
    # Check IP conflicts
    if [ "$FORCE_NEW_IP" = true ]; then
        python3 "$SCRIPT_DIR/pre_deploy_check.py" --provider "$PROVIDER" --region "$REGION" --force-new-ip
    else
        python3 "$SCRIPT_DIR/pre_deploy_check.py" --provider "$PROVIDER" --region "$REGION"
    fi
    
    if [ $? -ne 0 ]; then
        echo "Pre-deployment checks failed"
        exit 1
    fi
    
    echo "Pre-deployment checks passed"
    echo ""
fi

# Navigate to terraform directory
cd "$TERRAFORM_DIR"

# Set terraform variables
export TF_VAR_region="$REGION"
export TF_VAR_project_name="vpngen"

# State file paths
STATE_FILE="$BASE_DIR/state/${PROVIDER}-${REGION}.tfstate"
VARS_FILE="$BASE_DIR/state/${PROVIDER}-${REGION}.tfvars.json"
PLAN_FILE="$BASE_DIR/state/${PROVIDER}-${REGION}.tfplan"

echo "Using state file: $STATE_FILE"
echo "Using vars file: $VARS_FILE"
echo ""

# Execute terraform command
case "$COMMAND" in
    "init")
        echo "Initializing Terraform..."
        terraform init -reconfigure -backend-config="path=$STATE_FILE"
        ;;
    "plan")
        echo "Creating Terraform plan..."
        terraform plan -var-file="$VARS_FILE" -state="$STATE_FILE" -out="$PLAN_FILE"
        ;;
    "apply")
        echo "Applying Terraform configuration..."
        
        # Create plan first
        terraform plan -var-file="$VARS_FILE" -state="$STATE_FILE" -out="$PLAN_FILE"
        
        # Apply the plan
        terraform apply -auto-approve -state="$STATE_FILE" "$PLAN_FILE"
        
        # Post-deployment IP registration
        echo ""
        echo "Registering deployment in IP manager..."
        
        # Extract public IP from terraform output
        PUBLIC_IP=$(terraform output -state="$STATE_FILE" -raw public_ip 2>/dev/null || echo "")
        
        if [ -n "$PUBLIC_IP" ]; then
            echo "Detected public IP: $PUBLIC_IP"
            
            # Create deployment record with IP tracking
            DEPLOYMENT_ID="${PROVIDER}-${REGION}-$(date +%Y%m%d-%H%M%S)"
            
            # Register in deployment tracker (this will automatically register IP)
            python3 -c "
import sys
sys.path.append('$BASE_DIR')
from lib.deployment_tracker import DeploymentTracker
from pathlib import Path

tracker = DeploymentTracker(Path('$BASE_DIR'))
tracker.add_deployment(
    '$DEPLOYMENT_ID',
    '$PROVIDER', 
    '$REGION',
    {'public_ip': '$PUBLIC_IP'}
)
print(f'Registered deployment: $DEPLOYMENT_ID')
"
        else
            echo "Warning: Could not detect public IP from terraform output"
        fi
        ;;
    "destroy")
        echo "Destroying Terraform resources..."
        terraform destroy -auto-approve -var-file="$VARS_FILE" -state="$STATE_FILE"
        
        # Post-destroy cleanup
        echo ""
        echo "Cleaning up IP registrations..."
        python3 -c "
import sys
sys.path.append('$BASE_DIR')
from lib.deployment_tracker import DeploymentTracker
from pathlib import Path

tracker = DeploymentTracker(Path('$BASE_DIR'))
deployments = tracker.get_deployments_by_region('$PROVIDER', '$REGION')
for deployment in deployments:
    if deployment.get('status') == 'active':
        tracker.remove_deployment(deployment['id'])
        print(f'Released IP for deployment: {deployment[\"id\"]}')
"
        ;;
    *)
        echo "Unknown command: $COMMAND"
        echo "Valid commands: init, plan, apply, destroy"
        exit 1
        ;;
esac

echo ""
echo "Terraform $COMMAND completed successfully"

# Show IP usage report after apply/destroy
if [ "$COMMAND" = "apply" ] || [ "$COMMAND" = "destroy" ]; then
    echo ""
    echo "Current IP Usage Report:"
    python3 "$SCRIPT_DIR/pre_deploy_check.py" --provider "$PROVIDER" --region "$REGION" --report-only
fi