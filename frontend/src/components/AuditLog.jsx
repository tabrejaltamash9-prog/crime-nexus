import React, { useState, useEffect } from 'react';
import { ShieldCheck, ShieldAlert, Clock, Hash, CheckCircle, XCircle } from 'lucide-react';
import { getCaseAuditTrail, verifyCaseChain } from '../api';

export default function AuditLog({ caseId }) {
  const [entries, setEntries] = useState([]);
  const [chainStatus, setChainStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);

  useEffect(() => {
    fetchAuditTrail();
  }, [caseId]);

  const fetchAuditTrail = async () => {
    try {
      const data = await getCaseAuditTrail(caseId);
      setEntries(data.entries || []);
    } catch (err) {
      console.error('Failed to load audit trail:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyChain = async () => {
    setVerifying(true);
    try {
      const status = await verifyCaseChain(caseId);
      setChainStatus(status);
    } catch (err) {
      setChainStatus({ valid: false, message: 'Verification failed to execute.' });
    } finally {
      setVerifying(false);
    }
  };

  if (loading) return <div className="empty-state"><p>Loading ledger...</p></div>;

  return (
    <div className="audit-log-container" style={{ marginTop: '20px' }}>
      <div className="audit-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h3>Integrity Ledger</h3>
        <button className="btn btn-secondary" onClick={handleVerifyChain} disabled={verifying}>
          <ShieldCheck size={16} /> {verifying ? 'Verifying Chain...' : 'Verify Chain Integrity'}
        </button>
      </div>

      {chainStatus && (
        <div className={`alert ${chainStatus.valid ? 'alert-success' : 'alert-danger'}`} style={{ marginBottom: '20px', padding: '15px', borderRadius: '8px', display: 'flex', alignItems: 'center', gap: '10px', backgroundColor: chainStatus.valid ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)', border: `1px solid ${chainStatus.valid ? '#10b981' : '#ef4444'}` }}>
          {chainStatus.valid ? <CheckCircle color="#10b981" /> : <XCircle color="#ef4444" />}
          <div>
            <strong>{chainStatus.valid ? 'Chain Intact' : 'Chain Broken'}</strong>
            <p style={{ margin: '4px 0 0', fontSize: '0.9rem' }}>{chainStatus.message}</p>
          </div>
        </div>
      )}

      {entries.length === 0 ? (
        <div className="empty-state">
          <p>No ledger entries found.</p>
        </div>
      ) : (
        <div className="audit-timeline" style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
          {entries.map((entry, index) => (
            <div key={entry.entryId} className="audit-entry" style={{ padding: '15px', backgroundColor: '#1a1f2e', border: '1px solid #2e3548', borderRadius: '8px', borderLeft: '4px solid #3b82f6' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px' }}>
                <span className="badge badge-primary" style={{ backgroundColor: 'rgba(59, 130, 246, 0.2)', color: '#60a5fa', padding: '4px 8px', borderRadius: '4px', fontSize: '0.8rem', fontWeight: 'bold' }}>
                  {entry.action}
                </span>
                <span style={{ fontSize: '0.85rem', color: '#9ca3af', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Clock size={12} /> {new Date(entry.createdAt).toLocaleString()}
                </span>
              </div>
              
              <div style={{ marginBottom: '10px', fontSize: '0.95rem' }}>
                <strong>Actor:</strong> {entry.actor} <br/>
                <strong>Details:</strong> {entry.details}
              </div>

              <div style={{ fontSize: '0.8rem', color: '#6b7280', display: 'flex', flexDirection: 'column', gap: '4px', backgroundColor: '#0f131a', padding: '10px', borderRadius: '4px', fontFamily: 'monospace' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                  <Hash size={12} style={{ marginTop: '2px' }} />
                  <span style={{ wordBreak: 'break-all' }}><strong>Block Hash:</strong> {entry.blockHash}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                  <Hash size={12} style={{ marginTop: '2px' }} />
                  <span style={{ wordBreak: 'break-all' }}><strong>Prev Hash:</strong> {entry.prevHash}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
