import React, { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { LayoutDashboard, FolderOpen, Shield, Activity, LogOut, User, Globe } from 'lucide-react'
import { useAuth } from '../AuthContext'
import { logoutUserApi } from '../api'
import ProfileModal from './ProfileModal'

export default function Sidebar() {
  const [apiStatus, setApiStatus] = useState('checking')
  const [showProfileModal, setShowProfileModal] = useState(false)
  const location = useLocation()
  const { user, logoutUser } = useAuth()

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
        const res = await fetch(`${baseUrl}/health`)
        if (res.ok) setApiStatus('online')
        else setApiStatus('offline')
      } catch {
        setApiStatus('offline')
      }
    }
    checkHealth()
    const interval = setInterval(checkHealth, 15000)
    return () => clearInterval(interval)
  }, [])

  const handleLogout = async () => {
    try {
      await logoutUserApi()
    } catch (err) {
      console.error('Logout failed on backend:', err)
    } finally {
      logoutUser()
    }
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-icon">CN</div>
        <div>
          <h1>Crime Nexus</h1>
          <span className="version-badge">v0.2.0</span>
        </div>
      </div>

      <nav className="sidebar-nav">
        <span className="nav-section-label">Investigation</span>
        <NavLink to="/" end className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <LayoutDashboard className="nav-icon" />
          Dashboard
        </NavLink>
        <NavLink to="/" className={({ isActive }) => `nav-item ${location.pathname.startsWith('/case/') ? 'active' : ''}`}>
          <FolderOpen className="nav-icon" />
          Cases
        </NavLink>
        <NavLink to="/face-search" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <User className="nav-icon" />
          Face Search
        </NavLink>
        <NavLink to="/global-search" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <Globe className="nav-icon" />
          Global Search
        </NavLink>

        <span className="nav-section-label">System</span>
        <div className="nav-item" style={{ opacity: 0.5, cursor: 'default' }}>
          <Shield className="nav-icon" />
          Integrity Ledger
        </div>
        <div className="nav-item" style={{ opacity: 0.5, cursor: 'default' }}>
          <Activity className="nav-icon" />
          Audit Log
        </div>
      </nav>

      <div style={{ marginTop: 'auto', padding: '16px' }}>
        <div 
          onClick={() => setShowProfileModal(true)}
          style={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: '12px', 
            padding: '12px', 
            borderRadius: '12px', 
            backgroundColor: 'rgba(241, 245, 249, 0.6)', 
            cursor: 'pointer',
            marginBottom: '12px',
            border: '1px solid rgba(148, 185, 230, 0.2)',
            transition: 'all 0.15s ease'
          }}>
          {user?.profile_picture_url ? (
            <img src={user.profile_picture_url} alt="Avatar" style={{ width: '32px', height: '32px', borderRadius: '50%', objectFit: 'cover' }} />
          ) : (
            <div style={{ width: '32px', height: '32px', borderRadius: '50%', backgroundColor: 'rgba(59, 130, 246, 0.08)', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid rgba(59, 130, 246, 0.12)' }}>
              <User size={16} color="#3b82f6" />
            </div>
          )}
          <div style={{ flex: 1, overflow: 'hidden' }}>
            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#1e293b', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
              {user?.name || user?.username}
            </div>
            <div style={{ fontSize: '0.75rem', color: '#94a3b8', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
              {user?.email}
            </div>
          </div>
        </div>
        
        <button 
          onClick={handleLogout}
          className="btn" 
          style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', backgroundColor: 'rgba(254, 226, 226, 0.4)', color: '#dc2626', border: '1px solid rgba(220, 38, 38, 0.15)', borderRadius: '12px' }}
        >
          <LogOut size={16} />
          Logout
        </button>
      </div>

      <div className="sidebar-status">
        <div className="status-indicator">
          <div className={`status-dot ${apiStatus === 'online' ? '' : 'offline'}`} />
          <span>API {apiStatus === 'online' ? 'Connected' : apiStatus === 'checking' ? 'Checking...' : 'Offline'}</span>
        </div>
      </div>
      
      {showProfileModal && <ProfileModal onClose={() => setShowProfileModal(false)} />}
    </aside>
  )
}
