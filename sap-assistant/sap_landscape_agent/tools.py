from typing import Dict, Any
from google.cloud import discoveryengine_v1 as discoveryengine

PROJECT_ID = "genai-2222026"
DATA_STORE_ID = "sap-landscape-docs_1775532657104"
LOCATION = "global"

def search_sap_docs(query: str) -> Dict[str, Any]:
    """Search SAP documentation for relevant information."""
    client = discoveryengine.SearchServiceClient()
    
    serving_config = (
        f"projects/{PROJECT_ID}/locations/{LOCATION}"
        f"/collections/default_collection/dataStores/{DATA_STORE_ID}"
        f"/servingConfigs/default_search"
    )
    
    request = discoveryengine.SearchRequest(
        serving_config=serving_config,
        query=query,
        page_size=5,
        content_search_spec=discoveryengine.SearchRequest.ContentSearchSpec(
            snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
                return_snippet=True,
                max_snippet_count=3,
            ),
            extractive_content_spec=discoveryengine.SearchRequest.ContentSearchSpec.ExtractiveContentSpec(
                max_extractive_answer_count=3,
                max_extractive_segment_count=3,
            ),
        ),
    )
    
    response = client.search(request)
    
    results = []
    for result in response.results:
        doc = result.document
        doc_data = {"title": doc.derived_struct_data.get("title", "Unknown")}
        
        snippets = doc.derived_struct_data.get("snippets", [])
        if snippets:
            doc_data["content"] = snippets[0].get("snippet", "")
        
        answers = doc.derived_struct_data.get("extractive_answers", [])
        if answers:
            doc_data["answer"] = answers[0].get("content", "")
            
        results.append(doc_data)
    
    return {"results": results, "query": query}