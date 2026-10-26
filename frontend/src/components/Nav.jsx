import { Link, useLocation } from 'react-router-dom'
import { LayoutDashboard, Settings } from 'lucide-react'
import { useAuth } from '../App'

export default function Nav() {
  const { user }   = useAuth()
  const { pathname } = useLocation()

  const link = (to, label, Icon) => (
    <Link to={to} style={{
      display:'flex', alignItems:'center', gap:6,
      textDecoration:'none',
      fontSize:'.85rem', fontWeight:600,
      color: pathname===to ? 'var(--primary-lit)' : 'var(--text-muted)',
      transition:'color .15s',
    }}>
      <Icon size={15} />{label}
    </Link>
  )

  return (
    <nav className="nav">
      <span className="nav-logo">🎬 VideoFlow</span>
      <div style={{ display:'flex', gap:20 }}>
        {link('/', 'Dashboard', LayoutDashboard)}
        {link('/settings', 'Configurações', Settings)}
      </div>
      <div className="nav-right">
        <span style={{ fontSize:'.82rem', color:'var(--text-muted)' }}>{user?.name?.split(' ')[0]}</span>
        {user?.avatar_url && <img src={user.avatar_url} alt="avatar" className="avatar" />}
      </div>
    </nav>
  )
}
