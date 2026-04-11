"""
Landscape Agent - SAP Side
Provides SAP system landscape information from Cloud ALM.
"""

import json
from pathlib import Path

MOCK_DATA_PATH = Path(__file__).parent / "mock_data"

def load_landscape():
    with open(MOCK_DATA_PATH / "sap_landscape.json", "r") as f:
        return json.load(f)


def get_system_info(system_id: str = None) -> dict:
    """
    Get SAP system information.
    
    Args:
        system_id: Optional system ID. If None, returns all systems.
    
    Returns:
        System details including criticality, owner, dependencies.
    """
    data = load_landscape()
    
    if system_id:
        for system in data["systems"]:
            if system["system_id"] == system_id:
                return {"system": system}
        return {"error": f"System {system_id} not found"}
    
    return {
        "landscape": data["landscape"],
        "systems": data["systems"],
        "last_updated": data["last_updated"]
    }


def get_system_by_vm(vm_instance_id: str) -> dict:
    """
    Find which SAP system runs on a specific VM.
    This is the KEY function for A2A - maps GCP infra to SAP business.
    
    Args:
        vm_instance_id: GCP VM instance ID
    
    Returns:
        SAP system details for that VM.
    """
    data = load_landscape()
    
    # Look up VM to system mapping
    vm_map = data.get("vm_to_system_map", {})
    system_id = vm_map.get(vm_instance_id)
    
    if not system_id:
        return {
            "vm_instance_id": vm_instance_id,
            "sap_system": None,
            "message": "No SAP system found on this VM"
        }
    
    # Get full system details
    for system in data["systems"]:
        if system["system_id"] == system_id:
            return {
                "vm_instance_id": vm_instance_id,
                "sap_system": system,
                "criticality": system["criticality"],
                "can_shutdown": system["criticality"] == "LOW",
                "owner": system["owner"]
            }
    
    return {"error": "System mapping found but details missing"}


def get_critical_systems() -> dict:
    """
    Get all critical SAP systems that should never be auto-scaled.
    
    Returns:
        List of critical systems with their VMs.
    """
    data = load_landscape()
    critical = []
    
    for system in data["systems"]:
        if system["criticality"] in ["CRITICAL", "HIGH"]:
            critical.append({
                "system_id": system["system_id"],
                "name": system["name"],
                "criticality": system["criticality"],
                "hosted_on": system["hosted_on"],
                "sla": system["sla"],
                "owner": system["owner"]
            })
    
    return {
        "critical_systems": critical,
        "count": len(critical),
        "warning": "These VMs require manual approval before any changes"
    }


def check_vm_shutdown_safe(vm_instance_id: str) -> dict:
    """
    Check if a VM can be safely shut down.
    
    Args:
        vm_instance_id: GCP VM instance ID
    
    Returns:
        Safety assessment with business impact.
    """
    system_info = get_system_by_vm(vm_instance_id)
    
    if not system_info.get("sap_system"):
        return {
            "vm_instance_id": vm_instance_id,
            "safe_to_shutdown": True,
            "reason": "No SAP system on this VM",
            "approval_required": False
        }
    
    system = system_info["sap_system"]
    criticality = system["criticality"]
    
    if criticality == "CRITICAL":
        return {
            "vm_instance_id": vm_instance_id,
            "safe_to_shutdown": False,
            "reason": f"Hosts CRITICAL system: {system['name']}",
            "business_impact": "SEVERE - Production system",
            "sla": system["sla"],
            "approval_required": True,
            "approver": system["owner"]
        }
    elif criticality == "HIGH":
        return {
            "vm_instance_id": vm_instance_id,
            "safe_to_shutdown": False,
            "reason": f"Hosts HIGH criticality system: {system['name']}",
            "business_impact": "SIGNIFICANT",
            "approval_required": True,
            "approver": system["owner"]
        }
    else:
        return {
            "vm_instance_id": vm_instance_id,
            "safe_to_shutdown": True,
            "reason": f"Hosts LOW criticality system: {system['name']}",
            "business_impact": "MINIMAL",
            "approval_required": False,
            "recommendation": "Safe to shutdown during off-hours"
        }


AGENT_DESCRIPTION = """
I am the Landscape Agent connected to SAP Cloud ALM. I provide:
- SAP system inventory and dependencies
- VM to SAP system mapping
- System criticality and SLA information
- Shutdown safety assessments

I help GCP FinOps understand which VMs host critical SAP systems.
"""

TOOLS = [
    get_system_info,
    get_system_by_vm,
    get_critical_systems,
    check_vm_shutdown_safe,
]

if __name__ == "__main__":
    print("=== System by VM ===")
    print(json.dumps(get_system_by_vm("vm-payroll-prod-01"), indent=2))
    print("\n=== Shutdown Check ===")
    print(json.dumps(check_vm_shutdown_safe("vm-dev-unused-03"), indent=2))
