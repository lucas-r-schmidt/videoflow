import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Sparkles, Settings, LogOut } from 'lucide-react'
import { useAuth } from '../App'

export default function Nav() {
  const { user, logout } = useAuth()
  const { pathname } = useLocation()
  const nav = useNavigate()

  return (
    <nav className="nav">
      <Link to="/" className="nav-brand">
        <div className="nav-logo-icon">🎬</div>
        <span className="nav-logo">VideoFlow</span>
        <span className="nav-badge">
          <span className="nav-badge-dot" />
          Studio 2.0
        </span>
      </Link>

      <div className="nav-links">
        <Link to="/" className={`nav-link ${pathname === '/' ? 'active' : ''}`}>
          <Sparkles size={15} />
          Studio de Cortes
        </Link>
        <Link to="/settings" className={`nav-link ${pathname === '/settings' ? 'active' : ''}`}>
          <Settings size={15} />
          Conexões & Conta
        </Link>
      </div>

      <div className="nav-right">
        <span style={{ fontSize: '.8rem', fontWeight: 600, color: 'var(--text-muted)' }}>
          {user?.name?.split(' ')[0] || 'Admin'}
        </span>
        {user?.avatar_url ? (
          <img src={user.avatar_url} alt="avatar" className="avatar" />
        ) : (
          <div style={{
            width: 30, height: 30, borderRadius: '50%',
            background: 'rgba(124, 58, 237, 0.25)',
            border: '1px solid rgba(124, 58, 237, 0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '.76rem', fontWeight: 800, color: 'var(--primary-lit)'
          }}>
            {(user?.name || 'A')[0].toUpperCase()}
          </div>
        )}
        <button
          type="button"
          className="btn btn-outline btn-xs"
          title="Sair da sessão"
          onClick={() => { logout(); nav('/login') }}
        >
          <LogOut size={13} />
          Sair
        </button>
      </div>
    </nav>
  )
}
