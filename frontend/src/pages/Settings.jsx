import { useNavigate, useSearchParams } from 'react-router-dom'
import { useEffect } from 'react'
import { LogOut, CheckCircle, PlusCircle } from 'lucide-react'
import { useAuth } from '../App'

const CONNECTIONS = [
  {
    id:    'instagram',
    label: 'Instagram Reels',
    emoji: '📸',
    href:  '/auth/instagram/login',
    desc:  'Publica Reels automaticamente via Graph API',
  },
  {
    id:    'tiktok',
    label: 'TikTok',
    emoji: '🎵',
    href:  '/auth/tiktok/login',
    desc:  'Publica vídeos via Content Posting API v2',
  },
  {
    id:    'google_drive',
    label: 'Google Drive',
    emoji: '💾',
    href:  null,
    desc:  'Conectado ao fazer login com Google',
  },
]

export default function Settings() {
  const { user, logout, fetchMe } = useAuth()
  const nav = useNavigate()
  const [params] = useSearchParams()

  // Atualiza estado após callback de conexão de plataforma
  useEffect(() => {
    if (params.get('connected')) fetchMe()
  }, [])

  return (
    <div className="page" style={{ maxWidth:580, width:'100%', margin:'0 auto', gap:20 }}>

      {/* ── Plataformas ─────────────────────────────── */}
      <div className="card" style={{ width:'100%' }}>
        <p className="section-title" style={{ fontSize:'1.1rem' }}>Contas conectadas</p>
        <p className="section-sub" style={{ marginBottom:16 }}>
          Conecte suas redes sociais para publicar automaticamente.
        </p>

        {CONNECTIONS.map(({ id, label, emoji, href, desc }) => {
          const connected = user?.connected?.[id]
          return (
            <div key={id} className="platform-row">
              <div className="platform-info">
                <span className="platform-icon">{emoji}</span>
                <div>
                  <p style={{ fontWeight:600, fontSize:'.9rem' }}>{label}</p>
                  <p style={{ fontSize:'.75rem', color:'var(--text-muted)' }}>{desc}</p>
                </div>
              </div>
              {connected ? (
                <span className="badge badge-success">
                  <CheckCircle size={11} /> Conectado
                </span>
              ) : href ? (
                <a href={href}>
                  <button className="btn btn-outline btn-sm">
                    <PlusCircle size={13} /> Conectar
                  </button>
                </a>
              ) : (
                <span className="badge badge-muted">Via Google</span>
              )}
            </div>
          )
        })}
      </div>

      {/* ── Conta ───────────────────────────────────── */}
      <div className="card" style={{ width:'100%' }}>
        <p className="section-title" style={{ fontSize:'1.1rem', marginBottom:16 }}>Sua conta</p>
        <div style={{ display:'flex', alignItems:'center', gap:14, marginBottom:20 }}>
          {user?.avatar_url && (
            <img src={user.avatar_url} alt="avatar"
              style={{ width:48, height:48, borderRadius:'50%', border:'2px solid var(--primary)' }}
            />
          )}
          <div>
            <p style={{ fontWeight:600 }}>{user?.name}</p>
            <p style={{ fontSize:'.82rem', color:'var(--text-muted)' }}>{user?.email}</p>
          </div>
        </div>
        <button className="btn btn-outline" style={{ width:'100%', justifyContent:'center', color:'var(--danger)', borderColor:'var(--danger)' }}
          onClick={() => { logout(); nav('/login') }}>
          <LogOut size={15} /> Sair da conta
        </button>
      </div>

    </div>
  )
}
