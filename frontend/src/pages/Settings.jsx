import { useNavigate, useSearchParams } from 'react-router-dom'
import { useEffect } from 'react'
import { LogOut, CheckCircle, PlusCircle, Zap, ShieldCheck, ArrowLeft } from 'lucide-react'
import { useAuth } from '../App'

const CONNECTIONS = [
  {
    id:    'buffer',
    label: 'Buffer Gateway (Multi-Rede)',
    emoji: '🚀',
    href:  null,
    alwaysConnected: true,
    desc:  'Publica automaticamente no TikTok, Instagram Reels e YouTube Shorts via Buffer API',
  },
  {
    id:    'instagram',
    label: 'Instagram Reels (Direto)',
    emoji: '📸',
    href:  '/auth/instagram/login',
    desc:  'Publicação direta via Meta Graph API',
  },
  {
    id:    'tiktok',
    label: 'TikTok (Direto)',
    emoji: '🎵',
    href:  '/auth/tiktok/login',
    desc:  'Publicação direta via Content Posting API v2',
  },
  {
    id:    'google_drive',
    label: 'Google Drive',
    emoji: '💾',
    href:  null,
    desc:  'Importação direta de arquivos públicos ou via conta Google vinculada',
  },
]

export default function Settings() {
  const { user, logout, fetchMe } = useAuth()
  const nav = useNavigate()
  const [params] = useSearchParams()

  useEffect(() => {
    if (params.get('connected')) fetchMe()
  }, [])

  return (
    <div className="page" style={{ maxWidth: 680, width: '100%', margin: '0 auto', gap: 20 }}>
      <div style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 className="section-title" style={{ fontSize: '1.35rem' }}>Conexões & Conta</h1>
          <p className="section-sub">Gerencie seus canais de distribuição e credenciais do Studio</p>
        </div>
        <button type="button" className="btn btn-outline btn-sm" onClick={() => nav('/')}>
          <ArrowLeft size={14} /> Voltar ao Studio
        </button>
      </div>

      {/* ── Canais de Publicação ─────────────────────── */}
      <div className="card" style={{ width: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <Zap size={16} style={{ color: 'var(--primary-lit)' }} />
          <p style={{ fontSize: '1.02rem', fontWeight: 700 }}>Canais de Publicação</p>
        </div>
        <p className="section-sub" style={{ marginBottom: 16 }}>
          O Buffer Gateway já vem pré-integrado ao motor de publicação do servidor.
        </p>

        {CONNECTIONS.map(({ id, label, emoji, href, desc, alwaysConnected }) => {
          const connected = alwaysConnected || user?.connected?.[id]
          return (
            <div key={id} className="platform-row">
              <div className="platform-info">
                <span className="platform-icon">{emoji}</span>
                <div>
                  <p style={{ fontWeight: 700, fontSize: '.9rem' }}>{label}</p>
                  <p style={{ fontSize: '.76rem', color: 'var(--text-muted)' }}>{desc}</p>
                </div>
              </div>
              {connected ? (
                <span className="badge badge-success">
                  <CheckCircle size={12} /> Ativo
                </span>
              ) : href ? (
                <a href={href} style={{ textDecoration: 'none' }}>
                  <button type="button" className="btn btn-outline btn-sm">
                    <PlusCircle size={13} /> Conectar
                  </button>
                </a>
              ) : (
                <span className="badge badge-info">Habilitado por Link</span>
              )}
            </div>
          )
        })}
      </div>

      {/* ── Sessão e Conta ───────────────────────────── */}
      <div className="card" style={{ width: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
          <ShieldCheck size={16} style={{ color: '#34d399' }} />
          <p style={{ fontSize: '1.02rem', fontWeight: 700 }}>Sessão Autenticada</p>
        </div>

        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '14px', background: 'var(--surface-2)', borderRadius: 12,
          border: '1px solid var(--border)', marginBottom: 18, flexWrap: 'wrap', gap: 12
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {user?.avatar_url ? (
              <img
                src={user.avatar_url}
                alt="avatar"
                style={{ width: 44, height: 44, borderRadius: '50%', border: '2px solid var(--primary)' }}
              />
            ) : (
              <div style={{
                width: 44, height: 44, borderRadius: '50%',
                background: 'rgba(124, 58, 237, 0.25)',
                border: '2px solid var(--primary)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontWeight: 800, fontSize: '1rem', color: 'var(--primary-lit)'
              }}>
                {(user?.name || 'A')[0].toUpperCase()}
              </div>
            )}
            <div>
              <p style={{ fontWeight: 700, fontSize: '.95rem' }}>{user?.name || 'Administrador'}</p>
              <p style={{ fontSize: '.8rem', color: 'var(--text-muted)' }}>{user?.email}</p>
            </div>
          </div>
          <span className="badge badge-success">Sessão Ativa</span>
        </div>

        <button
          type="button"
          className="btn btn-outline"
          style={{ width: '100%', color: '#f87171', borderColor: 'rgba(239, 68, 68, 0.35)' }}
          onClick={() => { logout(); nav('/login') }}
        >
          <LogOut size={15} /> Encerrar Sessão
        </button>
      </div>
    </div>
  )
}
