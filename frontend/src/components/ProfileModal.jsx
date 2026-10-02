import React, { useState, useRef } from 'react';
import { useAuth } from '../AuthContext';
import { updateProfile, updateAvatar } from '../api';
import { User, Camera } from 'lucide-react';

export default function ProfileModal({ onClose }) {
  const { user, updateUser } = useAuth();
  const [formData, setFormData] = useState({
    name: user?.name || '',
    phone: user?.phone || ''
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const fileInputRef = useRef(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const updatedUser = await updateProfile(formData);
      updateUser(updatedUser);
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update profile');
    } finally {
      setLoading(false);
    }
  };

  const handleAvatarClick = () => {
    fileInputRef.current?.click();
  };

  const handleAvatarChange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setLoading(true);
    try {
      const updatedUser = await updateAvatar(file);
      updateUser(updatedUser);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to upload avatar');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ width: '400px' }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Profile Settings</h2>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>

        <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          {error && <div className="alert alert-danger" style={{ width: '100%' }}>{error}</div>}
          
          <div 
            style={{ 
              position: 'relative', 
              width: '100px', 
              height: '100px', 
              borderRadius: '50%', 
              backgroundColor: '#2e3548',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              marginBottom: '20px',
              overflow: 'hidden'
            }}
            onClick={handleAvatarClick}
            title="Click to change avatar"
          >
            {user?.profile_picture_url ? (
              <img src={user.profile_picture_url} alt="Avatar" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            ) : (
              <User size={48} color="#9ca3af" />
            )}
            <div style={{ position: 'absolute', bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)', width: '100%', textAlign: 'center', padding: '4px 0' }}>
              <Camera size={16} color="#fff" />
            </div>
            <input 
              type="file" 
              ref={fileInputRef} 
              style={{ display: 'none' }} 
              accept="image/*"
              onChange={handleAvatarChange}
            />
          </div>

          <form onSubmit={handleSubmit} style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '15px' }}>
            <div>
              <label>Username</label>
              <input type="text" className="input-field" value={user?.username || ''} disabled style={{ opacity: 0.7 }} />
            </div>
            <div>
              <label>Email</label>
              <input type="email" className="input-field" value={user?.email || ''} disabled style={{ opacity: 0.7 }} />
            </div>
            <div>
              <label>Full Name</label>
              <input 
                type="text" 
                className="input-field" 
                value={formData.name} 
                onChange={(e) => setFormData({...formData, name: e.target.value})} 
                placeholder="Investigation Officer Name"
              />
            </div>
            <div>
              <label>Phone Number</label>
              <input 
                type="text" 
                className="input-field" 
                value={formData.phone} 
                onChange={(e) => setFormData({...formData, phone: e.target.value})} 
                placeholder="+1234567890"
              />
            </div>

            <div className="modal-footer" style={{ marginTop: '10px' }}>
              <button type="button" className="btn" onClick={onClose}>Cancel</button>
              <button type="submit" className="btn btn-primary" disabled={loading}>
                {loading ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
