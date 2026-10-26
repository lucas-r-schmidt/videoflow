import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../App'

export default function AuthCallback() {
  const [params]    = useSearchParams()
  const { saveTokens } = useAuth()
  const nav         = useNavigate()

  useEffect(() => {
    const access  = params.get('access_token')
    const refresh = params.get('refresh_token')
    if (access && refresh) {
      saveTokens(access, refresh).then(userData => {
        if (userData) {
          nav('/', { replace: true })
        } else {
          nav('/login', { replace: true })
        }
      })
    } else {
      nav('/login', { replace: true })
    }
  }, [])

  return (
    <div className="page" style={{ justifyContent:'center' }}>
      <p style={{ color:'var(--text-muted)' }}>Autenticando…</p>
    </div>
  )
}
