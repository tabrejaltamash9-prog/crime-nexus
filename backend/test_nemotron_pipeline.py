import asyncio
import os
import sys
from dotenv import load_dotenv

# Load env before importing services
load_dotenv("../.env")

# Set the provider to nemotron explicitly for testing
os.environ["LLM_PROVIDER"] = "nemotron"

from services.rag_service import query_evidence
from services import vector_store
from services import neo4j_service

# --- Mocking the Databases ---

async def mock_search_similar(*args, **kwargs):
    return [
        {
            "document_id": "doc-001",
            "file_name": "police_report.pdf",
            "file_url": "/files/police_report.pdf",
            "chunk_text": "The primary suspect, John Doe (S-01), was seen driving a white Swift near the scene of the incident. A witness, Jane Smith, confirmed seeing him exit the white Swift at 22:00 hours.",
            "chunk_index": 1,
            "score": 0.95,
            "evidence_type": "Police Report"
        },
        {
            "document_id": "doc-002",
            "file_name": "phone_records.pdf",
            "file_url": "/files/phone_records.pdf",
            "chunk_text": "Call logs for S-01 show multiple calls to a burner phone (V-03) on the night of the incident.",
            "chunk_index": 3,
            "score": 0.88,
            "evidence_type": "Call Log"
        }
    ]

def mock_get_graph(*args, **kwargs):
    return {
        "nodes": [
            {"id": "n1", "text": "John Doe (S-01)", "type": "Person"},
            {"id": "n2", "text": "White Swift (VH-01)", "type": "Vehicle"},
            {"id": "n3", "text": "Jane Smith (S-03)", "type": "Person"},
            {"id": "n4", "text": "Burner Phone (V-03)", "type": "Phone"},
        ],
        "edges": [
            {"from": "n1", "to": "n2", "type": "DRIVES"},
            {"from": "n1", "to": "n3", "type": "KNOWS"},
            {"from": "n1", "to": "n4", "type": "CALLED"},
        ]
    }

# Apply mocks
vector_store.search_similar = mock_search_similar
neo4j_service.get_graph = mock_get_graph

# --- End Mocks ---

async def main():
    case_id = "test-case-id"
    
    test_questions = [
        "Who is the primary suspect?",
        "What evidence connects the primary suspect to the white Swift?",
        "What is the relationship between S-01 and S-03?",
        "Where was vehicle VH-01 seen after the first incident?",
        "Which phone contacts are connected to S-01?",
        "What evidence supports the relationship between S-01 and V-03?",
    ]
    
    print(f"Testing Nemotron Pipeline with Mocked DBs")
    print(f"Using Provider: {os.environ.get('LLM_PROVIDER')}")
    print("====================================================\n")
    
    for i, query in enumerate(test_questions, 1):
        print(f"--- Question {i}: {query} ---")
        try:
            result = await query_evidence(query, case_id)
            
            print(f"Answer:\n{result['answer']}\n")
            
            print("Sources Returned:")
            for src in result["sources"]:
                print(f"  - [{src['score']}] {src['file_name']} (Chunk {src['chunk_index']})")
                
        except Exception as e:
            print(f"Error querying Nemotron: {e}")
        
        print("\n" + "="*50 + "\n")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
