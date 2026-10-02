import React, { useState, useRef, useEffect } from 'react'
import {
  X,
  Upload,
  User,
  ScanFace,
  Fingerprint,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  Camera,
  FileText,
  Check,
  Hash,
  Eye,
  Shield,
  Layers
} from 'lucide-react'
import { uploadPersonPhoto } from '../api'
import { computeFileHash } from '../utils/cryptoUtils'
import './PersonPhotoUploadModal.css'

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

const ROLES = [
  { id: 'Suspect', label: 'Suspect', class: 'role-suspect', color: '#ef4444' },
  { id: 'Person of Interest', label: 'Person of Interest', class: 'role-poi', color: '#f59e0b' },
  { id: 'Witness', label: 'Witness', class: 'role-witness', color: '#3b82f6' },
  { id: 'Victim', label: 'Victim', class: 'role-victim', color: '#a855f7' },
  { id: 'Missing Person', label: 'Missing Person', class: 'role-missing', color: '#10b981' }
]

const POSES = [
  { id: 'frontal', label: 'Frontal (Standard)' },
  { id: 'profile', label: 'Profile (3/4 Angle)' },
  { id: 'cctv', label: 'Surveillance / CCTV' },
  { id: 'other', label: 'Oblique / Other' }
]

export default function PersonPhotoUploadModal({ caseId, onClose, onUploaded }) {
  const [file, setFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [fileHashPreview, setFileHashPreview] = useState(null)
  const [dragActive, setDragActive] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [stageText, setStageText] = useState('')
  const [result, setResult] = useState(null)
  
  const [formData, setFormData] = useState({
    full_name: '',
    aliases: '',
    age_approx: '',
    gender: 'Unknown',
    id_numbers: '',
    height: '',
    build: '',
    complexion: '',
    distinguishing_marks: '',
    role_in_case: 'Suspect',
    description: '',
    pose: 'frontal'
  })

  const inputRef = useRef(null)

  // Manage photo preview URL & compute hash in background
  useEffect(() => {
    if (!file) {
      setPreviewUrl(null)
      setFileHashPreview(null)
      return
    }

    const url = URL.createObjectURL(file)
    setPreviewUrl(url)

    // Compute preview SHA-256 for biometric HUD
    let isMounted = true
    computeFileHash(file)
      .then(hash => {
        if (isMounted) setFileHashPreview(hash)
      })
      .catch(() => {
        if (isMounted) setFileHashPreview(null)
      })

    return () => {
      isMounted = false
      URL.revokeObjectURL(url)
    }
  }, [file])

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
    if (e.dataTransfer.files?.[0]) {
      const droppedFile = e.dataTransfer.files[0]
      if (droppedFile.type.startsWith('image/')) {
        setFile(droppedFile)
        setResult(null)
      }
    }
  }

  const handleInputChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleRoleSelect = (roleId) => {
    setFormData(prev => ({ ...prev, role_in_case: roleId }))
  }

  const handleUpload = async () => {
    if (!file) return
    setUploading(true)
    setResult(null)

    try {
      setStageText('Computing cryptographic SHA-256 fingerprint...')
      setProgress(15)
      
      const originalSha256 = fileHashPreview || (await computeFileHash(file))
      setProgress(35)
      setStageText('Detecting facial landmarks with RetinaFace...')

      const res = await uploadPersonPhoto(
        caseId,
        file,
        originalSha256,
        formData,
        (e) => {
          if (e.total) {
            const pct = 35 + Math.round((e.loaded * 55) / e.total)
            setProgress(pct)
            if (pct > 60 && pct < 85) {
              setStageText('Extracting 512-D ArcFace biometric embedding...')
            } else if (pct >= 85) {
              setStageText('Upserting to Qdrant vector database & case graph...')
            }
          }
        }
      )

      setProgress(100)
      setStageText('Biometric registration complete')
      setResult({ 
        success: true, 
        data: res, 
        hash: originalSha256,
        name: formData.full_name || 'Unnamed Subject',
        role: formData.role_in_case
      })

      // Notify parent after delay
      setTimeout(() => {
        onUploaded?.()
      }, 1500)

    } catch (err) {
      let errorMsg = err.message || 'Biometric ingestion failed'
      if (err.response?.data?.detail) {
        const d = err.response.data.detail
        if (typeof d === 'string') errorMsg = d
        else if (Array.isArray(d)) errorMsg = d.map(x => x.msg || JSON.stringify(x)).join(', ')
        else errorMsg = JSON.stringify(d)
      }
      setResult({ success: false, error: errorMsg })
      setUploading(false)
    }
  }

  const isFormValid = file && formData.description.trim().length > 0

  return (
    <div className="bio-modal-overlay" onClick={onClose}>
      <div className="bio-modal-dialog" onClick={(e) => e.stopPropagation()}>
        
        {/* Modal Header */}
        <div className="bio-modal-header">
          <div className="bio-header-title-wrap">
            <div className="bio-header-icon-box">
              <ScanFace size={22} />
            </div>
            <div className="bio-header-text">
              <h2>
                Biometric Photograph Ingestion
                <span className="bio-header-badge">InsightFace 512-D</span>
              </h2>
              <p>Extract facial embeddings, compute immutable SHA-256 fingerprint, and link to case dossier.</p>
            </div>
          </div>
          <button 
            className="bio-modal-close-btn" 
            onClick={onClose} 
            disabled={uploading}
            title="Close modal"
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="bio-modal-body">
          {!result?.success ? (
            <div className="bio-modal-grid">
              
              {/* Left Column: Biometric Capture Station */}
              <div className="bio-capture-station">
                <div className="bio-station-title">
                  <Camera size={14} /> 1. Biometric Photo Ingestion
                </div>

                {!file ? (
                  /* Interactive Dropzone / Viewfinder */
                  <div
                    className={`bio-viewfinder ${dragActive ? 'drag-over' : ''}`}
                    onDragEnter={handleDrag}
                    onDragLeave={handleDrag}
                    onDragOver={handleDrag}
                    onDrop={handleDrop}
                    onClick={() => inputRef.current?.click()}
                  >
                    {/* Viewfinder corner brackets */}
                    <div className="reticle-bracket reticle-top-left"></div>
                    <div className="reticle-bracket reticle-top-right"></div>
                    <div className="reticle-bracket reticle-bottom-left"></div>
                    <div className="reticle-bracket reticle-bottom-right"></div>

                    <div className="bio-radar-circle">
                      <ScanFace size={28} />
                    </div>

                    <div className="bio-viewfinder-prompt">Select Subject Photograph</div>
                    <div className="bio-viewfinder-sub">Drag & drop or click to browse</div>

                    <div className="bio-browse-pill">
                      <Upload size={13} /> Browse Files
                    </div>

                    <input
                      ref={inputRef}
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      style={{ display: 'none' }}
                      onChange={(e) => {
                        if (e.target.files?.[0]) {
                          setFile(e.target.files[0])
                          setResult(null)
                        }
                      }}
                    />
                  </div>
                ) : (
                  /* Forensic Photo Preview Frame */
                  <div className="bio-preview-container">
                    <div className="bio-preview-media">
                      <img src={previewUrl} alt="Subject Preview" className="bio-preview-img" />
                      
                      {/* Viewfinder HUD Overlays */}
                      <div className="bio-hud-top">
                        <div className={`bio-hud-tag ${uploading ? 'scanning' : ''}`}>
                          <span className={`bio-hud-dot ${uploading ? 'scanning' : ''}`}></span>
                          {uploading ? 'BIO-SCANNING ACTIVE' : 'BIOMETRIC FRAME READY'}
                        </div>
                        <div className="bio-hud-tag" style={{ color: '#2563eb', borderColor: 'rgba(37, 99, 235, 0.3)' }}>
                          {formData.pose.toUpperCase()}
                        </div>
                      </div>

                      {/* Laser Scan line on upload */}
                      {uploading && <div className="bio-scan-line"></div>}

                      {/* Face bounding box guideline */}
                      <div className="bio-face-reticle"></div>
                    </div>

                    {/* Preview Footer */}
                    <div className="bio-preview-footer">
                      <div className="bio-file-meta">
                        <span className="bio-file-name" title={file.name}>{file.name}</span>
                        <span className="bio-file-specs">
                          {formatBytes(file.size)} • {fileHashPreview ? `${fileHashPreview.substring(0, 12)}...` : 'Computing SHA...'}
                        </span>
                      </div>
                      {!uploading && (
                        <div className="bio-preview-actions">
                          <button 
                            type="button" 
                            className="btn btn-secondary btn-sm"
                            onClick={() => inputRef.current?.click()}
                          >
                            Replace
                          </button>
                          <button 
                            type="button" 
                            className="btn btn-danger btn-sm"
                            onClick={() => setFile(null)}
                          >
                            Remove
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Pose / Angle Selector */}
                <div className="bio-field-group">
                  <label className="bio-label">
                    <Eye size={12} /> Capture Perspective / Pose
                  </label>
                  <select 
                    name="pose" 
                    className="bio-select" 
                    value={formData.pose} 
                    onChange={handleInputChange}
                    disabled={uploading}
                  >
                    {POSES.map(p => (
                      <option key={p.id} value={p.id}>{p.label}</option>
                    ))}
                  </select>
                </div>

                {/* Biometric Capture Standards Guideline */}
                <div className="bio-guidelines-card">
                  <div className="bio-guidelines-title">
                    <ShieldCheck size={13} className="bio-guideline-icon" /> Biometric Ingestion Standard
                  </div>
                  <div className="bio-guideline-item">
                    <Check size={11} className="bio-guideline-icon" /> Clear frontal or &lt;45° angle portrait
                  </div>
                  <div className="bio-guideline-item">
                    <Check size={11} className="bio-guideline-icon" /> Minimum 0.65 face confidence score
                  </div>
                  <div className="bio-guideline-item">
                    <Check size={11} className="bio-guideline-icon" /> Unobstructed eyes, nose & jawline
                  </div>
                </div>

              </div>

              {/* Right Column: Forensic Dossier Form */}
              <div className="bio-dossier-column">

                {/* Card 1: Primary Identification */}
                <div className="bio-section-card">
                  <div className="bio-section-header">
                    <div className="bio-section-title">
                      <User size={14} /> Primary Identity Details
                    </div>
                    <span className="bio-section-badge">SECTION 01</span>
                  </div>

                  <div className="bio-form-row">
                    <div className="bio-field-group">
                      <label className="bio-label">Full Legal Name</label>
                      <input 
                        type="text" 
                        name="full_name" 
                        className="bio-input" 
                        placeholder="e.g. Marcus Vance"
                        value={formData.full_name} 
                        onChange={handleInputChange}
                        disabled={uploading}
                      />
                    </div>
                    <div className="bio-field-group">
                      <label className="bio-label">Known Aliases / Monikers</label>
                      <input 
                        type="text" 
                        name="aliases" 
                        className="bio-input" 
                        placeholder="e.g. 'Viper', 'Ghost'"
                        value={formData.aliases} 
                        onChange={handleInputChange}
                        disabled={uploading}
                      />
                    </div>
                  </div>

                  <div className="bio-form-row three-col">
                    <div className="bio-field-group">
                      <label className="bio-label">Estimated Age</label>
                      <input 
                        type="number" 
                        name="age_approx" 
                        className="bio-input" 
                        placeholder="e.g. 32"
                        value={formData.age_approx} 
                        onChange={handleInputChange}
                        disabled={uploading}
                        min="1"
                        max="120"
                      />
                    </div>
                    <div className="bio-field-group">
                      <label className="bio-label">Gender</label>
                      <select 
                        name="gender" 
                        className="bio-select" 
                        value={formData.gender} 
                        onChange={handleInputChange}
                        disabled={uploading}
                      >
                        <option value="Unknown">Unknown</option>
                        <option value="Male">Male</option>
                        <option value="Female">Female</option>
                        <option value="Other">Non-Binary / Other</option>
                      </select>
                    </div>
                    <div className="bio-field-group">
                      <label className="bio-label">Govt / Police ID</label>
                      <input 
                        type="text" 
                        name="id_numbers" 
                        className="bio-input" 
                        placeholder="Aadhaar / Warrant #"
                        value={formData.id_numbers} 
                        onChange={handleInputChange}
                        disabled={uploading}
                      />
                    </div>
                  </div>
                </div>

                {/* Card 2: Physical & Biometric Descriptors */}
                <div className="bio-section-card">
                  <div className="bio-section-header">
                    <div className="bio-section-title">
                      <Fingerprint size={14} /> Physical Characteristics
                    </div>
                    <span className="bio-section-badge">SECTION 02</span>
                  </div>

                  <div className="bio-form-row three-col">
                    <div className="bio-field-group">
                      <label className="bio-label">Height</label>
                      <input 
                        type="text" 
                        name="height" 
                        className="bio-input" 
                        placeholder="e.g. 5'11&quot; (180 cm)" 
                        value={formData.height} 
                        onChange={handleInputChange}
                        disabled={uploading}
                      />
                    </div>
                    <div className="bio-field-group">
                      <label className="bio-label">Build</label>
                      <input 
                        type="text" 
                        name="build" 
                        className="bio-input" 
                        placeholder="Slim, Athletic, Heavy" 
                        value={formData.build} 
                        onChange={handleInputChange}
                        disabled={uploading}
                      />
                    </div>
                    <div className="bio-field-group">
                      <label className="bio-label">Complexion</label>
                      <input 
                        type="text" 
                        name="complexion" 
                        className="bio-input" 
                        placeholder="Fair, Medium, Dark" 
                        value={formData.complexion} 
                        onChange={handleInputChange}
                        disabled={uploading}
                      />
                    </div>
                  </div>

                  <div className="bio-form-row">
                    <div className="bio-field-group full-width">
                      <label className="bio-label">Distinguishing Marks, Scars or Tattoos</label>
                      <input 
                        type="text" 
                        name="distinguishing_marks" 
                        className="bio-input" 
                        placeholder="e.g. Snake tattoo on right arm, 2-inch surgical scar above left eyebrow"
                        value={formData.distinguishing_marks} 
                        onChange={handleInputChange}
                        disabled={uploading}
                      />
                    </div>
                  </div>
                </div>

                {/* Card 3: Role & Investigative Context */}
                <div className="bio-section-card">
                  <div className="bio-section-header">
                    <div className="bio-section-title">
                      <ShieldCheck size={14} /> Case Association & Context
                    </div>
                    <span className="bio-section-badge">SECTION 03</span>
                  </div>

                  {/* Interactive Role Radio Pills */}
                  <div className="bio-field-group">
                    <label className="bio-label">
                      Role in Investigation <span className="bio-req">*</span>
                    </label>
                    <div className="bio-role-grid">
                      {ROLES.map(role => (
                        <div
                          key={role.id}
                          className={`bio-role-pill ${role.class} ${formData.role_in_case === role.id ? 'active' : ''}`}
                          onClick={() => !uploading && handleRoleSelect(role.id)}
                        >
                          <span className="bio-role-dot"></span>
                          {role.label}
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Context Narrative */}
                  <div className="bio-field-group full-width">
                    <label className="bio-label">
                      Evidence Source & Investigative Context <span className="bio-req">*</span>
                    </label>
                    <textarea 
                      name="description" 
                      className="bio-textarea" 
                      rows="3" 
                      required
                      value={formData.description} 
                      onChange={handleInputChange}
                      placeholder="Specify the origin of this photo (e.g. Seized mobile phone gallery, CCTV surveillance frame at Terminal 2, or verified informant submission)..."
                      disabled={uploading}
                    ></textarea>
                  </div>
                </div>

                {/* Processing Progress Bar */}
                {uploading && (
                  <div className="bio-progress-box">
                    <div className="bio-progress-header">
                      <span className="bio-progress-stage">
                        <Sparkles size={14} className="animate-spin" /> {stageText}
                      </span>
                      <span className="bio-progress-pct">{progress}%</span>
                    </div>
                    <div className="bio-progress-track">
                      <div className="bio-progress-bar" style={{ width: `${progress}%` }}></div>
                    </div>
                  </div>
                )}

                {/* Error Callout */}
                {result?.error && (
                  <div className="bio-error-callout">
                    <AlertTriangle size={18} style={{ flexShrink: 0, marginTop: 1 }} />
                    <div>
                      <strong>Biometric Ingestion Warning</strong>
                      <div style={{ marginTop: 2 }}>{result.error}</div>
                    </div>
                  </div>
                )}

              </div>

            </div>
          ) : (
            /* Success State Receipt */
            <div className="bio-success-receipt">
              <div className="bio-success-icon-wrap">
                <CheckCircle2 size={42} />
              </div>
              <h3 className="bio-success-title">Biometric Record Successfully Registered</h3>
              <p className="bio-success-subtitle">
                Facial vectors have been normalized, indexed into the Qdrant 512-D collection, and anchored to the case evidence graph.
              </p>

              <div className="bio-receipt-card">
                <div className="bio-receipt-row">
                  <span className="bio-receipt-label">Subject Identity</span>
                  <span className="bio-receipt-val">{result.name}</span>
                </div>
                <div className="bio-receipt-row">
                  <span className="bio-receipt-label">Assigned Role</span>
                  <span className="bio-receipt-val" style={{ color: '#2563eb' }}>{result.role}</span>
                </div>
                <div className="bio-receipt-row">
                  <span className="bio-receipt-label">Embedding Vector</span>
                  <span className="bio-receipt-val">512-D ArcFace (Normalized)</span>
                </div>
                <div className="bio-receipt-row">
                  <span className="bio-receipt-label">Cryptographic SHA-256</span>
                  <span className="bio-receipt-val" style={{ fontSize: '0.74rem' }}>
                    {result.hash}
                  </span>
                </div>
                <div className="bio-receipt-row">
                  <span className="bio-receipt-label">Vector Store</span>
                  <span className="bio-receipt-val" style={{ color: '#059669' }}>Qdrant: face_embeddings (Indexed)</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="bio-modal-footer">
          <div className="bio-footer-security-seal">
            <Shield size={14} />
            <span>Encrypted with SHA-256 audit chain provenance</span>
          </div>

          <div className="bio-footer-buttons">
            {!result?.success ? (
              <>
                <button 
                  type="button" 
                  className="btn btn-secondary" 
                  onClick={onClose} 
                  disabled={uploading}
                >
                  Cancel
                </button>
                <button 
                  type="button" 
                  className="btn btn-primary" 
                  onClick={handleUpload} 
                  disabled={uploading || !isFormValid}
                >
                  {uploading ? (
                    <>
                      <Sparkles size={16} /> Processing Biometrics...
                    </>
                  ) : (
                    <>
                      <ScanFace size={16} /> Ingest & Index Record
                    </>
                  )}
                </button>
              </>
            ) : (
              <button 
                type="button" 
                className="btn btn-primary" 
                onClick={onClose}
              >
                Close & View Dossier
              </button>
            )}
          </div>
        </div>

      </div>
    </div>
  )
}
