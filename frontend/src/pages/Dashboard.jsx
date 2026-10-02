import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, FolderOpen, FileText, ShieldCheck, AlertTriangle, Globe, Search, ArrowRight } from 'lucide-react'
import { listCases, createCase } from '../api'
import CreateCaseModal from '../components/CreateCaseModal'

export default function Dashboard() {
  const [cases, setCases] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const navigate = useNavigate()

  const fetchCases = async () => {
    try {
      const data = await listCases()
      setCases(data.cases || [])
    } catch (err) {
      console.error('Failed to load cases:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchCases() }, [])

  const handleCreateCase = async (payload) => {
    await createCase(payload)
    await fetchCases()
  }

  const totalEvidence = cases.reduce((sum, c) => sum + (c.evidenceCount || 0), 0)
  const activeCases = cases.filter(c => c.status === 'open' || c.status === 'active').length
  const highPriority = cases.filter(c => c.priority === 'high' || c.priority === 'critical').length

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Investigation Dashboard</h1>
          <p className="page-subtitle">Crime Nexus — Case & Evidence Management</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreateModal(true)}>
          <Plus size={16} />
          New Case
        </button>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">
            <FolderOpen size={14} /> Total Cases
          </div>
          <div className="stat-value">{cases.length}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">
            <ShieldCheck size={14} /> Active Cases
          </div>
          <div className="stat-value">{activeCases}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">
            <FileText size={14} /> Evidence Items
          </div>
          <div className="stat-value">{totalEvidence}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">
            <AlertTriangle size={14} /> High Priority
          </div>
          <div className="stat-value">{highPriority}</div>
        </div>
      </div>

      <div style={{ background: 'linear-gradient(to right, rgba(59, 130, 246, 0.05), rgba(99, 102, 241, 0.05))', border: '1px solid rgba(59, 130, 246, 0.2)', borderRadius: '16px', padding: '24px', marginBottom: '32px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '1.25rem', color: '#1e293b', marginBottom: '8px' }}>
            <Globe size={22} style={{ color: 'var(--primary)' }} />
            Global AI Investigator
          </h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', maxWidth: '600px' }}>
            Search across all authorized case files, evidence, and entity networks. Discover cross-case connections, track suspects globally, and generate comprehensive intelligence reports.
          </p>
        </div>
        <button 
          className="btn btn-primary" 
          style={{ padding: '12px 24px', display: 'flex', alignItems: 'center', gap: '8px', boxShadow: '0 4px 6px -1px rgba(59, 130, 246, 0.2)' }}
          onClick={() => navigate('/global-search')}
        >
          <Search size={16} />
          Start Global Search
          <ArrowRight size={16} style={{ marginLeft: '4px' }} />
        </button>
      </div>

      <div className="section-header">
        <h2>All Cases</h2>
      </div>

      {loading ? (
        <div className="empty-state">
          <p>Loading cases...</p>
        </div>
      ) : cases.length === 0 ? (
        <div className="empty-state">
          <FolderOpen className="empty-state-icon" />
          <h3>No cases yet</h3>
          <p>Create your first investigation case to get started.</p>
          <button className="btn btn-primary" style={{ marginTop: 16 }} onClick={() => setShowCreateModal(true)}>
            <Plus size={16} /> Create Case
          </button>
        </div>
      ) : (
        <div className="cases-table-wrap">
          <table className="cases-table">
            <thead>
              <tr>
                <th>Case</th>
                <th>Status</th>
                <th>Priority</th>
                <th>Investigators</th>
                <th>Evidence</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.caseId} onClick={() => navigate(`/case/${c.caseId}`)}>
                  <td>
                    <div className="case-title-cell">
                      <span className="title">{c.title}</span>
                      {c.description && <span className="description">{c.description}</span>}
                    </div>
                  </td>
                  <td><span className={`badge badge-${c.status}`}>{c.status}</span></td>
                  <td><span className={`badge badge-${c.priority}`}>{c.priority}</span></td>
                  <td style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                    {c.investigators.length > 0 ? c.investigators.join(', ') : '—'}
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem' }}>{c.evidenceCount}</td>
                  <td style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                    {new Date(c.createdAt).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreateModal && (
        <CreateCaseModal
          onClose={() => setShowCreateModal(false)}
          onSubmit={handleCreateCase}
        />
      )}
    </>
  )
}
