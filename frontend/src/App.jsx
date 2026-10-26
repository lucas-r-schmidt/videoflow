import { createContext, useContext, useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import axios from 'axios'
import './index.css'

import Login       from './pages/Login'
import Dashboard   from './pages/Dashboard'
import Settings    from './pages/Settings'
import AuthCallback from './pages/AuthCallback'
import Nav         from './components/Nav'

// ── Auth Context ──────────────────────────────────────────────
const AuthCtx = createContext(null)
export const useAuth = () => useContext(AuthCtx)

export const api = axios.create({ baseURL: '/api/v1' })

function AuthProvider({ children }) {
  const [user, setUser]   = useState(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (token) {
      api.defaults.headers.common['Authorization'] = `Bearer ${token}`
      fetchMe()
    } else {
      // Auto login dev para abrir direto o painel
      axios.post('/auth/dev-login')
        .then(async ({ data }) => {
          await saveTokens(data.access_token, data.refresh_token)
        })
        .catch(() => {
          setReady(true)
        })
    }
  }, [])

  async function fetchMe(tokenOverride) {
    const token = tokenOverride || localStorage.getItem('access_token')
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
    localStorage.setItem('access_token',  access)
    localStorage.setItem('refresh_token', refresh)
    api.defaults.headers.common['Authorization'] = `Bearer ${access}`
    return await fetchMe(access)
  }

  function logout() {
    localStorage.clear()
    delete api.defaults.headers.common['Authorization']
    setUser(null)
  }

  if (!ready) return (
    <div style={{ display:'flex', alignItems:'center', justifyContent:'center', minHeight:'100vh' }}>
      <div style={{ color:'var(--text-muted)' }}>Carregando…</div>
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
  if (!ready) {
    return (
      <div style={{ display:'flex', alignItems:'center', justifyContent:'center', minHeight:'100vh' }}>
        <div style={{ color:'var(--text-muted)' }}>Carregando…</div>
      </div>
    )
  }
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
