import axios from 'axios';

const API = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 300000,
});

API.interceptors.request.use((req) => {
  const token = localStorage.getItem('token');
  if (token) {
    req.headers.Authorization = `Bearer ${token}`;
  }
  return req;
});

// ── Auth ─────────────────────────────────────────────────────────────────
export const login = (data) => API.post('/auth/login', data, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }).then(r => r.data);
export const registerFinalize = (data) => API.post('/auth/register', data).then(r => r.data);
export const getMe = () => API.get('/auth/me').then(r => r.data);
export const sendOtp = (data) => API.post('/auth/send-otp', data).then(r => r.data);
export const verifyOtp = (data) => API.post('/auth/verify-otp', data).then(r => r.data);
export const updateProfile = (data) => API.put('/auth/profile', data).then(r => r.data);
export const updateAvatar = (file) => {
  const form = new FormData();
  form.append('file', file);
  return API.post('/auth/avatar', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data);
};
export const logoutUserApi = () => API.post('/auth/logout').then(r => r.data);

// ── Cases ────────────────────────────────────────────────────────────────
export const createCase = (data) => API.post('/cases', data).then(r => r.data);
export const listCases = () => API.get('/cases').then(r => r.data);
export const getCase = (id) => API.get(`/cases/${id}`).then(r => r.data);
export const updateCase = (id, data) => API.patch(`/cases/${id}`, data).then(r => r.data);
export const deleteCase = (id) => API.delete(`/cases/${id}`);

export const uploadEvidence = (caseId, file, originalSha256, encryptionAlgorithm, iv, wrappedDeks, uploader = 'system', onProgress, sourceType = 'unknown') => {
  const form = new FormData();
  form.append('file', file);
  form.append('case_id', caseId);
  form.append('original_filename', file.name || 'uploaded_evidence');
  form.append('original_mime_type', file.type || 'application/octet-stream');
  form.append('original_sha256', originalSha256);
  form.append('encryption_algorithm', encryptionAlgorithm || 'AES-GCM-256');
  form.append('iv', iv || '');
  form.append('wrapped_deks', JSON.stringify(wrappedDeks || []));
  form.append('uploader', uploader || 'system');
  form.append('source_type', sourceType);
  return API.post('/evidence/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: onProgress,
  }).then(r => r.data);
};

export const uploadPersonPhoto = (caseId, file, originalSha256, metadata, onProgress) => {
  const form = new FormData();
  form.append('file', file);
  form.append('case_id', caseId);
  form.append('original_sha256', originalSha256);
  form.append('metadata', JSON.stringify(metadata));
  
  return API.post('/evidence/person-photo-upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: onProgress,
  }).then(r => r.data);
};

export const signEvidence = (evidenceId, signatureData) => API.post(`/evidence/${evidenceId}/sign`, signatureData).then(r => r.data);

export const listEvidence = (caseId) => API.get(`/evidence/case/${caseId}`).then(r => r.data);
export const getEvidence = (id) => API.get(`/evidence/${id}`).then(r => r.data);
export const verifyEvidence = (id) => API.get(`/evidence/${id}/verify`).then(r => r.data);
export const deleteEvidence = (id) => API.delete(`/evidence/${id}`);
export const getEvidenceDownloadUrl = (id) => `${API.defaults.baseURL}/evidence/${id}/download`;

// -- Graph API --
export const getCaseGraph = async (caseId) => {
  const res = await fetch(`${API.defaults.baseURL}/graph/case/${caseId}`)
  if (!res.ok) throw new Error('Failed to load graph')
  return res.json()
};

// ── Audit & Ledger ───────────────────────────────────────────────────────
export const getCaseAuditTrail = (caseId) => API.get(`/audit/case/${caseId}`).then(r => r.data);
export const verifyCaseChain = (caseId) => API.get(`/audit/case/${caseId}/verify`).then(r => r.data);
export const getEvidenceAuditTrail = (evidenceId) => API.get(`/audit/evidence/${evidenceId}`).then(r => r.data);

// ── RAG / Investigation Chat ─────────────────────────────────────────────
export const indexEvidence = (data) => API.post('/api/evidence/index', data).then(r => r.data);
export const globalSearch = (data) => API.post('/api/search/global', data).then(r => r.data);
export const localCaseChat = (caseId, data) => API.post(`/api/cases/${caseId}/chat`, data).then(r => r.data);
export const getLLMProviders = () => API.get('/api/llm/providers').then(r => r.data);
export const queryChat = (data) => API.post('/api/chat/query', data).then(r => r.data); // Keep for backward compat
export const reindexEvidence = (evidenceId) => API.post(`/evidence/${evidenceId}/index`).then(r => r.data);
export const reprocessEvidence = (evidenceId) => API.post(`/evidence/${evidenceId}/reprocess`).then(r => r.data);

// ── Face Recognition ─────────────────────────────────────────────────────
export const faceLookup = (file, includeLowConfidence = false) => {
  const form = new FormData();
  form.append('file', file);
  form.append('include_low_confidence', includeLowConfidence);
  return API.post('/face/lookup', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data);
};

export const faceSearchQuery = (file) => {
  const form = new FormData();
  form.append('file', file);
  return API.post('/face/search-query', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data);
};

export default API;
