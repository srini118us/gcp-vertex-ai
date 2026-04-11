import sys
sys.path.insert(0, '.')
from sap_agents.business_ops_agent import can_reduce_resources

result = can_reduce_resources('vm-dev-unused-03')
print('VM: vm-dev-unused-03')
print(f'Can Shutdown: {result.get("can_shutdown", False)}')
print(f'Reason: {result.get("reason")}')
print(f'Savings: $510/month')