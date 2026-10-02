import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import CaseDetail from './pages/CaseDetail'
import FaceSearch from './pages/FaceSearch'
import { AuthProvider, useAuth } from './AuthContext'
import AuthPage from './pages/AuthPage'
import GlobalSearch from './pages/GlobalSearch'
import './App.css'

function ProtectedApp() {
  const { user, loading } = useAuth();

  if (loading) {
    return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', color: '#fff' }}>Loading...</div>;
  }

  if (!user) {
    return <AuthPage />;
  }

  return (
    <div className="app-layout">
      <Sidebar />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/case/:caseId" element={<CaseDetail />} />
          <Route path="/face-search" element={<FaceSearch />} />
          <Route path="/global-search" element={<GlobalSearch />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <ProtectedApp />
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
