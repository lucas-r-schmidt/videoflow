import { createContext, useContext, useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import axios from 'axios'
import './index.css'

import Login        from './pages/Login'
import Dashboard    from './pages/Dashboard'
import Settings     from './pages/Settings'
import AuthCallback from './pages/AuthCallback'
import Nav          from './components/Nav'

// ── Auth Context ──────────────────────────────────────────────
const AuthCtx = createContext(null)
export const useAuth = () => useContext(AuthCtx)

export const api = axios.create({ baseURL: '/api/v1' })

function getStoredToken() {
  return localStorage.getItem('access_token') || localStorage.getItem('videoflow_token') || null
}

function AuthProvider({ children }) {
  const [user, setUser]   = useState(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const token = getStoredToken()
    if (token) {
      localStorage.setItem('access_token', token)
      localStorage.setItem('videoflow_token', token)
      api.defaults.headers.common['Authorization'] = `Bearer ${token}`
      fetchMe(token)
    } else {
      setReady(true)
    }
  }, [])

  async function fetchMe(tokenOverride) {
    const token = tokenOverride || getStoredToken()
    if (!token) {
      setUser(null)
      setReady(true)
      return null
    }
    try {
      const { data } = await axios.get('/auth/me', {
        headers: { Authorization: `Bearer ${token}` }
      })
      setUser(data)
      return data
    } catch {
      logout()
      return null
    } finally {
      setReady(true)
    }
  }

  async function saveTokens(access, refresh) {
    localStorage.setItem('access_token', access)
    localStorage.setItem('videoflow_token', access)
    if (refresh) {
      localStorage.setItem('refresh_token', refresh)
      localStorage.setItem('videoflow_refresh', refresh)
    }
    api.defaults.headers.common['Authorization'] = `Bearer ${access}`
    return await fetchMe(access)
  }

  function logout() {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('videoflow_token')
    localStorage.removeItem('videoflow_refresh')
    delete api.defaults.headers.common['Authorization']
    setUser(null)
  }

  if (!ready) return (
    <div style={{ display:'flex', flexDirection:'column', gap:12, alignItems:'center', justifyContent:'center', minHeight:'100vh' }}>
      <div className="nav-logo-icon" style={{ width:44, height:44, fontSize:'1.4rem' }}>🎬</div>
      <div style={{ color:'var(--text-muted)', fontSize:'.88rem', fontWeight:600 }}>Iniciando VideoFlow Studio…</div>
    </div>
  )

  return (
    <AuthCtx.Provider value={{ user, ready, saveTokens, logout, fetchMe }}>
      {children}
    </AuthCtx.Provider>
  )
}

function Protected({ children }) {
  const { user, ready } = useAuth()
  if (!ready) return null
  return user ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login"         element={<Login />} />
          <Route path="/auth/callback" element={<AuthCallback />} />
          <Route path="/" element={
            <Protected>
              <Nav />
              <Dashboard />
            </Protected>
          } />
          <Route path="/settings" element={
            <Protected>
              <Nav />
              <Settings />
            </Protected>
          } />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
