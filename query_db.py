import sqlite3

def run():
    conn = sqlite3.connect('backend/data/crime_nexus.db')
    cursor = conn.cursor()
    cursor.execute("SELECT evidence_id, status, ocr_status, qdrant_status, neo4j_status, index_error FROM evidence WHERE status = 'failed'")
    print(cursor.fetchall())
    
run()
