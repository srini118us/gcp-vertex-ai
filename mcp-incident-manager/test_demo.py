"""
Test Demo for MCP Incident Manager
Demonstrates the complete incident management workflow
"""

import json
import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator.incident_manager_agent import incident_manager


def test_servicenow_connection():
    """Test ServiceNow connection and basic operations"""
    print("\n" + "=" * 60)
    print("TEST 1: ServiceNow Connection Test")
    print("=" * 60)
    
    # Test listing incidents
    result = incident_manager.servicenow.list_incidents(limit=5)
    
    if result["success"]:
        print(f"✅ ServiceNow connection successful!")
        print(f"   Found {result['count']} incidents")
        for inc in result["incidents"]:
            print(f"   - {inc.get('number')}: {inc.get('short_description', 'No description')}")
        return True
    else:
        print(f"❌ ServiceNow connection failed: {result.get('error')}")
        return False


def test_sap_docs_search():
    """Test SAP documentation search"""
    print("\n" + "=" * 60)
    print("TEST 2: SAP Documentation Search Test")
    print("=" * 60)
    
    result = incident_manager.sap_docs.search_sap_documentation(
        query="SAP performance troubleshooting",
        page_size=3
    )
    
    if result["success"]:
        print(f"✅ SAP Docs search successful!")
        print(f"   Found {result['count']} results")
        for i, doc in enumerate(result["results"], 1):
            print(f"   {i}. {doc.get('title', 'No title')}")
            if doc.get("content"):
                content = doc["content"][:100] + "..." if len(doc["content"]) > 100 else doc["content"]
                print(f"      {content}")
        return True
    else:
        print(f"❌ SAP Docs search failed: {result.get('error')}")
        return False


def test_teams_notification():
    """Test Teams notification (will show webhook error if not configured)"""
    print("\n" + "=" * 60)
    print("TEST 3: Teams Notification Test")
    print("=" * 60)
    
    result = incident_manager.teams.send_message(
        message="🧪 Test message from MCP Incident Manager",
        title="System Test",
        color="good"
    )
    
    if result["success"]:
        print(f"✅ Teams notification sent successfully!")
        return True
    else:
        print(f"⚠️  Teams notification failed (expected if webhook not configured):")
        print(f"   {result.get('error')}")
        return False


def test_incident_creation():
    """Test incident creation workflow"""
    print("\n" + "=" * 60)
    print("TEST 4: Incident Creation Workflow")
    print("=" * 60)
    
    result = incident_manager.handle_new_incident(
        short_description="Test Incident - MCP Demo",
        description="This is a test incident created by the MCP Incident Manager demo. It demonstrates the complete workflow including ServiceNow creation, Teams notification, and SAP documentation analysis.",
        priority="3",
        category="Testing",
        auto_analyze=True
    )
    
    if result["success"]:
        print(f"✅ Incident workflow successful!")
        incident = result.get("incident", {})
        print(f"   Incident Number: {incident.get('number', 'Unknown')}")
        print(f"   Teams Notified: {result.get('teams_notified', False)}")
        print(f"   Analysis Completed: {result.get('analysis_completed', False)}")
        
        if result.get("recommendations"):
            print(f"   AI Recommendations: {len(result['recommendations'])} found")
            for i, rec in enumerate(result["recommendations"][:2], 1):
                print(f"     {i}. {rec[:100]}...")
        
        return True, incident.get("number")
    else:
        print(f"❌ Incident workflow failed: {result.get('error')}")
        return False, None


def test_incident_resolution(incident_number):
    """Test incident resolution workflow"""
    if not incident_number:
        print("\n⚠️  Skipping resolution test - no incident number available")
        return False
    
    print("\n" + "=" * 60)
    print("TEST 5: Incident Resolution Workflow")
    print("=" * 60)
    
    result = incident_manager.resolve_incident(
        incident_number=incident_number,
        resolution_notes="Test incident resolved successfully by MCP Incident Manager demo. All systems validated and working correctly.",
        resolved_by="MCP Demo"
    )
    
    if result["success"]:
        print(f"✅ Incident resolution successful!")
        print(f"   Incident {incident_number} marked as resolved")
        print(f"   Teams notification sent: {result.get('teams_notification', {}).get('success', False)}")
        return True
    else:
        print(f"❌ Incident resolution failed: {result.get('error')}")
        return False


def main():
    """Run all tests"""
    print("🚀 MCP Incident Manager - Test Demo")
    print("=" * 60)
    print("This demo tests all components of the incident management system")
    print("including ServiceNow, Teams, and SAP documentation integration.")
    
    # Track test results
    test_results = []
    incident_number = None
    
    # Test 1: ServiceNow Connection
    test_results.append(test_servicenow_connection())
    
    # Test 2: SAP Documentation Search
    test_results.append(test_sap_docs_search())
    
    # Test 3: Teams Notification
    test_results.append(test_teams_notification())
    
    # Test 4: Incident Creation
    success, inc_num = test_incident_creation()
    test_results.append(success)
    if inc_num:
        incident_number = inc_num
    
    # Test 5: Incident Resolution
    test_results.append(test_incident_resolution(incident_number))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    test_names = [
        "ServiceNow Connection",
        "SAP Documentation Search", 
        "Teams Notification",
        "Incident Creation",
        "Incident Resolution"
    ]
    
    passed = sum(test_results)
    total = len(test_results)
    
    for i, (name, result) in enumerate(zip(test_names, test_results), 1):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {i}. {name}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests completed successfully!")
    else:
        print("⚠️  Some tests failed. Check the configuration and try again.")
    
    print("\n" + "=" * 60)
    print("Demo completed. Check your ServiceNow instance for created incidents.")
    print("=" * 60)


if __name__ == "__main__":
    main()
