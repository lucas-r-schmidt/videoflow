import { useState, useEffect, useCallback } from 'react'
import { Link2, Youtube, HardDrive, Sparkles, Scissors, Send, RefreshCw } from 'lucide-react'
import { api } from '../App'

const PLATFORMS = [
  { id:'buffer',    label:'Buffer (Clipe que Vale)', emoji:'⚡' },
  { id:'instagram', label:'Instagram',               emoji:'📸' },
  { id:'tiktok',    label:'TikTok',                  emoji:'🎵' },
  { id:'kwai',      label:'Kwai',                    emoji:'🎬' },
]

const STATUS_META = {
  queued:      { label:'Na fila',      cls:'badge-muted'   },
  downloading: { label:'Baixando',     cls:'badge-info'    },
  analyzing:   { label:'Analisando',   cls:'badge-info'    },
  processing:  { label:'Processando',  cls:'badge-warn'    },
  publishing:  { label:'Publicando',   cls:'badge-warn'    },
  done:        { label:'Concluído',    cls:'badge-success' },
  failed:      { label:'Falha',        cls:'badge-muted'   },
}

const PROGRESS = { queued:5, downloading:20, analyzing:45, processing:70, publishing:90, done:100, failed:0 }

export default function Dashboard() {
  const [tab,          setTab]       = useState('highlights')
  const [sourceType,   setSrcType]   = useState('youtube')
  const [url,          setUrl]       = useState('')
  const [parts,        setParts]     = useState(60)
  const [maxClips,     setMaxClips]  = useState(3)
  const [platforms,    setPlatforms] = useState(['buffer'])
  const [subtitleStyle,setSubStyle]  = useState('none')
  const [jobs,         setJobs]      = useState([])
  const [loading,   setLoading]   = useState(false)

  const togglePlatform = (id) =>
    setPlatforms(prev => prev.includes(id) ? prev.filter(p=>p!==id) : [...prev, id])

  const submit = async () => {
    if (!url.trim()) return
    setLoading(true)
    try {
      const { data } = await api.post('/jobs', {
        source_type:      sourceType,
        [sourceType === 'youtube' ? 'source_url' : 'drive_file_id']: url.trim(),
        cut_mode:         tab,
        part_duration:    parts,
        max_clip_duration:60,
        max_clips:        maxClips,
        platforms,
        subtitle_style:   subtitleStyle,
      })
      setJobs(prev => [data, ...prev])
      setUrl('')
    } finally {
      setLoading(false)
    }
  }

  // Polling de jobs ativos
  const pollJobs = useCallback(async () => {
    const active = jobs.filter(j => !['done','failed'].includes(j.status))
    if (!active.length) return
    const updated = await Promise.all(
      active.map(j => api.get(`/jobs/${j.job_id}`).then(r => r.data))
    )
    setJobs(prev => prev.map(j => updated.find(u => u.job_id===j.job_id) || j))
  }, [jobs])

  useEffect(() => {
    const id = setInterval(pollJobs, 3000)
    return () => clearInterval(id)
  }, [pollJobs])

  return (
    <div className="page" style={{ maxWidth: 700, width:'100%', margin:'0 auto' }}>

      {/* ── Novo job ─────────────────────────────────── */}
      <div className="card" style={{ width:'100%', marginBottom: 24 }}>
        <p className="section-title">Novo vídeo</p>
        <p className="section-sub">Cole um link do YouTube ou ID do Google Drive</p>

        {/* Tabs */}
        <div className="tabs" style={{ marginBottom: 20 }}>
          <button className={`tab ${tab==='highlights'?'active':''}`} onClick={() => setTab('highlights')}>
            <Sparkles size={14} style={{ marginRight:4, display:'inline' }} />
            IA — Melhores momentos
          </button>
          <button className={`tab ${tab==='sequential'?'active':''}`} onClick={() => setTab('sequential')}>
            <Scissors size={14} style={{ marginRight:4, display:'inline' }} />
            Dividir em partes
          </button>
        </div>

        {/* Source type toggle */}
        <div style={{ display:'flex', gap:8, marginBottom: 14 }}>
          {[['youtube','YouTube',<Youtube size={14}/>],['google_drive','Google Drive',<HardDrive size={14}/>]].map(([v,l,ic])=>(
            <button key={v}
              className={`btn btn-sm ${sourceType===v?'btn-primary':'btn-outline'}`}
              onClick={()=>setSrcType(v)}
            >{ic}{l}</button>
          ))}
        </div>

        {/* URL input */}
        <div className="input-group" style={{ marginBottom:16 }}>
          <label className="label">
            {sourceType==='youtube' ? 'URL do YouTube' : 'ID do arquivo no Google Drive'}
          </label>
          <div style={{ display:'flex', gap:8 }}>
            <input className="input"
              placeholder={sourceType==='youtube' ? 'https://youtube.com/watch?v=...' : '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74...'}
              value={url}
              onChange={e=>setUrl(e.target.value)}
              onKeyDown={e=>e.key==='Enter' && submit()}
            />
          </div>
        </div>

        {/* Opções por modo */}
        {tab==='highlights' ? (
          <div className="input-group" style={{ marginBottom:16 }}>
            <label className="label">Número de clips gerados: {maxClips}</label>
            <input type="range" min={1} max={10} value={maxClips}
              onChange={e=>setMaxClips(+e.target.value)}
              style={{ accentColor:'var(--primary)' }}
            />
          </div>
        ) : (
          <div className="input-group" style={{ marginBottom:16 }}>
            <label className="label">Duração de cada parte: {parts}s</label>
            <input type="range" min={15} max={180} step={15} value={parts}
              onChange={e=>setParts(+e.target.value)}
              style={{ accentColor:'var(--primary)' }}
            />
          </div>
        )}

        {/* Plataformas */}
        <div style={{ marginBottom:20 }}>
          <p className="label" style={{ marginBottom:8 }}>Publicar em</p>
          <div style={{ display:'flex', gap:8 }}>
            {PLATFORMS.map(({id,label,emoji}) => (
              <button key={id}
                className={`btn btn-sm ${platforms.includes(id)?'btn-primary':'btn-outline'}`}
                onClick={()=>togglePlatform(id)}
              >{emoji} {label}</button>
            ))}
          </div>
        </div>

        {/* Legendas */}
        <div style={{ marginBottom:20 }}>
          <p className="label" style={{ marginBottom:8 }}>Legendas no vídeo</p>
          <div style={{ display:'flex', gap:8 }}>
            {[
              { v:'none',    l:'Sem legenda', e:'🚫' },
              { v:'simple',  l:'Simples',     e:'💬' },
              { v:'karaoke', l:'Karaokê',     e:'🎤' },
            ].map(({v,l,e}) => (
              <button key={v}
                className={`btn btn-sm ${subtitleStyle===v?'btn-primary':'btn-outline'}`}
                onClick={()=>setSubStyle(v)}
                title={v==='karaoke' ? 'Palavra por palavra destacada — estilo TikTok viral' : ''}
              >{e} {l}</button>
            ))}
          </div>
          {subtitleStyle==='karaoke' && (
            <p style={{ fontSize:'.74rem', color:'var(--primary-lit)', marginTop:6 }}>
              ✨ Palavra ativa destacada em amarelo — estilo TikTok viral
            </p>
          )}
          {subtitleStyle==='simple' && (
            <p style={{ fontSize:'.74rem', color:'var(--text-muted)', marginTop:6 }}>
              Legenda centralizada com fundo semi-transparente
            </p>
          )}
        </div>

        <button className="btn btn-primary" style={{ width:'100%', justifyContent:'center' }}
          onClick={submit} disabled={loading||!url.trim()}>
          <Send size={15} />
          {loading ? 'Enviando…' : 'Processar & Publicar'}
        </button>
      </div>

      {/* ── Lista de jobs ─────────────────────────────── */}
      {jobs.length > 0 && (
        <div style={{ width:'100%' }}>
          <p style={{ fontWeight:600, marginBottom:12, color:'var(--text-muted)', fontSize:'.85rem' }}>
            JOBS RECENTES
          </p>
          <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
            {jobs.map(job => {
              const meta = STATUS_META[job.status] || STATUS_META.queued
              const pct  = PROGRESS[job.status] || 0
              return (
                <div key={job.job_id} className="job-card">
                  <div style={{ flex:1 }}>
                    <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:6 }}>
                      <code style={{ fontSize:'.75rem', color:'var(--text-muted)' }}>
                        {job.job_id.slice(0,8)}…
                      </code>
                      <span className={`badge ${meta.cls}`}>{meta.label}</span>
                    </div>
                    <div className="progress-track">
                      <div className="progress-bar" style={{ width:`${pct}%` }} />
                    </div>
                    {job.status==='done' && job.output_files?.length > 0 && (
                      <p style={{ fontSize:'.75rem', color:'var(--success)', marginTop:6 }}>
                        ✅ {job.output_files.length} clip(s) publicado(s)
                      </p>
                    )}
                    {job.status==='failed' && (
                      <p style={{ fontSize:'.75rem', color:'var(--danger)', marginTop:6 }}>
                        ❌ {job.error_message || 'Erro desconhecido'}
                      </p>
                    )}
                  </div>
                  {!['done','failed'].includes(job.status) && (
                    <RefreshCw size={14} style={{ color:'var(--text-dim)', animation:'spin 2s linear infinite' }} />
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}
