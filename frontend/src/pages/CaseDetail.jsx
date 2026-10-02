import React, { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Upload, FileText, Image, Music, File,
  Download, ShieldCheck, ShieldAlert, Trash2, Users, Clock, Flag, RotateCw
} from 'lucide-react'
import { getCase, listEvidence, verifyEvidence, deleteEvidence, getEvidenceDownloadUrl, reindexEvidence, reprocessEvidence } from '../api'
import { useAuth } from '../AuthContext'
import UploadEvidenceModal from '../components/UploadEvidenceModal'
import PersonPhotoUploadModal from '../components/PersonPhotoUploadModal'
import GraphView from '../components/GraphView'
import InvestigationChat from '../components/InvestigationChat'

function formatBytes(bytes) {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

function getFileIcon(mimeType) {
  if (mimeType?.startsWith('image/')) return <Image size={16} />
  if (mimeType?.startsWith('audio/')) return <Music size={16} />
  if (mimeType?.includes('pdf') || mimeType?.startsWith('text/')) return <FileText size={16} />
  return <File size={16} />
}

export default function CaseDetail() {
  const { user } = useAuth()
  const { caseId } = useParams()
  const navigate = useNavigate()
  const [caseData, setCaseData] = useState(null)
  const [evidence, setEvidence] = useState([])
  const [loading, setLoading] = useState(true)
  const [showUploadModal, setShowUploadModal] = useState(null)
  const [verifying, setVerifying] = useState({})
  const [verifyResults, setVerifyResults] = useState({})
  const [tab, setTab] = useState('evidence')
  const [chatMessages, setChatMessages] = useState([])
  const [reprocessing, setReprocessing] = useState({})

  const fetchData = async () => {
    try {
      const [c, e] = await Promise.all([getCase(caseId), listEvidence(caseId)])
      setCaseData(c)
      setEvidence(e.evidence || [])
    } catch (err) {
      console.error('Failed to load case:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    setChatMessages([])
  }, [caseId])

  useEffect(() => {
    // If any evidence is still processing, poll every 3 seconds
    const hasPending = evidence.some(e => e.status === 'uploaded' || e.status === 'processing' || e.ocrStatus === 'processing' || e.ocrStatus === 'pending')
    if (hasPending) {
      const timer = setInterval(() => {
        fetchData()
      }, 3000)
      return () => clearInterval(timer)
    }
  }, [evidence, caseId])

  const handleVerify = async (evidenceId) => {
    setVerifying(prev => ({ ...prev, [evidenceId]: true }))
    try {
      const result = await verifyEvidence(evidenceId)
      setVerifyResults(prev => ({ ...prev, [evidenceId]: result }))
    } catch (err) {
      setVerifyResults(prev => ({ ...prev, [evidenceId]: { integrityValid: false, error: true } }))
    } finally {
      setVerifying(prev => ({ ...prev, [evidenceId]: false }))
    }
  }

  const handleReprocess = async (evidenceId) => {
    setReprocessing(prev => ({ ...prev, [evidenceId]: true }))
    try {
      await reprocessEvidence(evidenceId)
      await fetchData()
    } catch (err) {
      console.error('Failed to trigger reprocess:', err)
    } finally {
      setReprocessing(prev => ({ ...prev, [evidenceId]: false }))
    }
  }

  const handleDelete = async (evidenceId) => {
    if (!confirm('Delete this evidence item? This cannot be undone.')) return
    try {
      await deleteEvidence(evidenceId)
      await fetchData()
    } catch (err) {
      console.error('Failed to delete:', err)
    }
  }

  if (loading) {
    return (
      <div className="empty-state">
        <p>Loading case...</p>
      </div>
    )
  }

  if (!caseData) {
    return (
      <div className="empty-state">
        <h3>Case not found</h3>
        <button className="btn btn-secondary" style={{ marginTop: 16 }} onClick={() => navigate('/')}>
          <ArrowLeft size={16} /> Back to Dashboard
        </button>
      </div>
    )
  }

  return (
    <>
      <a className="back-nav" onClick={() => navigate('/')}>
        <ArrowLeft size={16} /> Back to Dashboard
      </a>

      <div className="case-detail-header">
        <div className="header-info">
          <h1>{caseData.title}</h1>
          {caseData.description && <p style={{ marginTop: 4, fontSize: '0.9rem' }}>{caseData.description}</p>}
          <div className="case-detail-meta">
            <div className="meta-item">
              <Flag size={14} />
              <span className={`badge badge-${caseData.priority}`}>{caseData.priority}</span>
            </div>
            <div className="meta-item">
              <span className={`badge badge-${caseData.status}`}>{caseData.status}</span>
            </div>
            <div className="meta-item">
              <Users size={14} />
              {caseData.investigators.length > 0 ? caseData.investigators.join(', ') : 'No investigators'}
            </div>
            <div className="meta-item">
              <Clock size={14} />
              {new Date(caseData.createdAt).toLocaleString()}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn btn-primary" onClick={() => setShowUploadModal('document')}>
            <Upload size={16} /> Upload Case Document
          </button>
          <button className="btn btn-secondary" onClick={() => setShowUploadModal('person')}>
            <Upload size={16} /> Upload Person Photo
          </button>
        </div>
      </div>

      <div className="tabs">
        <button className={`tab ${tab === 'evidence' ? 'active' : ''}`} onClick={() => setTab('evidence')}>
          Evidence ({evidence.length})
        </button>
        <button className={`tab ${tab === 'audit' ? 'active' : ''}`} onClick={() => setTab('audit')}>
          Audit Log
        </button>
        <button className={`tab ${tab === 'graph' ? 'active' : ''}`} onClick={() => setTab('graph')}>
          Entity Graph
        </button>
        <button className={`tab ${tab === 'investigate' ? 'active' : ''}`} onClick={() => setTab('investigate')}>
          AI Investigate
        </button>
      </div>

      {tab === 'evidence' && (
        <>
          {evidence.length === 0 ? (
            <div className="empty-state">
              <FileText className="empty-state-icon" />
              <h3>No evidence uploaded</h3>
              <p>Upload documents, images, or audio files to begin analysis.</p>
              <div style={{ marginTop: 16, display: 'flex', gap: '8px', justifyContent: 'center' }}>
                <button className="btn btn-primary" onClick={() => setShowUploadModal('document')}>
                  <Upload size={16} /> Upload Case Document
                </button>
                <button className="btn btn-secondary" onClick={() => setShowUploadModal('person')}>
                  <Upload size={16} /> Upload Person Photo
                </button>
              </div>
            </div>
          ) : (
            <div className="evidence-grid">
              {evidence.map((ev, idx) => {
                const vr = verifyResults[ev.evidenceId]
                return (
                  <div key={ev.evidenceId} className="evidence-card" style={{ animationDelay: `${idx * 0.05}s` }}>
                    <div className="evidence-card-header">
                      <div className="file-icon">{getFileIcon(ev.mimeType)}</div>
                      <span className={`badge badge-${ev.status}`}>{ev.status}</span>
                    </div>
                    <div className="file-name" title={ev.originalFilename}>{ev.originalFilename}</div>
                    <div className="evidence-meta">
                      <div className="evidence-meta-item">
                        <span className="label">Size</span>
                        <span className="value">{formatBytes(ev.size)}</span>
                      </div>
                      <div className="evidence-meta-item">
                        <span className="label">Type</span>
                        <span className="value">{ev.mimeType}</span>
                      </div>
                      <div className="evidence-meta-item">
                        <span className="label">Uploader</span>
                        <span className="value">{ev.uploader}</span>
                      </div>
                      <div className="evidence-meta-item">
                        <span className="label">Uploaded</span>
                        <span className="value">{new Date(ev.uploadedAt).toLocaleDateString()}</span>
                      </div>
                    </div>
                    <div className="hash-value">
                      SHA-256: {ev.sha256Hash}
                    </div>

                    {/* OCR Extraction Status & Content Preview */}
                    {ev.ocrStatus === 'processing' && (
                      <div style={{
                        marginTop: 10,
                        padding: '8px 10px',
                        background: 'rgba(59, 130, 246, 0.06)',
                        border: '1px solid rgba(59, 130, 246, 0.15)',
                        borderRadius: 8,
                        fontSize: '0.8rem',
                        color: '#2563eb',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6
                      }}>
                        <RotateCw size={14} className="spin" style={{ animation: 'spin 1s linear infinite' }} />
                        <span>Extracting text with Surya OCR (in progress)...</span>
                      </div>
                    )}

                    {ev.ocrStatus === 'failed' && (
                      <div style={{
                        marginTop: 10,
                        padding: '8px 10px',
                        background: 'rgba(254, 226, 226, 0.5)',
                        border: '1px solid rgba(220, 38, 38, 0.15)',
                        borderRadius: 8,
                        fontSize: '0.8rem',
                        color: '#dc2626'
                      }}>
                        ❌ OCR extraction failed. Try clicking <strong>Reprocess OCR</strong> below.
                      </div>
                    )}

                    {ev.ocrStatus === 'completed' && !ev.extractedText && (
                      <div style={{
                        marginTop: 10,
                        padding: '8px 10px',
                        background: 'rgba(241, 245, 249, 0.6)',
                        border: '1px solid rgba(148, 185, 230, 0.18)',
                        borderRadius: 8,
                        fontSize: '0.8rem',
                        color: '#64748b'
                      }}>
                        ℹ️ No text detected in this document.
                      </div>
                    )}

                    {ev.extractedText && (
                      <div className="extracted-text-preview" style={{
                        marginTop: 10,
                        padding: 10,
                        background: 'rgba(241, 245, 249, 0.6)',
                        borderRadius: 8,
                        fontSize: '0.82rem',
                        maxHeight: 180,
                        overflowY: 'auto',
                        whiteSpace: 'pre-wrap',
                        border: '1px solid rgba(148, 185, 230, 0.18)',
                        fontFamily: 'monospace',
                        lineHeight: 1.4,
                        color: '#334155'
                      }}>
                        {(() => {
                          try {
                            const parsed = JSON.parse(ev.extractedText);
                            if (parsed.blocks && Array.isArray(parsed.blocks)) {
                              const confPercent = parsed.overall_confidence 
                                ? Math.round(parsed.overall_confidence * 100) 
                                : null;
                              return (
                                <>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, color: '#2563eb', fontWeight: 600, fontFamily: 'sans-serif' }}>
                                    <span>Extracted Text (Surya OCR):</span>
                                    {confPercent !== null && (
                                      <span style={{ fontSize: '0.75rem', color: confPercent >= 70 ? '#059669' : '#d97706' }}>
                                        {confPercent}% confidence
                                      </span>
                                    )}
                                  </div>
                                  <div>
                                    {parsed.blocks.map((b, i) => (
                                      <div key={i} style={{ marginBottom: 2 }}>{b.text}</div>
                                    ))}
                                  </div>
                                </>
                              );
                            }
                            return (
                              <>
                                <div style={{ marginBottom: 4, color: '#38bdf8', fontWeight: 600, fontFamily: 'sans-serif' }}>
                                  Extracted Content:
                                </div>
                                <div>{ev.extractedText}</div>
                              </>
                            );
                          } catch (e) {
                            return (
                              <>
                                <div style={{ marginBottom: 4, color: '#2563eb', fontWeight: 600, fontFamily: 'sans-serif' }}>
                                  Extracted Content:
                                </div>
                                <div>{ev.extractedText}</div>
                              </>
                            );
                          }
                        })()}
                      </div>
                    )}

                    {vr && (
                      <div style={{ marginBottom: 10, marginTop: 10, display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        <span className={`badge ${vr.integrityValid ? 'badge-valid' : 'badge-invalid'}`}>
                          {vr.integrityValid ? (
                            <><ShieldCheck size={12} /> File Integrity: Valid</>
                          ) : (
                            <><ShieldAlert size={12} /> File Integrity: FAILED</>
                          )}
                        </span>
                      </div>
                    )}

                    <div className="evidence-actions">
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleVerify(ev.evidenceId)}
                        disabled={verifying[ev.evidenceId]}
                      >
                        <ShieldCheck size={14} />
                        {verifying[ev.evidenceId] ? 'Verifying...' : 'Verify'}
                      </button>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleReprocess(ev.evidenceId)}
                        disabled={reprocessing[ev.evidenceId] || ev.ocrStatus === 'processing'}
                        title="Re-run Surya OCR and re-index evidence"
                      >
                        <RotateCw size={14} style={{ animation: (reprocessing[ev.evidenceId] || ev.ocrStatus === 'processing') ? 'spin 1s linear infinite' : 'none' }} />
                        {(reprocessing[ev.evidenceId] || ev.ocrStatus === 'processing') ? 'Processing...' : 'Reprocess OCR'}
                      </button>
                      <a
                        className="btn btn-secondary btn-sm"
                        href={getEvidenceDownloadUrl(ev.evidenceId)}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        <Download size={14} /> Download
                      </a>
                      <button
                        className="btn btn-danger btn-sm"
                        onClick={() => handleDelete(ev.evidenceId)}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}

      {tab === 'audit' && <AuditLog caseId={caseId} />}

      {tab === 'graph' && <GraphView caseId={caseId} />}

      {tab === 'investigate' && (
        <InvestigationChat 
          caseId={caseId} 
          messages={chatMessages}
          setMessages={setChatMessages}
        />
      )}

      {showUploadModal === 'document' && (
        <UploadEvidenceModal
          caseId={caseId}
          currentUser={user}
          onClose={() => setShowUploadModal(null)}
          onUploaded={fetchData}
        />
      )}
      {showUploadModal === 'person' && (
        <PersonPhotoUploadModal
          caseId={caseId}
          onClose={() => setShowUploadModal(null)}
          onUploaded={fetchData}
        />
      )}
    </>
  )
}
