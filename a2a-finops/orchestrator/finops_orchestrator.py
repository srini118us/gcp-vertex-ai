"""
FinOps A2A Orchestrator
Routes queries between GCP and SAP agents using A2A protocol.
"""

import json
import sys
sys.path.insert(0, '.')

from gcp_agents.infra_metrics_agent import detect_anomalies, get_high_cpu_zero_users, get_instance_metrics
from gcp_agents.finops_recommender_agent import get_optimization_plan, get_billing_summary, analyze_instance_cost
from sap_agents.landscape_agent import get_system_by_vm, check_vm_shutdown_safe, get_critical_systems
from sap_agents.business_ops_agent import explain_high_cpu_zero_users, can_reduce_resources, get_active_batch_jobs


def load_agent_cards():
    """Load A2A agent cards for discovery."""
    with open('a2a_protocol/agent_cards/gcp_finops_card.json', 'r') as f:
        gcp_card = json.load(f)
    with open('a2a_protocol/agent_cards/sap_context_card.json', 'r') as f:
        sap_card = json.load(f)
    return {'gcp': gcp_card, 'sap': sap_card}


def finops_investigation(verbose=True):
    """
    Complete FinOps investigation using A2A collaboration.
    
    Flow:
    1. GCP Agent detects anomalies
    2. For each anomaly, query SAP Agent for business context
    3. Combine insights for final recommendation
    """
    
    if verbose:
        print('=' * 60)
        print('  A2A FINOPS INVESTIGATION')
        print('  GCP FinOps Agent <--A2A--> SAP Business Context Agent')
        print('=' * 60)
    
    # Step 1: GCP Agent - Detect anomalies
    if verbose:
        print('\n[STEP 1] GCP Agent: Detecting infrastructure anomalies...')
    
    anomalies = detect_anomalies()
    high_cpu = get_high_cpu_zero_users()
    billing = get_billing_summary()
    
    if verbose:
        print(f'  - Found {len(anomalies["anomalies"])} anomalies')
        print(f'  - High CPU with zero users: {high_cpu["count"]} instances')
        print(f'  - Monthly spend: ${billing["total_spend"]:,.2f} (+{billing["change_percent"]}% MoM)')
    
    # Step 2: For each suspicious instance, query SAP Agent
    if verbose:
        print('\n[STEP 2] A2A Protocol: Querying SAP Agent for business context...')
    
    results = []
    
    for instance in high_cpu['suspicious_instances']:
        vm_id = instance['instance_id']
        
        if verbose:
            print(f'\n  >> Querying SAP about: {vm_id}')
        
        # A2A Call to SAP Agent
        sap_explanation = explain_high_cpu_zero_users(vm_id)
        sap_can_reduce = can_reduce_resources(vm_id)
        sap_system = get_system_by_vm(vm_id)
        
        result = {
            'vm_id': vm_id,
            'gcp_metrics': instance,
            'sap_explanation': sap_explanation,
            'sap_system': sap_system,
            'can_reduce': sap_can_reduce,
            'final_recommendation': None
        }
        
        # Generate final recommendation based on both agents
        if sap_explanation.get('is_normal'):
            result['final_recommendation'] = {
                'action': 'NO_ACTION',
                'reason': sap_explanation.get('recommendation'),
                'contact': sap_explanation.get('contact')
            }
        elif sap_can_reduce.get('can_shutdown'):
            result['final_recommendation'] = {
                'action': 'SHUTDOWN',
                'reason': sap_can_reduce.get('reason'),
                'savings': instance.get('cost_per_day', 0) * 30
            }
        elif sap_can_reduce.get('can_reduce'):
            result['final_recommendation'] = {
                'action': 'RIGHTSIZE',
                'reason': sap_can_reduce.get('reason'),
                'approval_needed': sap_can_reduce.get('approval_needed', False)
            }
        else:
            result['final_recommendation'] = {
                'action': 'INVESTIGATE',
                'reason': 'Could not determine safe action',
                'contact': sap_system.get('owner', 'Unknown')
            }
        
        results.append(result)
        
        if verbose:
            print(f'     SAP System: {sap_system.get("sap_system", {}).get("name", "Unknown")}')
            print(f'     Explanation: {sap_explanation.get("explanation")}')
            print(f'     Recommendation: {result["final_recommendation"]["action"]}')
    
    # Step 3: Check for additional savings opportunities
    if verbose:
        print('\n[STEP 3] GCP Agent: Checking optimization opportunities...')
    
    optimization = get_optimization_plan()
    
    if verbose:
        print(f'  - Safe actions (no SAP approval needed): {len(optimization["safe_actions"])}')
        print(f'  - Needs SAP context: {len(optimization["needs_sap_context"])}')
        print(f'  - Total potential savings: ${optimization["total_potential_savings"]:,.2f}/month')
    
    # Final Summary
    if verbose:
        print('\n' + '=' * 60)
        print('  FINAL A2A INVESTIGATION SUMMARY')
        print('=' * 60)
        
        for r in results:
            print(f'\n  VM: {r["vm_id"]}')
            print(f'  GCP: CPU {r["gcp_metrics"]["cpu_percent"]}%, ${r["gcp_metrics"]["cost_per_day"]}/day')
            print(f'  SAP: {r["sap_explanation"].get("explanation", "Unknown")}')
            print(f'  ACTION: {r["final_recommendation"]["action"]}')
            print(f'  REASON: {r["final_recommendation"]["reason"]}')
    
    return {
        'anomalies': anomalies,
        'investigated_instances': results,
        'optimization_plan': optimization,
        'billing_summary': billing
    }


if __name__ == '__main__':
    results = finops_investigation(verbose=True)