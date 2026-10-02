import React, { useState } from 'react'
import { X } from 'lucide-react'

export default function CreateCaseModal({ onClose, onSubmit }) {
  const [form, setForm] = useState({
    title: '',
    description: '',
    investigators: '',
    priority: 'medium',
  })
  const [submitting, setSubmitting] = useState(false)

  const handleChange = (e) => {
    setForm(prev => ({ ...prev, [e.target.name]: e.target.value }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.title.trim()) return
    setSubmitting(true)
    try {
      const payload = {
        title: form.title.trim(),
        description: form.description.trim(),
        investigators: form.investigators
          .split(',')
          .map(s => s.trim())
          .filter(Boolean),
        priority: form.priority,
      }
      await onSubmit(payload)
      onClose()
    } catch (err) {
      console.error('Failed to create case:', err)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>New Investigation Case</h2>
          <button className="modal-close" onClick={onClose}><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div className="form-group">
              <label className="form-label">Case Title *</label>
              <input
                className="form-input"
                name="title"
                value={form.title}
                onChange={handleChange}
                placeholder="e.g., Operation Thunderstrike"
                required
                autoFocus
              />
            </div>
            <div className="form-group">
              <label className="form-label">Description</label>
              <textarea
                className="form-textarea"
                name="description"
                value={form.description}
                onChange={handleChange}
                placeholder="Describe the investigation scope..."
              />
            </div>
            <div className="form-group">
              <label className="form-label">Investigators (comma-separated)</label>
              <input
                className="form-input"
                name="investigators"
                value={form.investigators}
                onChange={handleChange}
                placeholder="INV-001, INV-002"
              />
            </div>
            <div className="form-group">
              <label className="form-label">Priority</label>
              <select className="form-select" name="priority" value={form.priority} onChange={handleChange}>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </div>
          </div>
          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={submitting || !form.title.trim()}>
              {submitting ? 'Creating...' : 'Create Case'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
