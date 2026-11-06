"""List Agent Engine deployments; delete them all with --delete (lab teardown)."""
import sys
import vertexai

PROJECT, LOCATION = "geap-ai-usecases-494501", "us-central1"
client = vertexai.Client(project=PROJECT, location=LOCATION)
engines = list(client.agent_engines.list())
print(f"agent engines found: {len(engines)}")
for e in engines:
    print(" ", e.api_resource.name, e.api_resource.display_name)
    if "--delete" in sys.argv:
        client.agent_engines.delete(name=e.api_resource.name, force=True)
        print("  deleted")
