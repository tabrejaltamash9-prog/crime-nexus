import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, Globe, ChevronRight, FileText, Bot, AlertCircle, Users, FileStack, Map } from 'lucide-react'
import { globalSearch, getLLMProviders } from '../api'

function renderMarkdown(text) {
  if (!text) return null
  return text.split('\n').map((line, i) => {
    let processed = line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    processed = processed.replace(/`([^`]+)`/g, '<code class="chat-inline-code">$1</code>')
    processed = processed.replace(/\[Doc:\s*(.*?),\s*Case:\s*(.*?)\]/g, '<span class="citation-badge">📄 $1 · Case $2</span>')
    processed = processed.replace(/\[Doc:\s*(.*?)\]/g, '<span class="citation-badge">📄 $1</span>')
    if (!processed.trim()) return <br key={i} />
    if (processed.startsWith('### ')) return <h4 key={i} className="chat-heading" dangerouslySetInnerHTML={{ __html: processed.slice(4) }} />
    if (processed.startsWith('## ')) return <h3 key={i} className="chat-heading" dangerouslySetInnerHTML={{ __html: processed.slice(3) }} />
    if (/^\s*[-•]\s/.test(processed)) return <li key={i} className="chat-list-item" dangerouslySetInnerHTML={{ __html: processed.replace(/^\s*[-•]\s/, '') }} />
    if (/^\s*\d+\.\s/.test(processed)) return <li key={i} className="chat-list-item chat-list-numbered" dangerouslySetInnerHTML={{ __html: processed.replace(/^\s*\d+\.\s/, '') }} />
    return <p key={i} className="chat-paragraph" dangerouslySetInnerHTML={{ __html: processed }} />
  })
}

export default function GlobalSearch() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  
  const [providers, setProviders] = useState([])
  const [selectedProvider, setSelectedProvider] = useState('')
  
  useEffect(() => {
    getLLMProviders().then(data => {
      setProviders(data.providers || [])
      setSelectedProvider(data.default_provider || '')
    }).catch(err => console.error('Failed to load providers:', err))
  }, [])

  const handleSearch = async (e) => {
    e?.preventDefault()
    if (!query.trim() || loading) return
    
    setLoading(true)
    setError(null)
    setResult(null)
    
    try {
      const res = await globalSearch({
        query: query,
        provider: selectedProvider || undefined,
        top_k: 20
      })
      setResult(res)
    } catch (err) {
      console.error('Global search failed:', err)
      setError(err.response?.data?.detail || err.message || 'Search failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', paddingBottom: '40px' }}>
      <div className="page-header" style={{ marginBottom: '24px' }}>
        <div>
          <h1 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Globe size={24} style={{ color: 'var(--primary)' }} />
            Global Search
          </h1>
          <p className="page-subtitle">Cross-case AI investigation and evidence retrieval</p>
        </div>
      </div>

      <div style={{ background: 'white', borderRadius: '16px', padding: '24px', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03)', border: '1px solid var(--border-color)', marginBottom: '24px' }}>
        <form onSubmit={handleSearch} style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
          <div style={{ flex: '1 1 300px', position: 'relative' }}>
            <Search size={18} style={{ position: 'absolute', left: '16px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
            <input 
              type="text" 
              placeholder="Search for names, phone numbers, vehicles, or events across all cases..."
              value={query}
              onChange={e => setQuery(e.target.value)}
              style={{ width: '100%', padding: '12px 16px 12px 44px', borderRadius: '8px', border: '1px solid var(--border-color)', fontSize: '1rem', outline: 'none', transition: 'border-color 0.2s' }}
              className="focus-ring"
            />
          </div>
          <select 
            value={selectedProvider} 
            onChange={e => setSelectedProvider(e.target.value)}
            style={{ padding: '0 16px', borderRadius: '8px', border: '1px solid var(--border-color)', background: 'white', cursor: 'pointer', outline: 'none' }}
          >
            <option value="">Default AI Model</option>
            {providers.filter(p => p.available).map(p => (
              <option key={p.provider} value={p.provider}>
                {p.provider.charAt(0).toUpperCase() + p.provider.slice(1)} ({p.model})
              </option>
            ))}
          </select>
          <button type="submit" className="btn btn-primary" disabled={!query.trim() || loading} style={{ padding: '0 24px' }}>
            {loading ? 'Searching...' : 'Search'}
          </button>
        </form>
      </div>

      {loading && (
        <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-secondary)' }}>
          <div className="typing-indicator" style={{ display: 'inline-flex', marginBottom: '16px' }}>
            <span style={{ width: '8px', height: '8px', margin: '0 4px', background: 'var(--primary)' }}></span>
            <span style={{ width: '8px', height: '8px', margin: '0 4px', background: 'var(--primary)' }}></span>
            <span style={{ width: '8px', height: '8px', margin: '0 4px', background: 'var(--primary)' }}></span>
          </div>
          <p>Analyzing cross-case evidence and generating report...</p>
        </div>
      )}

      {error && (
        <div style={{ padding: '16px', background: 'rgba(254, 226, 226, 0.4)', border: '1px solid rgba(220, 38, 38, 0.2)', borderRadius: '8px', color: '#dc2626', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {result && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: '24px', alignItems: 'start' }}>
          {/* Main Answer Area */}
          <div style={{ background: 'white', borderRadius: '16px', padding: '24px', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05)', border: '1px solid var(--border-color)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', paddingBottom: '16px', borderBottom: '1px solid var(--border-color)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--primary)', fontWeight: '600' }}>
                <Bot size={20} /> AI Analysis
              </div>
              <div style={{ display: 'flex', gap: '8px', fontSize: '0.8rem' }}>
                <span style={{ background: 'rgba(59, 130, 246, 0.1)', color: '#2563eb', padding: '4px 8px', borderRadius: '12px' }}>
                  Model: {result.model_used}
                </span>
                {result.failover_occurred && (
                  <span style={{ background: 'rgba(245, 158, 11, 0.1)', color: '#d97706', padding: '4px 8px', borderRadius: '12px' }}>
                    Failover Active
                  </span>
                )}
              </div>
            </div>
            
            <div className="chat-bubble-text" style={{ fontSize: '1rem', lineHeight: '1.6' }}>
              {renderMarkdown(result.answer)}
            </div>
          </div>

          {/* Right Sidebar - Connections & Sources */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            
            {/* Cross-Case Connections */}
            {result.cross_case_connections && result.cross_case_connections.length > 0 && (
              <div style={{ background: 'white', borderRadius: '12px', padding: '16px', border: '1px solid var(--border-color)' }}>
                <h3 style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Map size={16} /> Cross-Case Links
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {result.cross_case_connections.map((conn, idx) => (
                    <div key={idx} style={{ background: 'var(--bg-color)', padding: '10px', borderRadius: '8px' }}>
                      <div style={{ fontWeight: 600, fontSize: '0.95rem', color: '#1e293b' }}>{conn.entity}</div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>{conn.type}</div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                        {conn.cases.map(cid => (
                          <span key={cid} onClick={() => navigate(`/case/${cid}`)} style={{ fontSize: '0.75rem', background: 'rgba(59, 130, 246, 0.1)', color: '#2563eb', padding: '2px 6px', borderRadius: '4px', cursor: 'pointer' }}>
                            {cid}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Evidence Sources */}
            <div style={{ background: 'white', borderRadius: '12px', padding: '16px', border: '1px solid var(--border-color)' }}>
              <h3 style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <FileStack size={16} /> Referenced Sources
              </h3>
              {result.sources?.length === 0 ? (
                <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>No direct evidence citations used.</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {result.sources?.slice(0, 5).map((src, idx) => (
                    <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: '2px', paddingBottom: '8px', borderBottom: idx < Math.min(result.sources.length, 5) - 1 ? '1px solid var(--border-color)' : 'none' }}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '6px' }}>
                        <FileText size={14} style={{ color: 'var(--text-muted)', marginTop: '2px', flexShrink: 0 }} />
                        <span style={{ fontSize: '0.85rem', fontWeight: 500, color: '#334155', wordBreak: 'break-all' }}>{src.file_name}</span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted)', paddingLeft: '20px' }}>
                        <span>Case: {src.case_id}</span>
                        <span>{(src.score * 100).toFixed(0)}% match</span>
                      </div>
                    </div>
                  ))}
                  {result.sources?.length > 5 && (
                    <div style={{ fontSize: '0.8rem', color: 'var(--primary)', textAlign: 'center', cursor: 'pointer' }}>
                      + {result.sources.length - 5} more sources
                    </div>
                  )}
                </div>
              )}
            </div>
            
          </div>
        </div>
      )}
    </div>
  )
}
