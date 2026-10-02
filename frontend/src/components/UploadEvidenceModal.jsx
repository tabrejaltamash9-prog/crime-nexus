import React, { useState, useCallback, useRef } from 'react'
import { X, Upload, FileText } from 'lucide-react'
import { uploadEvidence } from '../api'
import { useAuth } from '../AuthContext'
import { computeFileHash } from '../utils/cryptoUtils'

function formatBytes(bytes) {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

export default function UploadEvidenceModal({ caseId, onClose, onUploaded, currentUser: propUser }) {
  const { user: authUser } = useAuth()
  const currentUser = propUser || authUser
  const [files, setFiles] = useState([])
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState({})
  const [results, setResults] = useState([])
  const [dragActive, setDragActive] = useState(false)
  const inputRef = useRef(null)

  const [sourceType, setSourceType] = useState('unknown')

  const handleFiles = useCallback((fileList) => {
    const newFiles = Array.from(fileList)
    setFiles(prev => [...prev, ...newFiles])
  }, [])

  const handleDrag = (e) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') setDragActive(true)
    else if (e.type === 'dragleave') setDragActive(false)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    if (e.dataTransfer.files?.length) handleFiles(e.dataTransfer.files)
  }

  const removeFile = (idx) => {
    setFiles(prev => prev.filter((_, i) => i !== idx))
  }

  const handleUpload = async () => {
    if (files.length === 0) return
    setUploading(true)
    const uploadResults = []
    
    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      try {
        setProgress(prev => ({ ...prev, [i]: 10 })) // 10%
        
        // 1. Hash the original file
        const originalSha256 = await computeFileHash(file)
        
        setProgress(prev => ({ ...prev, [i]: 50 })) // 50%

        // 2. Upload the file
        const result = await uploadEvidence(
          caseId, 
          file, 
          originalSha256, 
          "NONE", 
          "", 
          [], 
          'system', 
          (e) => {
            const pct = 50 + Math.round((e.loaded * 40) / e.total) // Scale 50-90%
            setProgress(prev => ({ ...prev, [i]: pct }))
          },
          sourceType
        )

        setProgress(prev => ({ ...prev, [i]: 100 }))

        uploadResults.push({ file: file.name, success: true, data: result })
      } catch (err) {
        let errorMsg = err.message || 'Upload failed'
        if (err.response?.data?.detail) {
          const d = err.response.data.detail
          if (typeof d === 'string') {
            errorMsg = d
          } else if (Array.isArray(d)) {
            errorMsg = d.map(item => item.msg || JSON.stringify(item)).join(', ')
          } else {
            errorMsg = JSON.stringify(d)
          }
        }
        uploadResults.push({ file: file.name, success: false, error: errorMsg })
      }
    }
    setResults(uploadResults)
    setUploading(false)
    if (uploadResults.some(r => r.success)) {
      onUploaded()
    }
  }

  const allDone = results.length > 0

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ width: 540 }}>
        <div className="modal-header">
          <h2>Upload Evidence</h2>
          <button className="modal-close" onClick={onClose}><X size={18} /></button>
        </div>
        <div className="modal-body">
          {!allDone && (
            <>
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', marginBottom: 4, fontSize: '0.9rem', fontWeight: 500 }}>Document Type (Optional)</label>
                <select 
                  className="input" 
                  value={sourceType} 
                  onChange={(e) => setSourceType(e.target.value)}
                  style={{ width: '100%' }}
                >
                  <option value="unknown">Unknown / Auto-detect</option>
                  <option value="typed">Typed Document</option>
                  <option value="handwritten">Handwritten Document</option>
                </select>
              </div>

              <div
                className={`dropzone ${dragActive ? 'active' : ''}`}
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                onClick={() => inputRef.current?.click()}
              >
                <Upload className="dropzone-icon" />
                <p className="dropzone-text">
                  <strong>Click to browse</strong> or drag files here
                </p>
                <p className="dropzone-hint">Documents, images, audio — up to 50 MB each</p>
                <input
                  ref={inputRef}
                  type="file"
                  multiple
                  style={{ display: 'none' }}
                  onChange={(e) => handleFiles(e.target.files)}
                />
              </div>

              {files.map((file, idx) => (
                <div key={idx} className="upload-progress">
                  <div className="upload-file-info">
                    <span className="upload-filename">
                      <FileText size={14} style={{ marginRight: 6, verticalAlign: 'middle' }} />
                      {file.name}
                    </span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span className="upload-size">{formatBytes(file.size)}</span>
                      {!uploading && (
                        <button className="modal-close" onClick={() => removeFile(idx)} style={{ padding: 2 }}>
                          <X size={14} />
                        </button>
                      )}
                    </div>
                  </div>
                  {uploading && (
                    <div className="progress-bar-track">
                      <div className="progress-bar-fill" style={{ width: `${progress[idx] || 0}%` }} />
                    </div>
                  )}
                </div>
              ))}

            </>
          )}

          {allDone && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {results.map((r, i) => (
                <div key={i} className="upload-progress">
                  <div className="upload-file-info">
                    <span className="upload-filename">{r.file}</span>
                    <span className={`badge ${r.success ? 'badge-valid' : 'badge-invalid'}`}>
                      {r.success ? '✓ Uploaded' : '✗ Failed'}
                    </span>
                  </div>
                    <div style={{ marginBottom: 0, marginTop: 4, display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '0.8rem', color: '#9ca3af' }}>
                      <div className="hash-value" style={{ margin: 0, padding: 0, background: 'none', border: 'none' }}>
                        ✓ SHA-256 Calculated: {r.data?.originalSha256 || r.data?.sha256Hash || 'Done'}
                      </div>
                    </div>
                  {!r.success && (
                    <div style={{ color: '#ef4444', fontSize: '0.8rem', marginTop: 4 }}>
                      {r.error}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="modal-footer">
          {allDone ? (
            <button className="btn btn-primary" onClick={onClose}>Done</button>
          ) : (
            <>
              <button className="btn btn-secondary" onClick={onClose} disabled={uploading}>Cancel</button>
              <button className="btn btn-primary" onClick={handleUpload} disabled={uploading || files.length === 0}>
                {uploading ? 'Uploading...' : `Upload ${files.length} file${files.length !== 1 ? 's' : ''}`}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
