import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import { Lock, Sparkles, ArrowRight, ShieldCheck } from 'lucide-react'
import { useAuth } from '../App'

export default function Login() {
  const { user, saveTokens } = useAuth()
  const nav = useNavigate()
  const [devLoading, setDevLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [pin, setPin] = useState('')
  const [authTab, setAuthTab] = useState('pin') // 'pin' | 'google'

  useEffect(() => { if (user) nav('/') }, [user])

  async function handleDevLogin(pinValue) {
    const finalPin = pinValue !== undefined ? pinValue : pin
    const trimmed = (finalPin || '').trim()
    if (!trimmed) {
      setErrorMsg('Por favor, informe o PIN de acesso.')
      return
    }
    setDevLoading(true)
    setErrorMsg('')
    try {
      const { data } = await axios.post(`/auth/dev-login?pin=${encodeURIComponent(trimmed)}`, { pin: trimmed })
      const loadedUser = await saveTokens(data.access_token, data.refresh_token)
      if (loadedUser) {
        nav('/')
      } else {
        setErrorMsg('Falha ao validar sessão.')
      }
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Erro ao conectar ao servidor.'
      setErrorMsg(msg)
    } finally {
      setDevLoading(false)
    }
  }

  return (
    <div className="page" style={{ justifyContent: 'center', padding: '24px' }}>
      <div className="card" style={{
        width: '100%',
        maxWidth: 430,
        padding: '32px 30px',
        textAlign: 'center',
        border: '1px solid rgba(124, 58, 237, 0.3)',
        boxShadow: '0 24px 60px rgba(0, 0, 0, 0.65), 0 0 40px rgba(124, 58, 237, 0.14)'
      }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginBottom: 14 }} className="nav-badge">
          <span className="nav-badge-dot" />
          VideoFlow Studio 2.0
        </div>

        <h1 style={{
          fontSize: '1.75rem',
          fontWeight: 800,
          letterSpacing: '-0.03em',
          marginBottom: 8,
          background: 'linear-gradient(135deg, #ffffff 30%, #a78bfa 100%)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent'
        }}>
          Cortes Virais 9:16 com IA
        </h1>
        <p style={{ color: 'var(--text-muted)', fontSize: '.86rem', marginBottom: 22, lineHeight: 1.55 }}>
          Diretor multimodal IA, Jump Cut automático, legendas Karaokê e disparo direto para TikTok, Reels e Shorts.
        </p>

        {/* Highlights rápidos */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: 8,
          marginBottom: 22,
          padding: '10px',
          background: 'rgba(255, 255, 255, 0.025)',
          borderRadius: 12,
          border: '1px solid var(--border)'
        }}>
          {[
            ['Gemini + Whisper', 'Clímax IA'],
            ['9:16 + Karaokê', 'Auto Render'],
            ['Buffer Gateway', 'Multi-Rede']
          ].map(([title, sub]) => (
            <div key={title} style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '.78rem', fontWeight: 700, color: 'var(--primary-lit)' }}>{title}</div>
              <div style={{ fontSize: '.68rem', color: 'var(--text-dim)', marginTop: 2 }}>{sub}</div>
            </div>
          ))}
        </div>

        {/* Seletor rápido de método */}
        <div className="tabs" style={{ marginBottom: 18 }}>
          <button
            type="button"
            className={`tab ${authTab === 'pin' ? 'active' : ''}`}
            onClick={() => { setAuthTab('pin'); setErrorMsg('') }}
          >
            <Lock size={14} /> PIN do Studio
          </button>
          <button
            type="button"
            className={`tab ${authTab === 'google' ? 'active' : ''}`}
            onClick={() => { setAuthTab('google'); setErrorMsg('') }}
          >
            <ShieldCheck size={14} /> Conta Google
          </button>
        </div>

        {errorMsg && (
          <div style={{
            background: 'rgba(239, 68, 68, 0.14)',
            border: '1px solid rgba(239, 68, 68, 0.35)',
            color: '#f87171',
            padding: '10px 12px',
            borderRadius: 10,
            fontSize: '.8rem',
            marginBottom: 14,
            textAlign: 'left'
          }}>
            ⚠️ {errorMsg}
          </div>
        )}

        {authTab === 'pin' ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <input
              type="password"
              placeholder="Digite o PIN de acesso"
              value={pin}
              onChange={e => setPin(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleDevLogin(pin)}
              className="input"
              style={{
                textAlign: 'center',
                letterSpacing: 5,
                fontWeight: 800,
                fontSize: '1.1rem',
                padding: '13px'
              }}
              autoFocus
            />
            <button
              type="button"
              onClick={() => handleDevLogin(pin)}
              disabled={devLoading || !pin.trim()}
              className="btn btn-cta"
            >
              <Sparkles size={16} />
              {devLoading ? 'Desbloqueando Studio…' : 'Desbloquear Studio'}
              <ArrowRight size={16} />
            </button>
          </div>
        ) : (
          <div>
            <a href="/auth/google/login" style={{ display: 'block', textDecoration: 'none' }}>
              <button type="button" className="btn btn-google" style={{ width: '100%', padding: '13px' }}>
                <svg width="18" height="18" viewBox="0 0 48 48">
                  <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                  <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
                  <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
                  <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
                </svg>
                Continuar com Google OAuth
              </button>
            </a>
          </div>
        )}
      </div>
    </div>
  )
}
