import os
import uuid
import logging
from neo4j import GraphDatabase, exceptions

logger = logging.getLogger(__name__)

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")

USE_STUB = False
driver = None

# In-memory stub for Hackathon if Neo4j Docker is down
_stub_nodes = []
_stub_edges = []
_review_queue = []

def init_neo4j():
    global driver, USE_STUB
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
        logger.info("Connected to Neo4j.")
        USE_STUB = False
    except Exception as e:
        logger.warning(f"Failed to connect to Neo4j: {e}. Falling back to STUB mode.")
        USE_STUB = True

def get_all_nodes(case_id: str):
    if USE_STUB:
        return [n for n in _stub_nodes if n.get("case_id") == case_id]
        
    query = """
    MATCH (n) WHERE n.case_id = $case_id
    RETURN n.id AS id, n.text AS text, n.type AS type, n.confidence AS confidence
    """
    with driver.session() as session:
        result = session.run(query, case_id=case_id)
        return [{"id": r["id"], "text": r["text"], "type": r["type"], "confidence": r["confidence"]} for r in result]

def create_node(case_id: str, text: str, ent_type: str, confidence: float, evidence_id: str):
    node_id = str(uuid.uuid4())
    if USE_STUB:
        node = {
            "id": node_id, "case_id": case_id, "text": text, 
            "type": ent_type, "confidence": confidence, "evidence_id": evidence_id
        }
        _stub_nodes.append(node)
        return node
        
    query = """
    CREATE (n:Entity {id: $id, case_id: $case_id, text: $text, type: $type, confidence: $confidence, evidence_id: $evidence_id})
    RETURN n.id AS id, n.text AS text, n.type AS type
    """
    with driver.session() as session:
        result = session.run(query, id=node_id, case_id=case_id, text=text, type=ent_type, confidence=confidence, evidence_id=evidence_id)
        return result.single().data()

def add_to_review_queue(case_id: str, review_item: dict):
    # review_item has: extracted, existing_id, existing_name, confidence
    review_item["case_id"] = case_id
    review_item["review_id"] = str(uuid.uuid4())
    
    if USE_STUB:
        _review_queue.append(review_item)
        return
        
    # In a real DB, you'd have a separate table or node type for this
    _review_queue.append(review_item)

def create_edge(case_id: str, from_id: str, to_id: str, edge_type: str, confidence: float, evidence_id: str):
    if USE_STUB:
        edge = {
            "case_id": case_id, "from": from_id, "to": to_id, 
            "type": edge_type, "confidence": confidence, "evidence_id": evidence_id
        }
        _stub_edges.append(edge)
        return edge
        
    query = """
    MATCH (a:Entity {id: $from_id}), (b:Entity {id: $to_id})
    CREATE (a)-[r:RELATION {type: $edge_type, confidence: $confidence, evidence_id: $evidence_id}]->(b)
    RETURN type(r)
    """
    with driver.session() as session:
        session.run(query, from_id=from_id, to_id=to_id, edge_type=edge_type, confidence=confidence, evidence_id=evidence_id)

def get_review_queue(case_id: str):
    return [q for q in _review_queue if q.get("case_id") == case_id]

def get_graph(case_id: str):
    if USE_STUB:
        nodes = [n for n in _stub_nodes if n.get("case_id") == case_id]
        edges = [e for e in _stub_edges if e.get("case_id") == case_id]
        return {"nodes": nodes, "edges": edges}
        
    query = """
    MATCH (n)-[r]->(m)
    WHERE n.case_id = $case_id AND m.case_id = $case_id
    RETURN n, r, m
    """
    nodes = {}
    edges = []
    
    with driver.session() as session:
        result = session.run(query, case_id=case_id)
        for record in result:
            n = record["n"]
            m = record["m"]
            r = record["r"]
            
            if n["id"] not in nodes:
                nodes[n["id"]] = dict(n)
            if m["id"] not in nodes:
                nodes[m["id"]] = dict(m)
                
            edges.append({
                "from": n["id"],
                "to": m["id"],
                "type": r.type,
                "confidence": r.get("confidence", 1.0)
            })
            
    # Also fetch isolated nodes
    iso_query = """
    MATCH (n)
    WHERE n.case_id = $case_id AND NOT (n)--()
    RETURN n
    """
    with driver.session() as session:
        iso_result = session.run(iso_query, case_id=case_id)
        for record in iso_result:
            n = record["n"]
            if n["id"] not in nodes:
                nodes[n["id"]] = dict(n)
                
    return {"nodes": list(nodes.values()), "edges": edges}

def search_entities(query_text: str, case_ids: list):
    """
    Search for entities matching the query text across authorized cases.
    Uses case-insensitive CONTAINS match on entity text.
    
    Returns list of entity dicts with case_id for grouping.
    """
    if USE_STUB:
        results = []
        query_lower = query_text.lower()
        for n in _stub_nodes:
            if n.get("case_id") in case_ids and query_lower in n.get("text", "").lower():
                results.append(n)
        return results
    
    query = """
    MATCH (n)
    WHERE n.case_id IN $case_ids AND toLower(n.text) CONTAINS toLower($query_text)
    RETURN n.id AS id, n.text AS text, n.type AS type, 
           n.confidence AS confidence, n.case_id AS case_id,
           n.evidence_id AS evidence_id
    LIMIT 50
    """
    with driver.session() as session:
        result = session.run(query, case_ids=case_ids, query_text=query_text)
        return [dict(r) for r in result]


def find_cross_case_connections(entity_text: str, case_ids: list):
    """
    Find entities with the same or similar text appearing across multiple 
    authorized cases. Useful for identifying cross-case connections
    (same person, phone number, vehicle, etc.).
    
    Returns list of dicts with entity info and their case_id.
    """
    if USE_STUB:
        results = []
        text_lower = entity_text.lower()
        for n in _stub_nodes:
            if n.get("case_id") in case_ids and text_lower in n.get("text", "").lower():
                results.append(n)
        return results
    
    query = """
    MATCH (n)
    WHERE n.case_id IN $case_ids AND toLower(n.text) CONTAINS toLower($entity_text)
    WITH n.text AS entity_name, n.type AS entity_type, 
         collect(DISTINCT n.case_id) AS cases, count(*) AS occurrences
    WHERE size(cases) > 0
    RETURN entity_name, entity_type, cases, occurrences
    ORDER BY occurrences DESC
    LIMIT 30
    """
    with driver.session() as session:
        result = session.run(query, case_ids=case_ids, entity_text=entity_text)
        return [dict(r) for r in result]


def get_entity_relationships(entity_text: str, case_ids: list):
    """
    Find all relationships connected to entities matching the given text
    within authorized cases.
    
    Returns dict with nodes and edges.
    """
    if USE_STUB:
        matching_ids = set()
        for n in _stub_nodes:
            if n.get("case_id") in case_ids and entity_text.lower() in n.get("text", "").lower():
                matching_ids.add(n.get("id"))
        
        related_nodes = {}
        related_edges = []
        for e in _stub_edges:
            if e.get("case_id") in case_ids:
                if e.get("from") in matching_ids or e.get("to") in matching_ids:
                    related_edges.append(e)
                    # Add connected node IDs
                    for n in _stub_nodes:
                        if n.get("id") in (e.get("from"), e.get("to")):
                            related_nodes[n["id"]] = n
        
        return {"nodes": list(related_nodes.values()), "edges": related_edges}
    
    query = """
    MATCH (n)-[r]-(m)
    WHERE n.case_id IN $case_ids AND m.case_id IN $case_ids
      AND toLower(n.text) CONTAINS toLower($entity_text)
    RETURN n, r, m
    LIMIT 100
    """
    nodes = {}
    edges = []
    
    with driver.session() as session:
        result = session.run(query, case_ids=case_ids, entity_text=entity_text)
        for record in result:
            n = record["n"]
            m = record["m"]
            r = record["r"]
            
            if n["id"] not in nodes:
                nodes[n["id"]] = dict(n)
            if m["id"] not in nodes:
                nodes[m["id"]] = dict(m)
            
            edges.append({
                "from": n["id"],
                "to": m["id"],
                "type": r.type,
                "confidence": r.get("confidence", 1.0),
            })
    
    return {"nodes": list(nodes.values()), "edges": edges}


def get_graph_for_cases(case_ids: list):
    """
    Get combined entity/relationship graph across multiple authorized cases.
    Used by global search to provide graph context.
    """
    if USE_STUB:
        nodes = [n for n in _stub_nodes if n.get("case_id") in case_ids]
        edges = [e for e in _stub_edges if e.get("case_id") in case_ids]
        return {"nodes": nodes, "edges": edges}
    
    query = """
    MATCH (n)-[r]->(m)
    WHERE n.case_id IN $case_ids AND m.case_id IN $case_ids
    RETURN n, r, m
    LIMIT 200
    """
    nodes = {}
    edges = []
    
    with driver.session() as session:
        result = session.run(query, case_ids=case_ids)
        for record in result:
            n = record["n"]
            m = record["m"]
            r = record["r"]
            
            if n["id"] not in nodes:
                nodes[n["id"]] = dict(n)
            if m["id"] not in nodes:
                nodes[m["id"]] = dict(m)
            
            edges.append({
                "from": n["id"],
                "to": m["id"],
                "type": r.type,
                "confidence": r.get("confidence", 1.0),
            })
    
    # Also fetch isolated nodes across these cases
    iso_query = """
    MATCH (n)
    WHERE n.case_id IN $case_ids AND NOT (n)--()
    RETURN n
    LIMIT 100
    """
    with driver.session() as session:
        iso_result = session.run(iso_query, case_ids=case_ids)
        for record in iso_result:
            n = record["n"]
            if n["id"] not in nodes:
                nodes[n["id"]] = dict(n)
    
    return {"nodes": list(nodes.values()), "edges": edges}


# Try init on load
init_neo4j()
