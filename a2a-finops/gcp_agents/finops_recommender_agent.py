"""
FinOps Recommender Agent - GCP Side
Analyzes billing data and provides cost optimization recommendations.
"""

import json
from pathlib import Path

MOCK_DATA_PATH = Path(__file__).parent / "mock_data"

def load_billing():
    with open(MOCK_DATA_PATH / "gcp_billing.json", "r") as f:
        return json.load(f)

def load_metrics():
    with open(MOCK_DATA_PATH / "gcp_metrics.json", "r") as f:
        return json.load(f)


def get_billing_summary() -> dict:
    """
    Get current billing summary with month-over-month comparison.
    
    Returns:
        Billing summary with spend breakdown and trends.
    """
    data = load_billing()
    return {
        "period": data["billing_period"],
        "total_spend": data["total_spend_usd"],
        "previous_month": data["previous_month_usd"],
        "change_percent": data["change_percent"],
        "breakdown": data["breakdown_by_project"]
    }


def get_cost_recommendations() -> dict:
    """
    Get cost optimization recommendations.
    
    Returns:
        List of recommendations with potential savings.
    """
    data = load_billing()
    return {
        "recommendations": data["recommendations"],
        "total_potential_savings": sum(r["potential_savings_monthly"] for r in data["recommendations"])
    }


def analyze_instance_cost(instance_id: str) -> dict:
    """
    Analyze cost and utilization for a specific instance.
    
    Args:
        instance_id: VM instance ID to analyze
    
    Returns:
        Cost analysis with optimization potential.
    """
    metrics = load_metrics()
    billing = load_billing()
    
    # Find instance in metrics
    instance_data = None
    for inst in metrics["instances"]:
        if inst["instance_id"] == instance_id:
            instance_data = inst
            break
    
    if not instance_data:
        return {"error": f"Instance {instance_id} not found"}
    
    # Find recommendation if exists
    recommendation = None
    for rec in billing["recommendations"]:
        if rec.get("instance_id") == instance_id:
            recommendation = rec
            break
    
    # Calculate efficiency score
    cpu = instance_data["metrics"]["cpu_utilization"]
    users = instance_data["metrics"]["active_users"]
    cost = instance_data["cost_per_day_usd"]
    
    if users > 0:
        cost_per_user = cost / users
        efficiency = "GOOD" if cost_per_user < 1.0 else "REVIEW"
    else:
        cost_per_user = None
        efficiency = "NEEDS_BUSINESS_CONTEXT"
    
    return {
        "instance_id": instance_id,
        "daily_cost": cost,
        "monthly_cost_estimate": cost * 30,
        "cpu_utilization": cpu,
        "active_users": users,
        "cost_per_user": cost_per_user,
        "efficiency": efficiency,
        "recommendation": recommendation,
        "action_required": "Query SAP for business context" if efficiency == "NEEDS_BUSINESS_CONTEXT" else None
    }


def get_optimization_plan() -> dict:
    """
    Generate comprehensive optimization plan.
    Identifies what needs SAP business context before action.
    
    Returns:
        Optimization plan with safe vs requires-context actions.
    """
    billing = load_billing()
    metrics = load_metrics()
    
    safe_actions = []  # Can act without SAP context
    needs_context = []  # Must verify with SAP first
    
    for rec in billing["recommendations"]:
        if rec["confidence"] == "HIGH":
            safe_actions.append({
                "action": rec["type"],
                "instance": rec["instance_id"],
                "savings": rec["potential_savings_monthly"],
                "risk": "LOW"
            })
        else:
            needs_context.append({
                "action": rec["type"],
                "instance": rec["instance_id"],
                "savings": rec["potential_savings_monthly"],
                "reason": rec.get("note", "Requires business validation"),
                "query_for_sap": f"What business process runs on {rec['instance_id']}?"
            })
    
    return {
        "safe_actions": safe_actions,
        "needs_sap_context": needs_context,
        "total_safe_savings": sum(a["savings"] for a in safe_actions),
        "total_potential_savings": sum(a["savings"] for a in safe_actions) + sum(n["savings"] for n in needs_context)
    }


AGENT_DESCRIPTION = """
I am the FinOps Recommender Agent. I analyze GCP costs and provide optimization recommendations:
- Billing summaries and trends
- Cost per instance analysis
- Rightsizing recommendations
- Idle resource identification

For production workloads, I flag recommendations that need SAP business context before action.
"""

TOOLS = [
    get_billing_summary,
    get_cost_recommendations,
    analyze_instance_cost,
    get_optimization_plan,
]

if __name__ == "__main__":
    print("=== Billing Summary ===")
    print(json.dumps(get_billing_summary(), indent=2))
    print("\n=== Optimization Plan ===")
    print(json.dumps(get_optimization_plan(), indent=2))
