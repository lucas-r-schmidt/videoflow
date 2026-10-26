import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import { useAuth } from '../App'

export default function Login() {
  const { user, saveTokens } = useAuth()
  const nav = useNavigate()
  const [devLoading, setDevLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')

  useEffect(() => { if (user) nav('/') }, [user])

  async function handleDevLogin() {
    setDevLoading(true)
    setErrorMsg('')
    try {
      const { data } = await axios.post('/auth/dev-login')
      const loadedUser = await saveTokens(data.access_token, data.refresh_token)
      if (loadedUser) {
        nav('/')
      } else {
        setErrorMsg('Falha ao autenticar sessão de teste.')
      }
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Erro ao conectar ao backend.'
      setErrorMsg(`Erro: ${msg} (Verifique se o backend está rodando)`)
    } finally {
      setDevLoading(false)
    }
  }

  return (
    <div className="page" style={{ justifyContent:'center' }}>
      <div className="card" style={{
        width: '100%', maxWidth: 400,
        textAlign: 'center',
        animation: 'fadeUp .5s ease both'
      }}>
        {/* Logo */}
        <div style={{ fontSize: '2.8rem', marginBottom: 8 }}>🎬</div>
        <h1 style={{
          fontSize: '1.6rem', fontWeight: 800, marginBottom: 6,
          background: 'linear-gradient(135deg,#9d6bfa,#06b6d4)',
          WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent'
        }}>
          VideoFlow
        </h1>
        <p style={{ color:'var(--text-muted)', fontSize:'.9rem', marginBottom: 32, lineHeight: 1.6 }}>
          Automatize o download, corte e publicação de vídeos no Instagram, TikTok e Kwai.
        </p>

        {/* Stats rápidos */}
        <div style={{ display:'flex', justifyContent:'center', gap: 24, marginBottom: 32 }}>
          {[['IA', 'Highlights'], ['9:16', 'Auto-crop'], ['3', 'Plataformas']].map(([v, l]) => (
            <div key={l} style={{ textAlign:'center' }}>
              <div style={{ fontSize:'1.2rem', fontWeight:700, color:'var(--primary-lit)' }}>{v}</div>
              <div style={{ fontSize:'.72rem', color:'var(--text-muted)' }}>{l}</div>
            </div>
          ))}
        </div>

        {errorMsg && (
          <div style={{
            background: 'rgba(239, 68, 68, 0.15)',
            border: '1px solid rgba(239, 68, 68, 0.4)',
            color: '#f87171',
            padding: '10px 14px',
            borderRadius: 'var(--radius)',
            fontSize: '.82rem',
            marginBottom: 16,
            textAlign: 'left'
          }}>
            {errorMsg}
          </div>
        )}

        <a href="http://localhost:8000/auth/google/login" style={{ display:'block', textDecoration:'none', marginBottom: 12 }}>
          <button className="btn btn-google" style={{ width:'100%', justifyContent:'center' }}>
            <svg width="18" height="18" viewBox="0 0 48 48">
              <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
              <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
              <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
              <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
            </svg>
            Continuar com Google
          </button>
        </a>

        {/* Botão Teste / Dev */}
        <button
          onClick={handleDevLogin}
          disabled={devLoading}
          className="btn"
          style={{
            width:'100%',
            justifyContent:'center',
            background: 'rgba(255,255,255,0.06)',
            border: '1px solid rgba(255,255,255,0.15)',
            color: 'var(--text)',
            cursor: devLoading ? 'not-allowed' : 'pointer',
            padding: '10px 16px',
            borderRadius: 'var(--radius)',
            fontSize: '.9rem',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            opacity: devLoading ? 0.7 : 1,
          }}
        >
          {devLoading ? 'Autenticando teste…' : '⚡ Entrar como Teste / Dev'}
        </button>

        <p style={{ marginTop: 20, fontSize:'.75rem', color:'var(--text-dim)' }}>
          Ao entrar, você concorda com os termos de uso.
        </p>
      </div>

      <style>{`
        @keyframes fadeUp {
          from { opacity:0; transform:translateY(24px); }
          to   { opacity:1; transform:translateY(0); }
        }
      `}</style>
    </div>
  )
}
