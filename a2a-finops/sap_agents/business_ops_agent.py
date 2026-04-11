"""
Business Operations Agent - SAP Side
Provides business process context and batch job information.
"""

import json
from pathlib import Path
from datetime import datetime

MOCK_DATA_PATH = Path(__file__).parent / "mock_data"

def load_business_ops():
    with open(MOCK_DATA_PATH / "sap_business_ops.json", "r") as f:
        return json.load(f)

def load_landscape():
    with open(MOCK_DATA_PATH / "sap_landscape.json", "r") as f:
        return json.load(f)


def get_process_by_vm(vm_instance_id: str) -> dict:
    """
    Get business process running on a specific VM.
    Critical for understanding WHY a VM has high CPU.
    
    Args:
        vm_instance_id: GCP VM instance ID
    
    Returns:
        Business process details explaining VM behavior.
    """
    data = load_business_ops()
    
    processes = []
    for process in data["business_processes"]:
        if process["hosted_on"] == vm_instance_id:
            processes.append(process)
    
    if not processes:
        return {
            "vm_instance_id": vm_instance_id,
            "business_processes": [],
            "message": "No business processes found on this VM"
        }
    
    return {
        "vm_instance_id": vm_instance_id,
        "business_processes": processes,
        "count": len(processes)
    }


def get_active_batch_jobs() -> dict:
    """
    Get currently running batch jobs.
    Explains high CPU with zero users scenario.
    
    Returns:
        List of active batch jobs with expected completion.
    """
    data = load_business_ops()
    return {
        "active_jobs": data["active_batch_jobs"],
        "count": len(data["active_batch_jobs"])
    }


def explain_high_cpu_zero_users(vm_instance_id: str) -> dict:
    """
    Explain why a VM might have high CPU but zero users.
    This is THE KEY function for FinOps A2A collaboration.
    
    Args:
        vm_instance_id: VM showing high CPU, zero users
    
    Returns:
        Business explanation for the anomaly.
    """
    ops_data = load_business_ops()
    
    # Check for active batch jobs on this VM
    active_jobs = []
    for job in ops_data["active_batch_jobs"]:
        # Find which VM this job runs on
        for process in ops_data["business_processes"]:
            if process["process_id"] == job["process_id"] and process["hosted_on"] == vm_instance_id:
                active_jobs.append({
                    "job": job,
                    "process": process
                })
    
    if active_jobs:
        job_info = active_jobs[0]
        return {
            "vm_instance_id": vm_instance_id,
            "explanation": "EXPECTED_BATCH_JOB",
            "is_normal": True,
            "details": {
                "job_name": job_info["job"]["job_id"],
                "process_name": job_info["process"]["name"],
                "status": job_info["job"]["status"],
                "expected_completion": job_info["job"]["expected_completion"],
                "expected_cpu": job_info["process"]["schedule"].get("expected_cpu_percent", "N/A"),
                "expected_users": job_info["process"]["schedule"].get("expected_users", 0),
                "criticality": job_info["process"]["criticality"],
                "business_impact": job_info["process"]["business_impact"]
            },
            "recommendation": "DO NOT reduce resources. Batch job in progress.",
            "contact": job_info["process"].get("contact", job_info["process"]["owner"])
        }
    
    # Check for scheduled processes that might explain it
    for process in ops_data["business_processes"]:
        if process["hosted_on"] == vm_instance_id:
            schedule = process.get("schedule", {})
            if schedule.get("expected_users", 1) == 0 and schedule.get("expected_cpu_percent", 0) > 50:
                return {
                    "vm_instance_id": vm_instance_id,
                    "explanation": "SCHEDULED_BATCH_PROCESS",
                    "is_normal": True,
                    "details": {
                        "process_name": process["name"],
                        "frequency": schedule.get("frequency"),
                        "next_run": schedule.get("next_run"),
                        "criticality": process["criticality"]
                    },
                    "recommendation": "Normal behavior for batch processing system.",
                    "contact": process["owner"]
                }
    
    # No explanation found
    return {
        "vm_instance_id": vm_instance_id,
        "explanation": "UNKNOWN",
        "is_normal": False,
        "details": "No scheduled batch job or process found to explain high CPU",
        "recommendation": "Investigate further - may be anomaly or undocumented process",
        "action": "Contact system owner for verification"
    }


def can_reduce_resources(vm_instance_id: str) -> dict:
    """
    Determine if VM resources can be reduced.
    Final decision point for FinOps optimization.
    
    Args:
        vm_instance_id: VM to evaluate
    
    Returns:
        Decision with business justification.
    """
    ops_data = load_business_ops()
    landscape = load_landscape()
    
    # Get system info
    vm_map = landscape.get("vm_to_system_map", {})
    system_id = vm_map.get(vm_instance_id)
    
    system_info = None
    for sys in landscape["systems"]:
        if sys["system_id"] == system_id:
            system_info = sys
            break
    
    # Get process info
    process_info = None
    for process in ops_data["business_processes"]:
        if process["hosted_on"] == vm_instance_id:
            process_info = process
            break
    
    # Decision logic
    if not system_info:
        return {
            "vm_instance_id": vm_instance_id,
            "can_reduce": True,
            "confidence": "HIGH",
            "reason": "No SAP system on this VM",
            "approval_needed": False
        }
    
    if system_info["criticality"] == "CRITICAL":
        return {
            "vm_instance_id": vm_instance_id,
            "can_reduce": False,
            "confidence": "HIGH",
            "reason": f"CRITICAL system: {system_info['name']}",
            "business_impact": process_info["business_impact"] if process_info else "Unknown",
            "approval_needed": True,
            "approver": system_info["owner"]
        }
    
    if system_info["criticality"] == "LOW":
        # Check if actively used
        if process_info:
            last_used = process_info.get("schedule", {}).get("last_used")
            notes = process_info.get("notes", "")
            
            if "ended" in notes.lower() or "decommission" in notes.lower():
                return {
                    "vm_instance_id": vm_instance_id,
                    "can_reduce": True,
                    "can_shutdown": True,
                    "confidence": "HIGH",
                    "reason": f"LOW criticality, project ended: {notes}",
                    "recommendation": "Safe to shut down. Consider decommissioning.",
                    "approval_needed": False,
                    "savings_action": "SHUTDOWN"
                }
        
        return {
            "vm_instance_id": vm_instance_id,
            "can_reduce": True,
            "confidence": "MEDIUM",
            "reason": f"LOW criticality system: {system_info['name']}",
            "recommendation": "Can reduce during off-hours",
            "approval_needed": False
        }
    
    return {
        "vm_instance_id": vm_instance_id,
        "can_reduce": False,
        "confidence": "MEDIUM",
        "reason": "Requires further analysis",
        "approval_needed": True
    }


AGENT_DESCRIPTION = """
I am the Business Operations Agent. I provide SAP business context:
- Business processes running on VMs
- Active batch job information
- Explanation for high CPU / zero users scenarios
- Resource reduction decisions with business justification

I help FinOps make SAFE cost optimization decisions by providing business context.
"""

TOOLS = [
    get_process_by_vm,
    get_active_batch_jobs,
    explain_high_cpu_zero_users,
    can_reduce_resources,
]

if __name__ == "__main__":
    print("=== Explain High CPU Zero Users ===")
    print(json.dumps(explain_high_cpu_zero_users("vm-payroll-prod-01"), indent=2))
    print("\n=== Can Reduce Resources ===")
    print(json.dumps(can_reduce_resources("vm-dev-unused-03"), indent=2))
