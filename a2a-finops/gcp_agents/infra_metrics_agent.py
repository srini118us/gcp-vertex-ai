"""
Infra Metrics Agent - GCP Side
Analyzes GCP infrastructure metrics and detects anomalies.
"""

import json
from pathlib import Path

# Load mock data
MOCK_DATA_PATH = Path(__file__).parent / "mock_data"

def load_metrics():
    with open(MOCK_DATA_PATH / "gcp_metrics.json", "r") as f:
        return json.load(f)

def load_billing():
    with open(MOCK_DATA_PATH / "gcp_billing.json", "r") as f:
        return json.load(f)


def get_instance_metrics(instance_id: str = None) -> dict:
    """
    Get metrics for a specific instance or all instances.
    
    Args:
        instance_id: Optional VM instance ID. If None, returns all.
    
    Returns:
        Instance metrics with CPU, memory, users, cost.
    """
    data = load_metrics()
    
    if instance_id:
        for instance in data["instances"]:
            if instance["instance_id"] == instance_id:
                return {
                    "instance": instance,
                    "timestamp": data["timestamp"]
                }
        return {"error": f"Instance {instance_id} not found"}
    
    return {
        "instances": data["instances"],
        "timestamp": data["timestamp"]
    }


def detect_anomalies() -> dict:
    """
    Detect infrastructure anomalies.
    
    Returns:
        List of detected anomalies with severity and recommendations.
    """
    data = load_metrics()
    return {
        "anomalies": data["anomalies_detected"],
        "timestamp": data["timestamp"]
    }


def get_high_cpu_zero_users() -> dict:
    """
    Find instances with high CPU but zero active users.
    These are candidates for investigation.
    
    Returns:
        List of suspicious instances requiring business context.
    """
    data = load_metrics()
    suspicious = []
    
    for instance in data["instances"]:
        metrics = instance["metrics"]
        if metrics["cpu_utilization"] > 80 and metrics["active_users"] == 0:
            suspicious.append({
                "instance_id": instance["instance_id"],
                "cpu_percent": metrics["cpu_utilization"],
                "memory_percent": metrics["memory_utilization"],
                "cost_per_day": instance["cost_per_day_usd"],
                "labels": instance["labels"],
                "question_for_sap": "Is this expected business activity?"
            })
    
    return {
        "suspicious_instances": suspicious,
        "count": len(suspicious)
    }


# Agent definition for ADK
AGENT_DESCRIPTION = """
I am the Infra Metrics Agent. I monitor GCP infrastructure including:
- CPU and memory utilization
- Active user counts
- Cost per instance
- Anomaly detection (high CPU with zero users, idle expensive instances)

I identify infrastructure anomalies but need SAP business context to make recommendations.
"""

TOOLS = [
    get_instance_metrics,
    detect_anomalies,
    get_high_cpu_zero_users,
]

if __name__ == "__main__":
    # Test
    print("=== Anomalies ===")
    print(json.dumps(detect_anomalies(), indent=2))
    print("\n=== High CPU Zero Users ===")
    print(json.dumps(get_high_cpu_zero_users(), indent=2))
