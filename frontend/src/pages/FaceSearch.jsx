import React, { useState, useRef } from 'react';
import { Upload, Camera, AlertCircle, CheckCircle, Shield, User, FileText } from 'lucide-react';
import { Link } from 'react-router-dom';
import { faceSearchQuery } from '../api';

export default function FaceSearch() {
  const [file, setFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

  const handleFileChange = (e) => {
    const selected = e.target.files[0];
    if (selected && selected.type.startsWith('image/')) {
      setFile(selected);
      setPreviewUrl(URL.createObjectURL(selected));
      setResults(null);
      setError(null);
    } else {
      setError("Please select a valid image file.");
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const selected = e.dataTransfer.files[0];
    if (selected && selected.type.startsWith('image/')) {
      setFile(selected);
      setPreviewUrl(URL.createObjectURL(selected));
      setResults(null);
      setError(null);
    } else {
      setError("Please drop a valid image file.");
    }
  };

  const handleSearch = async () => {
    if (!file) return;

    setLoading(true);
    setError(null);

    try {
      const data = await faceSearchQuery(file);
      setResults(data);
    } catch (err) {
      setError(err.response?.data?.detail || "Face search failed.");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '24px', maxWidth: '1000px', margin: '0 auto' }}>
      <header style={{ marginBottom: '24px' }}>
        <h1 style={{ color: '#1e293b', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Camera size={28} color="#3b82f6" />
          Face Identity Search
        </h1>
        <p style={{ color: '#64748b', marginTop: '8px' }}>
          Standalone identity lookup. Query photos are transient and are not stored in the evidence vault.
        </p>
      </header>

      <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
        {/* Upload Column */}
        <div style={{ flex: '1 1 300px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div
            onDragOver={handleDragOver}
            onDrop={handleDrop}
            style={{
              border: '2px dashed rgba(148, 185, 230, 0.3)',
              borderRadius: '16px',
              padding: '32px',
              textAlign: 'center',
              backgroundColor: 'rgba(255, 255, 255, 0.55)',
              backdropFilter: 'blur(20px) saturate(1.5)',
              WebkitBackdropFilter: 'blur(20px) saturate(1.5)',
              cursor: 'pointer',
              transition: 'border-color 0.2s, box-shadow 0.2s',
              position: 'relative',
              minHeight: '300px',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
            }}
            onClick={() => fileInputRef.current.click()}
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              style={{ display: 'none' }}
              accept="image/*"
            />

            {previewUrl ? (
              <img 
                src={previewUrl} 
                alt="Preview" 
                style={{ 
                  maxWidth: '100%', 
                  maxHeight: '260px', 
                  borderRadius: '12px',
                  objectFit: 'contain',
                  boxShadow: '0 4px 16px rgba(0,0,0,0.08)'
                }} 
              />
            ) : (
              <>
                <Upload size={48} color="#94a3b8" style={{ marginBottom: '16px' }} />
                <p style={{ color: '#475569', fontWeight: '500' }}>Click or drag photo to search</p>
                <p style={{ color: '#94a3b8', fontSize: '0.85rem', marginTop: '8px' }}>JPEG, PNG up to 10MB</p>
              </>
            )}
          </div>

          <button
            onClick={handleSearch}
            disabled={!file || loading}
            className="btn btn-primary"
            style={{ padding: '12px', width: '100%', borderRadius: '50px', fontSize: '0.95rem' }}
          >
            {loading ? 'Searching...' : 'Search Identity Database'}
          </button>

          {error && (
            <div style={{ padding: '12px', backgroundColor: 'rgba(254, 226, 226, 0.5)', color: '#dc2626', borderRadius: '12px', display: 'flex', gap: '8px', alignItems: 'center', border: '1px solid rgba(220, 38, 38, 0.15)' }}>
              <AlertCircle size={18} />
              <span style={{ fontSize: '0.9rem' }}>{error}</span>
            </div>
          )}
        </div>

        {/* Results Column */}
        <div style={{ flex: '2 1 500px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {results && (
            <div style={{ backgroundColor: 'rgba(255, 255, 255, 0.55)', backdropFilter: 'blur(20px) saturate(1.5)', WebkitBackdropFilter: 'blur(20px) saturate(1.5)', borderRadius: '16px', padding: '24px', border: '1px solid rgba(255, 255, 255, 0.7)', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', paddingBottom: '16px', borderBottom: '1px solid rgba(148, 185, 230, 0.18)' }}>
                <h2 style={{ color: '#1e293b', fontSize: '1.2rem', margin: 0 }}>Search Results</h2>
                <div style={{ display: 'flex', gap: '12px' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.85rem', color: '#64748b' }}>
                    <CheckCircle size={14} color="#059669" />
                    Query Quality: {(results.query_face_quality * 100).toFixed(0)}%
                  </span>
                </div>
              </div>

              {results.message && (
                <div style={{ textAlign: 'center', padding: '32px 0', color: '#94a3b8' }}>
                  <Shield size={48} color="#cbd5e1" style={{ margin: '0 auto 16px auto', opacity: 0.5 }} />
                  <p>{results.message}</p>
                </div>
              )}

              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {results.results?.map((match, idx) => (
                  <div key={idx} style={{ 
                    backgroundColor: 'rgba(255, 255, 255, 0.6)', 
                    borderRadius: '12px', 
                    padding: '16px', 
                    border: '1px solid rgba(148, 185, 230, 0.18)',
                    position: 'relative',
                    overflow: 'hidden',
                    transition: 'all 0.2s',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.04)'
                  }}>
                    {/* Confidence bar background */}
                    <div style={{ 
                      position: 'absolute', 
                      bottom: 0, 
                      left: 0, 
                      height: '3px', 
                      backgroundColor: match.confidence > 0.8 ? '#059669' : match.confidence > 0.6 ? '#d97706' : '#dc2626',
                      width: `${Math.min(100, Math.max(0, match.confidence * 100))}%`,
                      transition: 'width 1s ease-out'
                    }} />
                    
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{ width: '40px', height: '40px', borderRadius: '50%', backgroundColor: 'rgba(59, 130, 246, 0.08)', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid rgba(59, 130, 246, 0.12)' }}>
                          <User size={20} color="#3b82f6" />
                        </div>
                        <div>
                          <h3 style={{ color: '#1e293b', margin: '0 0 4px 0', fontSize: '1.1rem' }}>
                            {match.person_record?.full_name || 'Unknown Individual'}
                          </h3>
                          <span style={{ color: '#64748b', fontSize: '0.85rem', fontFamily: 'monospace' }}>
                            Case: {match.case_title} ({match.case_id?.substring(0, 8)})
                          </span>
                        </div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ color: match.confidence > 0.8 ? '#059669' : match.confidence > 0.6 ? '#d97706' : '#dc2626', fontWeight: '600', fontSize: '1.2rem' }}>
                          {(match.confidence * 100).toFixed(1)}%
                        </div>
                        <div style={{ color: '#94a3b8', fontSize: '0.8rem' }}>Confidence</div>
                      </div>
                    </div>

                    {match.person_record && (
                      <div style={{ marginTop: '16px', paddingTop: '16px', borderTop: '1px solid rgba(148, 185, 230, 0.15)' }}>
                        <h4 style={{ color: '#475569', fontSize: '0.9rem', marginBottom: '12px', margin: 0, display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <User size={14} /> Original Upload Details
                        </h4>
                        
                        <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                          {match.person_record.photo_url && (
                            <div style={{ flexShrink: 0, width: '120px' }}>
                              <img 
                                src={`http://localhost:8000${match.person_record.photo_url}`} 
                                alt="Original" 
                                style={{ width: '100%', borderRadius: '10px', border: '1px solid rgba(148, 185, 230, 0.2)', objectFit: 'cover' }} 
                              />
                            </div>
                          )}
                          <div style={{ flex: 1, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '8px', fontSize: '0.85rem' }}>
                            {match.person_record.aliases && (
                              <div><span style={{ color: '#94a3b8' }}>Aliases:</span> <span style={{ color: '#475569' }}>{match.person_record.aliases}</span></div>
                            )}
                            {match.person_record.age_approx && (
                              <div><span style={{ color: '#94a3b8' }}>Age:</span> <span style={{ color: '#475569' }}>{match.person_record.age_approx}</span></div>
                            )}
                            {match.person_record.gender && (
                              <div><span style={{ color: '#94a3b8' }}>Gender:</span> <span style={{ color: '#475569' }}>{match.person_record.gender}</span></div>
                            )}
                            {match.person_record.height && (
                              <div><span style={{ color: '#94a3b8' }}>Height:</span> <span style={{ color: '#475569' }}>{match.person_record.height}</span></div>
                            )}
                            {match.person_record.build && (
                              <div><span style={{ color: '#94a3b8' }}>Build:</span> <span style={{ color: '#475569' }}>{match.person_record.build}</span></div>
                            )}
                            {match.person_record.distinguishing_marks && (
                              <div style={{ gridColumn: '1 / -1' }}><span style={{ color: '#94a3b8' }}>Marks:</span> <span style={{ color: '#475569' }}>{match.person_record.distinguishing_marks}</span></div>
                            )}
                            {match.person_record.description && (
                              <div style={{ gridColumn: '1 / -1' }}><span style={{ color: '#94a3b8' }}>Description:</span> <span style={{ color: '#475569' }}>{match.person_record.description}</span></div>
                            )}
                          </div>
                        </div>
                      </div>
                    )}

                    <div style={{ marginTop: '16px', paddingTop: '16px', borderTop: '1px solid rgba(148, 185, 230, 0.15)' }}>
                      <h4 style={{ color: '#475569', fontSize: '0.9rem', marginBottom: '12px', margin: 0, display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <FileText size={14} /> Match Details
                      </h4>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        <Link 
                          to={`/case/${match.case_id}`}
                          style={{ 
                            display: 'flex', 
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            backgroundColor: 'rgba(241, 245, 249, 0.6)', 
                            padding: '12px 16px', 
                            borderRadius: '12px', 
                            textDecoration: 'none',
                            border: '1px solid rgba(148, 185, 230, 0.18)',
                            transition: 'all 0.2s'
                          }}
                          onMouseOver={(e) => {
                            e.currentTarget.style.borderColor = 'rgba(59, 130, 246, 0.3)';
                            e.currentTarget.style.backgroundColor = 'rgba(59, 130, 246, 0.04)';
                          }}
                          onMouseOut={(e) => {
                            e.currentTarget.style.borderColor = 'rgba(148, 185, 230, 0.18)';
                            e.currentTarget.style.backgroundColor = 'rgba(241, 245, 249, 0.6)';
                          }}
                        >
                          <div>
                            <div style={{ color: '#1e293b', fontWeight: '500', fontSize: '0.95rem', marginBottom: '4px' }}>
                              {match.case_title}
                            </div>
                            <div style={{ color: '#64748b', fontSize: '0.8rem', display: 'flex', gap: '8px' }}>
                              <span>Role: <strong style={{ color: '#475569' }}>{match.person_record?.role_in_case || 'Unknown'}</strong></span>
                              <span>•</span>
                              <span style={{ 
                                color: match.case_status === 'open' ? '#059669' : match.case_status === 'closed' ? '#dc2626' : '#3b82f6' 
                              }}>
                                {match.case_status ? match.case_status.toUpperCase() : 'UNKNOWN'}
                              </span>
                            </div>
                          </div>
                          <div style={{ color: '#94a3b8' }}>
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M9 18l6-6-6-6" />
                            </svg>
                          </div>
                        </Link>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          
          {!results && !loading && (
            <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8', border: '1px dashed rgba(148, 185, 230, 0.3)', borderRadius: '16px', backgroundColor: 'rgba(255, 255, 255, 0.4)', backdropFilter: 'blur(16px)', minHeight: '300px' }}>
              Upload a photo to search the identity graph.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
