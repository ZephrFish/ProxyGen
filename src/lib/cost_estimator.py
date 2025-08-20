#!/usr/bin/env python3
"""
Cost Estimator and Optimisation for ProxyGen
Provides cost estimation and optimisation recommendations across cloud providers
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional


class CostEstimator:
    """Estimate and optimise cloud infrastructure costs"""

    def __init__(self):
        # Load real-time pricing if available
        self._load_pricing_updates()
        
        # Pricing data (as of 2024, prices in USD per hour)
        self.pricing = {
            "aws": {
                "instances": {
                    "t3.micro": 0.0104,
                    "t3.small": 0.0208,
                    "t3.medium": 0.0416,
                    "t3.large": 0.0832,
                    "t3.xlarge": 0.1664,
                    "t4g.micro": 0.0084,  # ARM-based, cheaper
                    "t4g.small": 0.0168,
                    "t4g.medium": 0.0336,
                },
                "bandwidth": {
                    "first_10tb": 0.09,  # per GB
                    "next_40tb": 0.085,
                    "next_100tb": 0.07,
                    "over_150tb": 0.05,
                },
                "storage": {"gp3": 0.08, "gp2": 0.10},  # per GB per month
                "ip": 0.005,  # per hour for elastic IP
                "regions": {
                    "us-east-1": 1.0,  # baseline
                    "us-west-2": 1.0,
                    "eu-west-1": 1.1,
                    "eu-central-1": 1.15,
                    "ap-southeast-1": 1.2,
                    "ap-northeast-1": 1.25,
                    "sa-east-1": 1.4,
                },
            },
            "azure": {
                "instances": {
                    "Standard_B1s": 0.0104,
                    "Standard_B1ms": 0.0207,
                    "Standard_B2s": 0.0416,
                    "Standard_B2ms": 0.0832,
                    "Standard_B4ms": 0.1664,
                    "Standard_D2s_v5": 0.096,
                    "Standard_D4s_v5": 0.192,
                },
                "bandwidth": {
                    "first_5gb": 0.0,  # free
                    "next_10tb": 0.087,
                    "next_40tb": 0.083,
                    "next_100tb": 0.07,
                    "over_150tb": 0.05,
                },
                "storage": {
                    "standard_ssd": 0.12,  # per GB per month
                    "premium_ssd": 0.20,
                },
                "ip": 0.004,  # per hour for public IP
                "regions": {
                    "eastus": 1.0,
                    "westus2": 1.0,
                    "westeurope": 1.1,
                    "northeurope": 1.08,
                    "southeastasia": 1.15,
                    "japaneast": 1.25,
                    "brazilsouth": 1.35,
                },
            },
            "digitalocean": {
                "instances": {
                    "s-1vcpu-1gb": 0.00833,  # $6/month
                    "s-1vcpu-2gb": 0.01667,  # $12/month
                    "s-2vcpu-2gb": 0.02500,  # $18/month
                    "s-2vcpu-4gb": 0.03333,  # $24/month
                    "s-4vcpu-8gb": 0.06667,  # $48/month
                    "c-2": 0.04167,  # $30/month CPU-optimized
                    "c-4": 0.08333,  # $60/month CPU-optimized
                },
                "bandwidth": {
                    "first_1000gb": 0.0,  # 1TB free
                    "over_1000gb": 0.01,  # $0.01 per GB
                },
                "storage": {"standard": 0.10},  # $0.10 per GB per month
                "ip": 0.0,  # Floating IPs are free
                "regions": {
                    "nyc1": 1.0,
                    "nyc3": 1.0,
                    "sfo1": 1.0,
                    "sfo2": 1.0,
                    "sfo3": 1.0,
                    "ams2": 1.0,
                    "ams3": 1.0,
                    "sgp1": 1.0,
                    "lon1": 1.0,
                    "fra1": 1.0,
                    "tor1": 1.0,
                    "blr1": 1.0,
                    "syd1": 1.0,
                },
            },
            "hetzner": {
                "instances": {
                    "cx11": 0.00500,  # ~€3.29/month
                    "cx21": 0.00889,  # ~€5.83/month
                    "cx31": 0.01611,  # ~€10.59/month
                    "cx41": 0.03056,  # ~€20.09/month
                    "cx51": 0.05958,  # ~€39.19/month
                    "cpx11": 0.00639,  # ~€4.20/month shared vCPU
                    "cpx21": 0.01139,  # ~€7.49/month shared vCPU
                    "cpx31": 0.02083,  # ~€13.70/month shared vCPU
                },
                "bandwidth": {
                    "first_20tb": 0.0,  # 20TB free
                    "over_20tb": 0.001,  # €1 per TB
                },
                "storage": {"standard": 0.05},  # Included in instance price
                "ip": 0.0,  # Floating IPs included
                "regions": {
                    "fsn1": 1.0,  # Falkenstein, Germany
                    "nbg1": 1.0,  # Nuremberg, Germany
                    "hel1": 1.0,  # Helsinki, Finland
                    "ash": 1.1,   # Ashburn, USA (slightly more expensive)
                    "hil": 1.1,   # Hillsboro, USA
                },
            },
        }

        # Optimisation thresholds
        self.optimisation_thresholds = {
            "cpu_utilisation_low": 20,  # %
            "cpu_utilisation_high": 80,  # %
            "bandwidth_high": 1000,  # GB per month
            "cost_savings_minimum": 10,  # % minimum savings to recommend
        }

    def estimate_monthly_cost(
        self,
        provider: str,
        instance_type: str,
        region: str,
        bandwidth_gb: float = 100,
        storage_gb: float = 20,
        hours_per_month: float = 730,
    ) -> Dict:
        """Estimate monthly cost for a Proxy server"""

        if provider not in self.pricing:
            raise ValueError(f"Unknown provider: {provider}")

        provider_pricing = self.pricing[provider]

        # Get base instance cost
        if instance_type not in provider_pricing["instances"]:
            raise ValueError(f"Unknown instance type: {instance_type}")

        instance_hourly = provider_pricing["instances"][instance_type]

        # Apply regional pricing modifier
        region_modifier = provider_pricing["regions"].get(region, 1.0)
        instance_hourly *= region_modifier

        # Calculate costs
        instance_cost = instance_hourly * hours_per_month

        # IP address cost
        ip_cost = provider_pricing["ip"] * hours_per_month

        # Bandwidth cost (tiered pricing)
        bandwidth_cost = self.calculate_bandwidth_cost(provider, bandwidth_gb)

        # Storage cost
        storage_type = list(provider_pricing["storage"].keys())[0]
        storage_cost = provider_pricing["storage"][storage_type] * storage_gb

        # Total cost
        total_cost = instance_cost + ip_cost + bandwidth_cost + storage_cost

        return {
            "provider": provider,
            "region": region,
            "instance_type": instance_type,
            "breakdown": {
                "instance": round(instance_cost, 2),
                "ip_address": round(ip_cost, 2),
                "bandwidth": round(bandwidth_cost, 2),
                "storage": round(storage_cost, 2),
            },
            "total_monthly": round(total_cost, 2),
            "total_yearly": round(total_cost * 12, 2),
            "currency": "USD",
            "estimated_at": datetime.now().isoformat(),
        }

    def calculate_bandwidth_cost(self, provider: str, bandwidth_gb: float) -> float:
        """Calculate bandwidth cost with tiered pricing"""
        bandwidth_pricing = self.pricing[provider]["bandwidth"]
        cost = 0.0

        if provider == "aws":
            if bandwidth_gb <= 10240:  # First 10TB
                cost = bandwidth_gb * bandwidth_pricing["first_10tb"]
            elif bandwidth_gb <= 51200:  # Next 40TB
                cost = 10240 * bandwidth_pricing["first_10tb"]
                cost += (bandwidth_gb - 10240) * bandwidth_pricing["next_40tb"]
            elif bandwidth_gb <= 153600:  # Next 100TB
                cost = 10240 * bandwidth_pricing["first_10tb"]
                cost += 40960 * bandwidth_pricing["next_40tb"]
                cost += (bandwidth_gb - 51200) * bandwidth_pricing["next_100tb"]
            else:  # Over 150TB
                cost = 10240 * bandwidth_pricing["first_10tb"]
                cost += 40960 * bandwidth_pricing["next_40tb"]
                cost += 102400 * bandwidth_pricing["next_100tb"]
                cost += (bandwidth_gb - 153600) * bandwidth_pricing["over_150tb"]

        elif provider == "azure":
            if bandwidth_gb <= 5:  # First 5GB free
                cost = 0
            elif bandwidth_gb <= 10245:  # Next 10TB
                cost = (bandwidth_gb - 5) * bandwidth_pricing["next_10tb"]
            elif bandwidth_gb <= 51205:  # Next 40TB
                cost = 10240 * bandwidth_pricing["next_10tb"]
                cost += (bandwidth_gb - 10245) * bandwidth_pricing["next_40tb"]
            # Similar tiered calculation

        elif provider == "digitalocean":
            if bandwidth_gb <= 1000:  # First 1TB free
                cost = 0
            else:
                cost = (bandwidth_gb - 1000) * bandwidth_pricing["over_1000gb"]
        
        elif provider == "hetzner":
            if bandwidth_gb <= 20480:  # First 20TB free
                cost = 0
            else:
                # Convert to TB and charge per TB over 20TB
                cost = ((bandwidth_gb - 20480) / 1024) * 1000 * bandwidth_pricing["over_20tb"]

        return cost

    def compare_providers(
        self, regions: Dict[str, str], bandwidth_gb: float = 100, storage_gb: float = 20
    ) -> List[Dict]:
        """Compare costs across different providers and regions"""
        comparisons = []

        for provider in ["aws", "azure", "digitalocean", "hetzner"]:
            # Get default instance type for provider
            if provider == "aws":
                instance_type = "t3.micro"
                region = regions.get("aws", "us-east-1")
            elif provider == "azure":
                instance_type = "Standard_B1s"
                region = regions.get("azure", "eastus")
            elif provider == "digitalocean":
                instance_type = "s-1vcpu-1gb"
                region = regions.get("digitalocean", "nyc1")
            else:  # hetzner
                instance_type = "cx11"
                region = regions.get("hetzner", "fsn1")

            try:
                estimate = self.estimate_monthly_cost(
                    provider, instance_type, region, bandwidth_gb, storage_gb
                )
                comparisons.append(estimate)
            except Exception as e:
                print(f"Error estimating {provider}: {e}")

        # Sort by total cost
        comparisons.sort(key=lambda x: x["total_monthly"])

        return comparisons

    def get_optimisation_recommendations(
        self, current_config: Dict, usage_metrics: Dict
    ) -> List[Dict]:
        """Get cost optimisation recommendations based on usage"""
        recommendations = []

        provider = current_config["provider"]
        current_instance = current_config["instance_type"]

        # Check CPU utilisation
        cpu_util = usage_metrics.get("avg_cpu_utilisation", 50)

        if cpu_util < self.optimisation_thresholds["cpu_utilisation_low"]:
            # Recommend smaller instance
            smaller_instances = self.get_smaller_instances(provider, current_instance)

            if smaller_instances:
                new_instance = smaller_instances[0]
                current_cost = self.pricing[provider]["instances"][current_instance]
                new_cost = self.pricing[provider]["instances"][new_instance]
                savings = (current_cost - new_cost) * 730  # Monthly

                recommendations.append(
                    {
                        "type": "downsize_instance",
                        "reason": f"Low CPU utilisation ({cpu_util}%)",
                        "current": current_instance,
                        "recommended": new_instance,
                        "monthly_savings": round(savings, 2),
                        "priority": "high" if savings > 20 else "medium",
                    }
                )

        elif cpu_util > self.optimisation_thresholds["cpu_utilisation_high"]:
            # Recommend larger instance
            larger_instances = self.get_larger_instances(provider, current_instance)

            if larger_instances:
                recommendations.append(
                    {
                        "type": "upsize_instance",
                        "reason": f"High CPU utilisation ({cpu_util}%)",
                        "current": current_instance,
                        "recommended": larger_instances[0],
                        "priority": "high",
                    }
                )

        # Check for ARM-based instances (usually cheaper)
        if provider == "aws" and not current_instance.startswith("t4g"):
            arm_equivalent = self.get_arm_equivalent(current_instance)
            if arm_equivalent:
                current_cost = self.pricing[provider]["instances"][current_instance]
                arm_cost = self.pricing[provider]["instances"][arm_equivalent]
                savings = (current_cost - arm_cost) * 730

                if savings > 0:
                    recommendations.append(
                        {
                            "type": "switch_to_arm",
                            "reason": "ARM instances are more cost-effective",
                            "current": current_instance,
                            "recommended": arm_equivalent,
                            "monthly_savings": round(savings, 2),
                            "priority": "medium",
                        }
                    )

        # Check for reserved instances
        recommendations.append(
            {
                "type": "reserved_instances",
                "reason": "Long-term usage can benefit from reserved instances",
                "potential_savings": "Up to 72% with 3-year commitment",
                "priority": "low",
            }
        )

        # Check bandwidth usage
        bandwidth_gb = usage_metrics.get("monthly_bandwidth_gb", 0)
        if bandwidth_gb > self.optimisation_thresholds["bandwidth_high"]:
            recommendations.append(
                {
                    "type": "bandwidth_optimisation",
                    "reason": f"High bandwidth usage ({bandwidth_gb} GB/month)",
                    "suggestions": [
                        "Enable compression",
                        "Implement caching",
                        "Consider CDN for static content",
                        "Use split tunneling to reduce Proxy traffic",
                    ],
                    "priority": "medium",
                }
            )

        # Check for idle resources
        if usage_metrics.get("active_connections", 0) == 0:
            recommendations.append(
                {
                    "type": "remove_idle",
                    "reason": "No active connections detected",
                    "suggestion": "Consider removing or stopping this server",
                    "monthly_savings": self.estimate_monthly_cost(
                        provider, current_instance, current_config["region"]
                    )["total_monthly"],
                    "priority": "high",
                }
            )

        return recommendations

    def get_smaller_instances(self, provider: str, current: str) -> List[str]:
        """Get list of smaller instance types"""
        instances = list(self.pricing[provider]["instances"].keys())
        current_price = self.pricing[provider]["instances"][current]

        smaller = [
            i
            for i in instances
            if self.pricing[provider]["instances"][i] < current_price
        ]

        # Sort by price descending (largest of the smaller instances first)
        smaller.sort(key=lambda x: self.pricing[provider]["instances"][x], reverse=True)

        return smaller

    def get_larger_instances(self, provider: str, current: str) -> List[str]:
        """Get list of larger instance types"""
        instances = list(self.pricing[provider]["instances"].keys())
        current_price = self.pricing[provider]["instances"][current]

        larger = [
            i
            for i in instances
            if self.pricing[provider]["instances"][i] > current_price
        ]

        # Sort by price ascending (smallest of the larger instances first)
        larger.sort(key=lambda x: self.pricing[provider]["instances"][x])

        return larger

    def get_arm_equivalent(self, instance_type: str) -> Optional[str]:
        """Get ARM equivalent of x86 instance"""
        arm_map = {
            "t3.micro": "t4g.micro",
            "t3.small": "t4g.small",
            "t3.medium": "t4g.medium",
        }

        return arm_map.get(instance_type)

    def generate_cost_report(
        self, deployments: List[Dict], period_days: int = 30
    ) -> Dict:
        """Generate comprehensive cost report"""
        report = {
            "period_days": period_days,
            "generated_at": datetime.now().isoformat(),
            "deployments": [],
            "total_cost": 0,
            "cost_by_provider": {},
            "cost_by_region": {},
            "recommendations": [],
        }

        for deployment in deployments:
            estimate = self.estimate_monthly_cost(
                deployment["provider"],
                deployment["instance_type"],
                deployment["region"],
                deployment.get("bandwidth_gb", 100),
                deployment.get("storage_gb", 20),
            )

            report["deployments"].append(estimate)
            report["total_cost"] += estimate["total_monthly"]

            # Aggregate by provider
            provider = deployment["provider"]
            if provider not in report["cost_by_provider"]:
                report["cost_by_provider"][provider] = 0
            report["cost_by_provider"][provider] += estimate["total_monthly"]

            # Aggregate by region
            region = deployment["region"]
            if region not in report["cost_by_region"]:
                report["cost_by_region"][region] = 0
            report["cost_by_region"][region] += estimate["total_monthly"]

        # Round totals
        report["total_cost"] = round(report["total_cost"], 2)
        report["cost_by_provider"] = {
            k: round(v, 2) for k, v in report["cost_by_provider"].items()
        }
        report["cost_by_region"] = {
            k: round(v, 2) for k, v in report["cost_by_region"].items()
        }

        # Add savings opportunities
        if report["total_cost"] > 100:
            report["recommendations"].append(
                {
                    "type": "reserved_instances",
                    "potential_savings": f"${round(report['total_cost'] * 0.3, 2)}/month",
                    "description": "Consider reserved instances for 30% savings",
                }
            )

        if len(deployments) > 5:
            report["recommendations"].append(
                {
                    "type": "consolidation",
                    "description": "Consider consolidating servers in same region",
                }
            )

        return report

    def _load_pricing_updates(self):
        """Load real-time pricing updates if available"""
        # Placeholder for future real-time pricing API integration
        pass

    def pre_deployment_cost_analysis(
        self, 
        provider: str, 
        region: str, 
        instance_type: str = None,
        expected_clients: int = 1,
        bandwidth_gb_per_month: float = 100,
        storage_gb: float = 20,
        duration_months: int = 12
    ) -> Dict:
        """Comprehensive pre-deployment cost analysis"""
        
        # Auto-detect instance type if not provided
        if not instance_type:
            if provider == "aws":
                instance_type = "t3.micro"
            elif provider == "azure":
                instance_type = "Standard_B1s"
            elif provider == "digitalocean":
                instance_type = "s-1vcpu-1gb"
            elif provider == "hetzner":
                instance_type = "cx11"
        
        # Calculate base deployment cost
        base_cost = self.estimate_monthly_cost(
            provider, instance_type, region, bandwidth_gb_per_month, storage_gb
        )
        
        # Calculate scaling scenarios
        scenarios = {
            "current": base_cost,
            "light_usage": self.estimate_monthly_cost(
                provider, instance_type, region, bandwidth_gb_per_month * 0.5, storage_gb
            ),
            "heavy_usage": self.estimate_monthly_cost(
                provider, instance_type, region, bandwidth_gb_per_month * 3, storage_gb * 2
            )
        }
        
        # Calculate multi-client scaling
        client_scaling = {}
        for clients in [5, 10, 25, 50]:
            scaled_bandwidth = bandwidth_gb_per_month * (clients / expected_clients)
            scaled_storage = storage_gb + (clients * 0.1)  # Small per-client overhead
            
            client_scaling[f"{clients}_clients"] = self.estimate_monthly_cost(
                provider, instance_type, region, scaled_bandwidth, scaled_storage
            )
        
        # Provider comparison
        comparison = self.compare_providers(
            {provider: region}, bandwidth_gb_per_month, storage_gb
        )
        
        # Cost projections
        projections = {
            "monthly": base_cost["total_monthly"],
            "quarterly": base_cost["total_monthly"] * 3,
            "yearly": base_cost["total_monthly"] * 12,
            "custom_duration": base_cost["total_monthly"] * duration_months
        }
        
        # Budget warnings and recommendations
        warnings = []
        recommendations = []
        
        # Check for high costs
        if base_cost["total_monthly"] > 50:
            warnings.append({
                "type": "high_cost",
                "message": f"Monthly cost (${base_cost['total_monthly']:.2f}) exceeds $50 threshold",
                "severity": "warning"
            })
            recommendations.append({
                "type": "cost_optimization",
                "action": "Consider smaller instance type or different region",
                "potential_savings": "20-40%"
            })
        
        # Check bandwidth efficiency
        bandwidth_cost = base_cost["breakdown"]["bandwidth"]
        if bandwidth_cost > base_cost["total_monthly"] * 0.3:
            warnings.append({
                "type": "bandwidth_heavy",
                "message": f"Bandwidth costs (${bandwidth_cost:.2f}) are {bandwidth_cost/base_cost['total_monthly']*100:.1f}% of total",
                "severity": "info"
            })
            recommendations.append({
                "type": "bandwidth_optimization",
                "action": "Consider CDN or traffic optimization",
                "potential_savings": "15-25%"
            })
        
        # Instance optimization recommendations - simplified for pre-deployment
        if provider == "aws" and instance_type == "t3.micro":
            recommendations.append({
                "type": "instance_optimization",
                "action": "Consider t4g.micro (ARM-based) for 20% cost savings",
                "potential_savings": "20%"
            })
        
        # Regional cost comparison
        comparison_dict = {item["provider"]: item for item in comparison}
        if len(comparison_dict) > 1:
            cheapest = min(comparison, key=lambda x: x["total_monthly"])
            current = next((item for item in comparison if item["provider"] == provider), base_cost)
            if cheapest["total_monthly"] < current["total_monthly"]:
                savings = current["total_monthly"] - cheapest["total_monthly"]
                recommendations.append({
                    "type": "region_optimization",
                    "action": f"Consider deploying in a cheaper region ({cheapest['provider']})",
                    "potential_savings": f"${savings:.2f}/month ({savings/current['total_monthly']*100:.1f}%)"
                })
        
        return {
            "deployment_config": {
                "provider": provider,
                "region": region,
                "instance_type": instance_type,
                "expected_clients": expected_clients,
                "bandwidth_gb_per_month": bandwidth_gb_per_month,
                "storage_gb": storage_gb
            },
            "base_cost": base_cost,
            "scenarios": scenarios,
            "client_scaling": client_scaling,
            "provider_comparison": comparison,
            "projections": projections,
            "warnings": warnings,
            "recommendations": recommendations,
            "summary": {
                "total_monthly": base_cost["total_monthly"],
                "total_yearly": projections["yearly"],
                "cost_per_client_monthly": base_cost["total_monthly"] / expected_clients,
                "break_even_clients": max(1, int(50 / (base_cost["total_monthly"] / expected_clients))),
                "risk_level": "high" if base_cost["total_monthly"] > 100 else "medium" if base_cost["total_monthly"] > 30 else "low"
            },
            "generated_at": datetime.now().isoformat()
        }

    def cost_comparison_matrix(self, regions_config: Dict[str, str], scenarios: Dict[str, Dict]) -> Dict:
        """Generate cost comparison matrix across providers and scenarios"""
        
        matrix = {}
        
        for scenario_name, scenario_config in scenarios.items():
            matrix[scenario_name] = {}
            
            for provider, region in regions_config.items():
                try:
                    cost = self.estimate_monthly_cost(
                        provider=provider,
                        instance_type=scenario_config.get("instance_type", "t3.micro"),
                        region=region,
                        bandwidth_gb=scenario_config.get("bandwidth_gb", 100),
                        storage_gb=scenario_config.get("storage_gb", 20)
                    )
                    matrix[scenario_name][provider] = {
                        "region": region,
                        "monthly_cost": cost["total_monthly"],
                        "breakdown": cost["breakdown"]
                    }
                except Exception:
                    matrix[scenario_name][provider] = {
                        "region": region,
                        "monthly_cost": None,
                        "error": "Pricing not available"
                    }
        
        return matrix

    def budget_analysis(self, monthly_budget: float, requirements: Dict) -> Dict:
        """Analyze what can be deployed within a given budget"""
        
        provider = requirements.get("provider", "aws")
        region = requirements.get("region", "us-east-1")
        clients = requirements.get("clients", 5)
        bandwidth_per_client = requirements.get("bandwidth_per_client_gb", 20)
        
        # Find optimal configuration within budget
        configurations = []
        
        # Test different instance types
        instance_types = list(self.pricing[provider]["instances"].keys())
        
        for instance_type in instance_types:
            total_bandwidth = clients * bandwidth_per_client
            
            try:
                cost = self.estimate_monthly_cost(
                    provider, instance_type, region, total_bandwidth, 20
                )
                
                if cost["total_monthly"] <= monthly_budget:
                    configurations.append({
                        "instance_type": instance_type,
                        "monthly_cost": cost["total_monthly"],
                        "budget_utilization": cost["total_monthly"] / monthly_budget,
                        "max_clients": int(clients * (monthly_budget / cost["total_monthly"])),
                        "cost_breakdown": cost["breakdown"]
                    })
            except Exception:
                continue
        
        # Sort by budget utilization (best value)
        configurations.sort(key=lambda x: x["budget_utilization"], reverse=True)
        
        return {
            "monthly_budget": monthly_budget,
            "requirements": requirements,
            "feasible_configurations": configurations,
            "recommended": configurations[0] if configurations else None,
            "budget_sufficient": len(configurations) > 0,
            "minimum_budget_needed": min(
                [c["monthly_cost"] for c in configurations], default=None
            ) if not configurations else None
        }
