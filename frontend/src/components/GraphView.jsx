import React, { useState, useEffect, useRef } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { getCaseGraph } from '../api'

export default function GraphView({ caseId }) {
  const [graphData, setGraphData] = useState({ nodes: [], links: [] })
  const [loading, setLoading] = useState(true)
  const fgRef = useRef()

  useEffect(() => {
    async function fetchGraph() {
      try {
        const data = await getCaseGraph(caseId)
        // Format for react-force-graph
        const formattedData = {
          nodes: data.nodes.map(n => ({
            id: n.id,
            name: n.text,
            val: 1.5,
            group: n.type
          })),
          links: data.edges.map(e => ({
            source: e.from_id || e.from,
            target: e.to_id || e.to,
            name: e.type
          }))
        }
        setGraphData(formattedData)
      } catch (err) {
        console.error("Failed to load graph", err)
      } finally {
        setLoading(false)
      }
    }
    fetchGraph()
  }, [caseId])

  const getNodeColor = (node) => {
    switch (node.group) {
      case 'PERSON': return '#ff7b72'
      case 'PHONE': return '#79c0ff'
      case 'LOCATION': return '#d2a8ff'
      case 'FINANCIAL': return '#a5d6ff'
      case 'ORGANIZATION': return '#ffa657'
      default: return '#c9d1d9'
    }
  }

  if (loading) {
    return <div className="empty-state"><p>Loading graph...</p></div>
  }

  if (graphData.nodes.length === 0) {
    return (
      <div className="empty-state">
        <h3>Graph is empty</h3>
        <p>Upload and process evidence to discover entities and relationships.</p>
      </div>
    )
  }

  return (
    <div style={{ width: '100%', height: '600px', background: 'rgba(0,0,0,0.2)', borderRadius: '8px', overflow: 'hidden', border: '1px solid rgba(255,255,255,0.05)' }}>
      <ForceGraph2D
        ref={fgRef}
        graphData={graphData}
        nodeLabel="name"
        nodeColor={getNodeColor}
        linkDirectionalArrowLength={3.5}
        linkDirectionalArrowRelPos={1}
        linkCurvature={0.25}
        width={800} // A fixed width for now, will CSS it
        height={600}
        onEngineStop={() => fgRef.current.zoomToFit(400)}
      />
    </div>
  )
}
