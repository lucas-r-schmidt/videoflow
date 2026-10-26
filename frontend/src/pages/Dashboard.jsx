import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Sparkles, Scissors, Send, RefreshCw, Flame, Clock, Calendar,
  Upload, Link2, CheckCircle2, AlertCircle, Play, Download,
  Copy, Check, Smartphone, Sliders, Zap, Film, Trash2, ClipboardPaste,
  ShieldCheck, Shield, Plus, X
} from 'lucide-react'
import { api } from '../App'

const PLATFORMS = [
  { id: 'buffer',    label: 'Buffer (Clipe que Vale)', emoji: '🚀', desc: 'TikTok, Reels e Shorts' },
  { id: 'instagram', label: 'Instagram Direto',        emoji: '📸', desc: 'Graph API' },
  { id: 'tiktok',    label: 'TikTok Direto',           emoji: '🎵', desc: 'Posting API' },
  { id: 'kwai',      label: 'Kwai',                    emoji: '🎬', desc: 'Pacote pronto' },
]

const STATUS_META = {
  queued:      { label: 'Na Fila',      cls: 'badge-muted',   step: 1 },
  downloading: { label: 'Baixando',     cls: 'badge-info',    step: 1 },
  analyzing:   { label: 'Analisando IA',cls: 'badge-info',    step: 2 },
  processing:  { label: 'Renderizando', cls: 'badge-warn',    step: 4 },
  publishing:  { label: 'Publicando',   cls: 'badge-warn',    step: 5 },
  done:        { label: 'Concluído',    cls: 'badge-success', step: 5 },
  failed:      { label: 'Falhou',       cls: 'badge-danger',  step: 0 },
  cancelled:   { label: 'Cancelado',    cls: 'badge-muted',   step: 0 },
}

const PROGRESS = {
  queued: 8,
  downloading: 24,
  analyzing: 50,
  processing: 76,
  publishing: 92,
  done: 100,
  failed: 0,
  cancelled: 0,
}

const PIPELINE_STEPS = [
  { num: 1, label: 'Recebendo e baixando vídeo fonte' },
  { num: 2, label: 'Transcrevendo áudio com Whisper IA' },
  { num: 3, label: 'Diretor IA selecionando clímax e copy viral' },
  { num: 4, label: 'Renderizando 9:16 + Jump Cut + Legendas' },
  { num: 5, label: 'Publicando no destino / Finalizando' },
]

const HOOK_SUGGESTIONS = [
  { label: '✨ IA Automática', value: '' },
  { label: '👀 NÃO FAÇA ISSO', value: 'NÃO FAÇA ISSO 👀' },
  { label: '😱 ESPERE ATÉ O FINAL', value: 'ESPERE ATÉ O FINAL 😱' },
  { label: '🔥 O SEGREDO REVELADO', value: 'O SEGREDO QUE NINGUÉM CONTA 🔥' },
]

function detectSourceFromInput(raw) {
  const val = (raw || '').trim()
  if (!val) return { type: 'youtube', label: 'Aguardando link…', icon: '🔗' }
  if (/youtube\.com|youtu\.be/i.test(val)) {
    const isShorts = /\/shorts\//i.test(val)
    return { type: 'youtube', label: isShorts ? 'YouTube Shorts detectado' : 'YouTube detectado', icon: '▶️' }
  }
  if (/drive\.google\.com/i.test(val) || /^[a-zA-Z0-9_-]{18,60}$/.test(val)) {
    return { type: 'google_drive', label: 'Google Drive detectado', icon: '💾' }
  }
  return { type: 'youtube', label: 'Link externo detectado', icon: '🌐' }
}

function getSuggestedScheduleTime() {
  const now = new Date()
  now.setHours(now.getHours() + 1)
  now.setMinutes(0, 0, 0)
  const pad = n => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`
}

export default function Dashboard() {
  // ── Input & Source State ──────────────────────────────────────
  const [inputMode, setInputMode]           = useState('link') // 'link' | 'upload'
  const [url, setUrl]                       = useState('')
  const [uploadFile, setUploadFile]         = useState(null)
  const [isDragging, setIsDragging]         = useState(false)
  const [uploadPct, setUploadPct]           = useState(0)
  const fileInputRef                        = useRef(null)

  // ── Preset & Cut Config State ─────────────────────────────────
  const [activePreset, setActivePreset]     = useState('viral_ai') // 'viral_ai' | 'series_parts' | 'custom'
  const [nichePreset, setNichePreset]       = useState('general') // 'general' | 'emotional' | 'debate'
  const [tab, setTab]                       = useState('highlights') // 'highlights' | 'sequential'
  const [aspectMode, setAspectMode]         = useState('fill') // 'fill' | 'blur' | 'split'
  const [subtitleStyle, setSubStyle]        = useState('karaoke') // 'karaoke' | 'simple' | 'none'
  const [enableHook, setEnableHook]         = useState(true)
  const [hookText, setHookText]             = useState('')
  const [maxClipDuration, setMaxClipDuration] = useState(60)
  const [splitLongClips, setSplitLongClips] = useState(true)
  const [autoClips, setAutoClips]           = useState(true)
  const [maxClips, setMaxClips]             = useState(3)
  const [jumpCut, setJumpCut]               = useState(true)
  const [parts, setParts]                   = useState(60)
  const [maxSeqParts, setMaxSeqParts]       = useState(0) // 0 = todas as partes
  const [showAdvanced, setShowAdvanced]     = useState(false)

  // ── Tratamentos Audiovisuais Fair Use / Anti-Content ID (Sprint 2) ──
  const [enableBgm, setEnableBgm]           = useState(true)
  const [speedBoost, setSpeedBoost]         = useState(1.03)
  const [enableHeadline, setEnableHeadline] = useState(true)

  // ── Destination & Schedule State ──────────────────────────────
  const [destinationMode, setDestMode]      = useState('publish') // 'publish' | 'download_only'
  const [platforms, setPlatforms]           = useState(['buffer'])
  const [publishMode, setPublishMode]       = useState('shareNow') // 'shareNow' | 'addToQueue' | 'scheduled'
  const [dueAt, setDueAt]                   = useState(getSuggestedScheduleTime)

  // ── Authorized Channels & Moderation State ──────────────────
  const [showChannelsModal, setShowChannelsModal] = useState(false)
  const [authorizedChannels, setAuthorizedChannels] = useState([])
  const [channelsLoading, setChannelsLoading] = useState(false)
  const [newChanName, setNewChanName]       = useState('')
  const [newChanUrl, setNewChanUrl]         = useState('')
  const [newChanDelay, setNewChanDelay]     = useState(24)
  const [newChanNotes, setNewChanNotes]     = useState('')
  const [addingChannel, setAddingChannel]   = useState(false)
  const [actionLoadingId, setActionLoadingId] = useState(null)
  const [requiresApproval, setRequiresApproval] = useState(true)

  // ── Jobs, Gallery & UI Feedback State ─────────────────────────
  const [jobs, setJobs]                     = useState([])
  const [jobsLoading, setJobsLoading]       = useState(true)
  const [jobFilter, setJobFilter]           = useState('all') // 'all' | 'done' | 'active' | 'failed'
  const [selectedClipIdx, setSelectedClipIdx] = useState({}) // { [jobId]: index }
  const [copiedId, setCopiedId]             = useState(null)
  const [loading, setLoading]               = useState(false)
  const [toasts, setToasts]                 = useState([])
  const [confirmCancelId, setConfirmCancelId] = useState(null)

  const addToast = useCallback((msg, type = 'info') => {
    const id = Date.now() + Math.random()
    setToasts(prev => [...prev, { id, msg, type }])
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
    }, 4200)
  }, [])

  // ── Fetch Authorized Channels ─────────────────────────────────
  const fetchChannels = useCallback(async () => {
    setChannelsLoading(true)
    try {
      const { data } = await api.get('/channels/')
      if (Array.isArray(data)) setAuthorizedChannels(data)
    } catch {
      // Silencioso se rota ainda não estiver montada
    } finally {
      setChannelsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchChannels()
  }, [fetchChannels])

  const handleAddChannel = async (e) => {
    e.preventDefault()
    if (!newChanName.trim() && !newChanUrl.trim()) {
      addToast('Informe o nome ou link do canal.', 'warn')
      return
    }
    setAddingChannel(true)
    try {
      await api.post('/channels/', {
        name: newChanName.trim() || 'Novo Canal',
        channel_url: newChanUrl.trim() || null,
        min_delay_hours: Number(newChanDelay) || 0,
        policy_notes: newChanNotes.trim() || null,
      })
      addToast('Canal adicionado à Whitelist!', 'success')
      setNewChanName('')
      setNewChanUrl('')
      setNewChanNotes('')
      fetchChannels()
    } catch (err) {
      addToast(err?.response?.data?.detail || 'Erro ao cadastrar canal.', 'error')
    } finally {
      setAddingChannel(false)
    }
  }

  const handleToggleChannel = async (channel) => {
    try {
      await api.patch(`/channels/${channel.id}`, { is_active: !channel.is_active })
      fetchChannels()
      addToast(`Canal ${!channel.is_active ? 'ativado' : 'desativado'}.`, 'info')
    } catch {
      addToast('Erro ao atualizar status do canal.', 'error')
    }
  }

  const handleDeleteChannel = async (channelId) => {
    try {
      await api.delete(`/channels/${channelId}`)
      fetchChannels()
      addToast('Canal removido da Whitelist.', 'info')
    } catch {
      addToast('Erro ao remover canal.', 'error')
    }
  }

  const handlePublishJob = async (jobId) => {
    setActionLoadingId(jobId)
    try {
      const { data } = await api.post(`/jobs/${jobId}/publish`)
      addToast('🚀 Publicação aprovada e iniciada!', 'success')
      setJobs(prev => prev.map(j => j.job_id === jobId ? data : j))
    } catch (err) {
      addToast(err?.response?.data?.detail || 'Erro ao publicar job.', 'error')
    } finally {
      setActionLoadingId(null)
    }
  }

  const handleRejectJob = async (jobId) => {
    try {
      const { data } = await api.post(`/jobs/${jobId}/reject`)
      addToast('Job marcado como rejeitado.', 'info')
      setJobs(prev => prev.map(j => j.job_id === jobId ? data : j))
    } catch {
      addToast('Erro ao rejeitar job.', 'error')
    }
  }

  // ── Apply Smart Presets ───────────────────────────────────────
  const applyPreset = (presetId) => {
    setActivePreset(presetId)
    if (presetId === 'viral_ai') {
      setTab('highlights')
      setAspectMode('fill')
      setSubStyle('karaoke')
      setEnableHook(true)
      setMaxClipDuration(60)
      setSplitLongClips(true)
      setAutoClips(true)
      setJumpCut(true)
      setShowAdvanced(false)
    } else if (presetId === 'series_parts') {
      setTab('sequential')
      setAspectMode('fill')
      setSubStyle('karaoke')
      setEnableHook(true)
      setParts(60)
      setMaxSeqParts(0)
      setShowAdvanced(false)
    } else if (presetId === 'custom') {
      setShowAdvanced(true)
    }
  }

  // ── Load Initial Jobs History ─────────────────────────────────
  const fetchJobs = useCallback(async (silent = false) => {
    if (!silent) setJobsLoading(true)
    try {
      const { data } = await api.get('/jobs/?limit=20')
      if (Array.isArray(data)) {
        setJobs(data)
      }
    } catch {
      // Silencioso no polling
    } finally {
      if (!silent) setJobsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchJobs(false)
  }, [fetchJobs])

  // ── Poll Active Jobs ──────────────────────────────────────────
  const pollJobs = useCallback(async () => {
    const active = jobs.filter(j => !['done', 'failed', 'cancelled'].includes(j.status))
    if (!active.length) return
    try {
      const updated = await Promise.all(
        active.map(j => api.get(`/jobs/${j.job_id}`).then(r => r.data).catch(() => j))
      )
      setJobs(prev => prev.map(j => {
        const next = updated.find(u => u.job_id === j.job_id)
        if (next && j.status !== 'done' && next.status === 'done') {
          addToast('🎉 Corte concluído e pronto na galeria!', 'success')
        } else if (next && j.status !== 'failed' && next.status === 'failed') {
          addToast(`Falha no job: ${next.error_message || 'Erro no processamento'}`, 'error')
        }
        return next || j
      }))
    } catch {
      // ignore
    }
  }, [jobs, addToast])

  useEffect(() => {
    const id = setInterval(pollJobs, 3000)
    return () => clearInterval(id)
  }, [pollJobs])

  // ── Helpers ───────────────────────────────────────────────────
  const togglePlatform = (id) => {
    setPlatforms(prev => {
      const exists = prev.includes(id)
      const next = exists ? prev.filter(p => p !== id) : [...prev, id]
      return next.length ? next : ['buffer']
    })
  }

  const handlePasteClipboard = async () => {
    try {
      const text = await navigator.clipboard.readText()
      if (text) {
        setUrl(text.trim())
        addToast('Link colado da área de transferência!', 'success')
      }
    } catch {
      addToast('Use Ctrl+V no campo para colar o link.', 'warn')
    }
  }

  const handleFilePicked = (file) => {
    if (!file) return
    const ext = '.' + (file.name.split('.').pop() || '').toLowerCase()
    if (!['.mp4', '.mov', '.mkv', '.webm'].includes(ext)) {
      addToast('Formato inválido. Envie arquivos MP4, MOV, MKV ou WEBM.', 'error')
      return
    }
    if (file.size > 500 * 1024 * 1024) {
      addToast('O arquivo excede o limite máximo de 500 MB.', 'error')
      return
    }
    setUploadFile(file)
    addToast(`Arquivo "${file.name}" selecionado.`, 'success')
  }

  const copyToClipboard = async (text, id) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedId(id)
      addToast('Copy copiada para a área de transferência!', 'success')
      setTimeout(() => setCopiedId(null), 2000)
    } catch {
      addToast('Não foi possível copiar automaticamente.', 'error')
    }
  }

  // ── Submit Job (Link or File Upload) ──────────────────────────
  const submit = async () => {
    if (inputMode === 'link' && !url.trim()) {
      addToast('Cole uma URL do YouTube ou Google Drive para continuar.', 'warn')
      return
    }
    if (inputMode === 'upload' && !uploadFile) {
      addToast('Selecione um arquivo de vídeo (.mp4 ou .mov) para enviar.', 'warn')
      return
    }
    if (destinationMode === 'publish' && publishMode === 'scheduled' && !dueAt) {
      addToast('Escolha a data e o horário para o agendamento.', 'warn')
      return
    }

    const effectivePlatforms = destinationMode === 'publish' ? platforms : []
    const effectivePubMode = destinationMode === 'publish' ? publishMode : 'shareNow'
    const dueAtIso = (destinationMode === 'publish' && publishMode === 'scheduled' && dueAt)
      ? new Date(dueAt).toISOString()
      : null
    const finalClipsCount = tab === 'highlights'
      ? (autoClips ? 0 : maxClips)
      : maxSeqParts

    setLoading(true)
    setUploadPct(0)

    try {
      let createdJob
      if (inputMode === 'link') {
        const detected = detectSourceFromInput(url)
        const payload = {
          source_type:       detected.type,
          source_url:        url.trim(),
          drive_file_id:     detected.type === 'google_drive' ? url.trim() : null,
          cut_mode:          tab,
          part_duration:     parts,
          max_clip_duration: tab === 'highlights' ? maxClipDuration : parts,
          max_clips:         finalClipsCount,
          split_long_clips:  tab === 'highlights' ? splitLongClips : true,
          jump_cut:          jumpCut,
          platforms:         effectivePlatforms,
          subtitle_style:    subtitleStyle,
          aspect_mode:       aspectMode,
          niche_preset:      nichePreset,
          enable_hook:       enableHook,
          hook_text:         enableHook ? (hookText.trim() || null) : null,
          enable_bgm:        enableBgm,
          speed_boost:       speedBoost,
          enable_headline:   enableHeadline,
          publish_mode:      effectivePubMode,
          due_at:            dueAtIso,
          requires_approval: requiresApproval,
        }
        const { data } = await api.post('/jobs/', payload)
        createdJob = data
        setUrl('')
      } else {
        const formData = new FormData()
        formData.append('file', uploadFile)
        formData.append('cut_mode', tab)
        formData.append('part_duration', String(parts))
        formData.append('max_clip_duration', String(tab === 'highlights' ? maxClipDuration : parts))
        formData.append('max_clips', String(finalClipsCount))
        formData.append('split_long_clips', String(tab === 'highlights' ? splitLongClips : true))
        formData.append('jump_cut', String(jumpCut))
        formData.append('platforms', JSON.stringify(effectivePlatforms))
        formData.append('subtitle_style', subtitleStyle)
        formData.append('aspect_mode', aspectMode)
        formData.append('niche_preset', nichePreset)
        formData.append('enable_hook', String(enableHook))
        formData.append('enable_bgm', String(enableBgm))
        formData.append('speed_boost', String(speedBoost))
        formData.append('enable_headline', String(enableHeadline))
        formData.append('requires_approval', String(requiresApproval))
        if (enableHook && hookText.trim()) {
          formData.append('hook_text', hookText.trim())
        }
        formData.append('publish_mode', effectivePubMode)
        if (dueAtIso) {
          formData.append('due_at', dueAtIso)
        }

        const { data } = await api.post('/jobs/upload', formData, {
          onUploadProgress: (evt) => {
            if (evt.total) {
              setUploadPct(Math.round((evt.loaded * 100) / evt.total))
            }
          }
        })
        createdJob = data
        setUploadFile(null)
      }

      setJobs(prev => [createdJob, ...prev.filter(j => j.job_id !== createdJob.job_id)])
      addToast('🚀 Processamento iniciado! Acompanhe o progresso ao vivo.', 'success')
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Falha na comunicação com o servidor.'
      addToast(`Erro: ${msg}`, 'error')
    } finally {
      setLoading(false)
      setUploadPct(0)
    }
  }

  // ── Cancel Job ────────────────────────────────────────────────
  const cancelJob = async (id) => {
    try {
      await api.post(`/jobs/${id}/cancel`)
      setJobs(prev => prev.map(j => j.job_id === id
        ? { ...j, status: 'cancelled', error_message: 'Cancelado pelo usuário' }
        : j
      ))
      setConfirmCancelId(null)
      addToast('Processamento interrompido.', 'warn')
    } catch (err) {
      addToast('Erro ao cancelar: ' + (err.response?.data?.detail || err.message), 'error')
    }
  }

  const detectedSource = detectSourceFromInput(url)
  const activeRunningJob = jobs.find(j => !['done', 'failed', 'cancelled'].includes(j.status))

  const filteredJobs = jobs.filter(j => {
    if (jobFilter === 'done') return j.status === 'done'
    if (jobFilter === 'active') return !['done', 'failed', 'cancelled'].includes(j.status)
    if (jobFilter === 'failed') return ['failed', 'cancelled'].includes(j.status)
    return true
  })

  const canSubmit = !loading && (
    (inputMode === 'link' && url.trim().length > 0) ||
    (inputMode === 'upload' && !!uploadFile)
  )

  return (
    <div className="page">
      {/* ── Toast Container ─────────────────────────────────────── */}
      <div className="toast-container">
        {toasts.map(t => (
          <div key={t.id} className={`toast ${t.type}`}>
            <span>{t.msg}</span>
          </div>
        ))}
      </div>

      <div className="studio-container">
        {/* ── Studio Hero Header ────────────────────────────────── */}
        <div className="studio-hero">
          <div>
            <h1 className="section-title">Studio de Cortes Inteligentes</h1>
            <p className="section-sub">
              Transforme vídeos longos em Shorts, Reels e TikToks virais em 3 passos simples.
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn btn-outline btn-sm"
              onClick={() => setShowChannelsModal(true)}
              style={{ gap: 6, borderColor: 'rgba(59,130,246,0.3)', color: '#38bdf8' }}
            >
              <ShieldCheck size={14} /> Canais Autorizados ({authorizedChannels.length})
            </button>
            <span className="badge badge-info">
              <Zap size={12} /> IA Multimodal + Whisper
            </span>
            <span className="badge badge-muted">
              <Smartphone size={12} /> Render 9:16 Nativo
            </span>
          </div>
        </div>

        {/* ── 2-Column Studio Grid ──────────────────────────────── */}
        <div className="studio-grid">

          {/* ════════════════════════════════════════════════════════
              COLUNA ESQUERDA: WORKFLOW EM 3 PASSOS
             ════════════════════════════════════════════════════════ */}
          <div>

            {/* ── PASSO 1: FONTE DO VÍDEO ───────────────────────── */}
            <section className="step-block">
              <div className="step-header">
                <div className="step-title-wrap">
                  <span className="step-number">1</span>
                  <div>
                    <h2 className="step-title">Fonte do Vídeo</h2>
                    <p className="step-sub">Cole um link do YouTube / Google Drive ou envie um arquivo MP4/MOV</p>
                  </div>
                </div>

                {/* Switcher Link vs Upload */}
                <div className="tabs" style={{ width: 250 }}>
                  <button
                    type="button"
                    className={`tab ${inputMode === 'link' ? 'active' : ''}`}
                    onClick={() => setInputMode('link')}
                  >
                    <Link2 size={14} /> Link
                  </button>
                  <button
                    type="button"
                    className={`tab ${inputMode === 'upload' ? 'active' : ''}`}
                    onClick={() => setInputMode('upload')}
                  >
                    <Upload size={14} /> Upload
                  </button>
                </div>
              </div>

              {inputMode === 'link' ? (
                <div className="input-group">
                  <div className="label">
                    <span>URL do YouTube ou Link/ID do Google Drive</span>
                    {url.trim() && (
                      <span className="badge badge-info" style={{ fontSize: '.68rem', padding: '2px 8px' }}>
                        {detectedSource.icon} {detectedSource.label}
                      </span>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <div className="input-wrapper" style={{ flex: 1 }}>
                      <input
                        className="input"
                        placeholder="https://youtube.com/watch?v=... ou https://drive.google.com/file/d/..."
                        value={url}
                        onChange={e => setUrl(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && canSubmit && submit()}
                        style={{ paddingRight: url ? 36 : 14 }}
                      />
                      {url && (
                        <button
                          type="button"
                          onClick={() => setUrl('')}
                          title="Limpar campo"
                          style={{
                            position: 'absolute', right: 10, background: 'transparent',
                            border: 'none', color: 'var(--text-dim)', cursor: 'pointer', fontSize: '.9rem'
                          }}
                        >
                          ✕
                        </button>
                      )}
                    </div>
                    <button
                      type="button"
                      className="btn btn-outline"
                      onClick={handlePasteClipboard}
                      title="Colar da área de transferência"
                    >
                      <ClipboardPaste size={15} />
                      Colar
                    </button>
                  </div>
                </div>
              ) : (
                <div>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="video/mp4,video/quicktime,video/x-matroska,video/webm,.mp4,.mov,.mkv,.webm"
                    style={{ display: 'none' }}
                    onChange={e => handleFilePicked(e.target.files?.[0])}
                  />
                  <div
                    className={`dropzone ${isDragging ? 'dragover' : ''}`}
                    onClick={() => fileInputRef.current?.click()}
                    onDragOver={e => { e.preventDefault(); setIsDragging(true) }}
                    onDragLeave={() => setIsDragging(false)}
                    onDrop={e => {
                      e.preventDefault()
                      setIsDragging(false)
                      handleFilePicked(e.dataTransfer.files?.[0])
                    }}
                  >
                    <div className="dropzone-icon">
                      <Upload size={22} />
                    </div>
                    {uploadFile ? (
                      <>
                        <div style={{ fontWeight: 700, fontSize: '.92rem', color: '#34d399' }}>
                          ✅ {uploadFile.name}
                        </div>
                        <div style={{ fontSize: '.76rem', color: 'var(--text-muted)' }}>
                          {(uploadFile.size / (1024 * 1024)).toFixed(1)} MB • Clique para trocar arquivo
                        </div>
                      </>
                    ) : (
                      <>
                        <div style={{ fontWeight: 700, fontSize: '.9rem' }}>
                          Arraste seu vídeo aqui ou clique para selecionar
                        </div>
                        <div style={{ fontSize: '.76rem', color: 'var(--text-dim)' }}>
                          Suporta MP4, MOV, MKV e WEBM até 500 MB
                        </div>
                      </>
                    )}
                  </div>
                  {loading && uploadPct > 0 && (
                    <div style={{ marginTop: 10 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '.75rem', marginBottom: 4 }}>
                        <span>Enviando arquivo para o Studio…</span>
                        <b>{uploadPct}%</b>
                      </div>
                      <div className="progress-track">
                        <div className="progress-bar" style={{ width: `${uploadPct}%` }} />
                      </div>
                    </div>
                  )}
                </div>
              )}
            </section>

            {/* ── PASSO 2: ESTILO & INTELIGÊNCIA DE CORTE ────────── */}
            <section className="step-block">
              <div className="step-header">
                <div className="step-title-wrap">
                  <span className="step-number">2</span>
                  <div>
                    <h2 className="step-title">Estilo & Inteligência de Corte</h2>
                    <p className="step-sub">Escolha um preset de 1 clique ou personalize cada detalhe</p>
                  </div>
                </div>
                <button
                  type="button"
                  className={`btn btn-sm ${showAdvanced ? 'btn-primary' : 'btn-outline'}`}
                  onClick={() => setShowAdvanced(!showAdvanced)}
                >
                  <Sliders size={13} />
                  {showAdvanced ? 'Ocultar Ajustes Finos' : 'Ajustes Finos'}
                </button>
              </div>

              {/* Presets Rápidos de 1 Clique */}
              <div className="preset-grid">
                <button
                  type="button"
                  className={`choice-card ${activePreset === 'viral_ai' ? 'selected' : ''}`}
                  onClick={() => applyPreset('viral_ai')}
                >
                  <div className="choice-card-top">
                    <span>🔥 Viral IA</span>
                    <span className="badge badge-info" style={{ fontSize: '.62rem', padding: '1px 6px' }}>Recomendado</span>
                  </div>
                  <div className="choice-card-desc">
                    IA acha os clímax (60s), Jump Cut ativo, legenda Karaokê e gancho no topo.
                  </div>
                </button>

                <button
                  type="button"
                  className={`choice-card ${activePreset === 'series_parts' ? 'selected' : ''}`}
                  onClick={() => applyPreset('series_parts')}
                >
                  <div className="choice-card-top">
                    <span>✂️ Série em Partes</span>
                  </div>
                  <div className="choice-card-desc">
                    Divide o vídeo em partes sequenciais (Parte 1, Parte 2…) com corte na pausa de voz.
                  </div>
                </button>

                <button
                  type="button"
                  className={`choice-card ${activePreset === 'custom' ? 'selected' : ''}`}
                  onClick={() => applyPreset('custom')}
                >
                  <div className="choice-card-top">
                    <span>🎛️ Studio Pro</span>
                  </div>
                  <div className="choice-card-desc">
                    Controle total sobre duração (30s–3m), enquadramento Blur/Fill e número de cortes.
                  </div>
                </button>
              </div>

              {/* Seletor de Nicho / Tom IA */}
              <div style={{ marginBottom: 16 }}>
                <div className="label" style={{ marginBottom: 6 }}>
                  <span>Nicho / Tom do Conteúdo</span>
                  <span style={{ fontSize: '.72rem', color: 'var(--text-dim)' }}>Direciona a IA para o clímax e a copy ideais</span>
                </div>
                <div className="choice-grid-3">
                  {[
                    { id: 'emotional', icon: '🤝', title: 'Ajuda / Emoção', desc: 'Caridade, superação, lágrimas e reflexão (John Leitão, Valentim)' },
                    { id: 'debate',    icon: '🎙️', title: 'Debate / Futebol', desc: 'Mesas-redondas, polêmicas, confrontos e bastidores' },
                    { id: 'general',   icon: '⚡', title: 'Geral / Variedades', desc: 'Clímax dinâmico, revelações e curiosidades de alto impacto' },
                  ].map(n => (
                    <button
                      key={n.id}
                      type="button"
                      className={`choice-card ${nichePreset === n.id ? 'selected' : ''}`}
                      onClick={() => setNichePreset(n.id)}
                      style={{ padding: '10px 12px' }}
                    >
                      <div className="choice-card-top" style={{ fontSize: '.84rem' }}>
                        <span>{n.icon} {n.title}</span>
                      </div>
                      <div className="choice-card-desc" style={{ fontSize: '.72rem' }}>
                        {n.desc}
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Controles Visuais Principais (Modo + Enquadramento) */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 14, marginBottom: 16 }}>
                {/* Modo de Corte */}
                <div>
                  <div className="label" style={{ marginBottom: 6 }}>Modo de Corte</div>
                  <div className="tabs">
                    <button
                      type="button"
                      className={`tab ${tab === 'highlights' ? 'active' : ''}`}
                      onClick={() => { setTab('highlights'); setActivePreset('custom') }}
                    >
                      <Sparkles size={13} /> Melhores Momentos
                    </button>
                    <button
                      type="button"
                      className={`tab ${tab === 'sequential' ? 'active' : ''}`}
                      onClick={() => { setTab('sequential'); setActivePreset('custom') }}
                    >
                      <Scissors size={13} /> Dividir Partes
                    </button>
                  </div>
                </div>

                {/* Enquadramento 9:16 */}
                <div>
                  <div className="label" style={{ marginBottom: 6 }}>Enquadramento 9:16</div>
                  <div className="tabs">
                    <button
                      type="button"
                      className={`tab ${aspectMode === 'fill' ? 'active' : ''}`}
                      onClick={() => setAspectMode('fill')}
                    >
                      📱 Tela Cheia
                    </button>
                    <button
                      type="button"
                      className={`tab ${aspectMode === 'split' ? 'active' : ''}`}
                      onClick={() => setAspectMode('split')}
                    >
                      👥 Split Podcast
                    </button>
                    <button
                      type="button"
                      className={`tab ${aspectMode === 'blur' ? 'active' : ''}`}
                      onClick={() => setAspectMode('blur')}
                    >
                      🌫️ Blur
                    </button>
                  </div>
                </div>
              </div>

              {/* Estilo de Legenda */}
              <div style={{ marginBottom: 16 }}>
                <div className="label" style={{ marginBottom: 6 }}>
                  <span>Legendas Dinâmicas no Vídeo</span>
                  <span style={{ fontSize: '.72rem', color: 'var(--text-dim)' }}>Veja prévia no celular ao lado 👉</span>
                </div>
                <div className="choice-grid-3">
                  {[
                    { v: 'karaoke', l: '🎤 Karaokê Viral', d: 'Palavra ativa destacada em amarelo vibrante' },
                    { v: 'simple',  l: '💬 Clássica Simples', d: 'Legenda limpa com caixa escura translúcida' },
                    { v: 'none',    l: '🚫 Sem Legenda', d: 'Vídeo limpo apenas com o áudio original' },
                  ].map(({ v, l, d }) => (
                    <button
                      key={v}
                      type="button"
                      className={`choice-card ${subtitleStyle === v ? 'selected' : ''}`}
                      onClick={() => setSubStyle(v)}
                    >
                      <div className="choice-card-top">{l}</div>
                      <div className="choice-card-desc">{d}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Gancho Visual de Retenção (primeiros 5s) */}
              <div style={{
                padding: '14px 16px',
                background: 'rgba(245, 158, 11, 0.05)',
                border: '1px solid rgba(245, 158, 11, 0.22)',
                borderRadius: 12
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: enableHook ? 10 : 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Flame size={16} style={{ color: '#f59e0b' }} />
                    <div>
                      <div style={{ fontSize: '.85rem', fontWeight: 700, color: '#fbbf24' }}>
                        Gancho de Retenção nos Primeiros 5 Segundos
                      </div>
                      <div style={{ fontSize: '.73rem', color: 'var(--text-muted)' }}>
                        Banner impactante no topo para prender atenção imediata no scroll
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    className={`btn btn-xs ${enableHook ? 'btn-primary' : 'btn-outline'}`}
                    onClick={() => setEnableHook(!enableHook)}
                  >
                    {enableHook ? 'Ativado 🔥' : 'Desativado'}
                  </button>
                </div>

                {enableHook && (
                  <div>
                    <input
                      className="input"
                      style={{ fontSize: '.84rem', padding: '9px 12px', marginBottom: 8 }}
                      placeholder="Deixe em branco para a IA criar o gancho ideal ou digite aqui (ex: NÃO FAÇA ISSO 👀)"
                      value={hookText}
                      onChange={e => setHookText(e.target.value)}
                    />
                    <div className="pill-row">
                      {HOOK_SUGGESTIONS.map(s => (
                        <button
                          key={s.label}
                          type="button"
                          className={`pill ${hookText === s.value ? 'active' : ''}`}
                          style={{ fontSize: '.71rem', padding: '4px 9px' }}
                          onClick={() => setHookText(s.value)}
                        >
                          {s.label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* ── Tratamentos Audiovisuais Fair Use & Anti-Content ID (Sprint 2) ── */}
              <div style={{
                marginTop: 16,
                padding: '12px 14px',
                background: 'rgba(234,179,8,0.05)',
                borderRadius: 10,
                border: '1px solid rgba(234,179,8,0.2)',
                display: 'flex',
                flexDirection: 'column',
                gap: 10
              }}>
                <div style={{ fontSize: '.84rem', fontWeight: 600, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Shield size={15} color="#eab308" /> Proteção Anti-Content ID & Fair Use
                </div>
                <div className="choice-grid-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 8 }}>
                  <div style={{ padding: '8px 10px', background: 'var(--surface-2)', borderRadius: 8, border: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontSize: '.78rem', fontWeight: 700 }}>Trilha Neutra (BGM) 🎵</div>
                      <div style={{ fontSize: '.68rem', color: 'var(--text-muted)' }}>Música de fundo sutil</div>
                    </div>
                    <button
                      type="button"
                      className={`btn btn-xs ${enableBgm ? 'btn-primary' : 'btn-outline'}`}
                      onClick={() => setEnableBgm(!enableBgm)}
                    >
                      {enableBgm ? 'Ativo' : 'Off'}
                    </button>
                  </div>

                  <div style={{ padding: '8px 10px', background: 'var(--surface-2)', borderRadius: 8, border: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontSize: '.78rem', fontWeight: 700 }}>Aceleração 1.03x ⚡</div>
                      <div style={{ fontSize: '.68rem', color: 'var(--text-muted)' }}>Altera pitch & tempo</div>
                    </div>
                    <button
                      type="button"
                      className={`btn btn-xs ${speedBoost > 1.0 ? 'btn-primary' : 'btn-outline'}`}
                      onClick={() => setSpeedBoost(speedBoost > 1.0 ? 1.0 : 1.03)}
                    >
                      {speedBoost > 1.0 ? '1.03x' : '1.0x'}
                    </button>
                  </div>

                  <div style={{ padding: '8px 10px', background: 'var(--surface-2)', borderRadius: 8, border: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontSize: '.78rem', fontWeight: 700 }}>Headline Superior 🏷️</div>
                      <div style={{ fontSize: '.68rem', color: 'var(--text-muted)' }}>Banner persistente</div>
                    </div>
                    <button
                      type="button"
                      className={`btn btn-xs ${enableHeadline ? 'btn-primary' : 'btn-outline'}`}
                      onClick={() => setEnableHeadline(!enableHeadline)}
                    >
                      {enableHeadline ? 'Ativo' : 'Off'}
                    </button>
                  </div>
                </div>
              </div>

              {/* Painel de Ajustes Finos de Duração, Partes e Jump Cut */}
              {(showAdvanced || activePreset !== 'viral_ai') && (
                <div style={{
                  marginTop: 16,
                  paddingTop: 16,
                  borderTop: '1px solid var(--border)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 14
                }}>
                  {tab === 'highlights' ? (
                    <>
                      <div>
                        <div className="label" style={{ marginBottom: 8 }}>
                          <span>Duração Alvo do Clipe: <b style={{ color: 'var(--primary-lit)' }}>{maxClipDuration}s</b></span>
                          <span style={{ fontSize: '.72rem', color: 'var(--text-dim)' }}>
                            {maxClipDuration <= 60 ? '⚡ Ideal para Shorts/Reels' : '🎬 História estendida'}
                          </span>
                        </div>
                        <div className="pill-row">
                          {[
                            { s: 30, l: '30s (Rápido)' },
                            { s: 45, l: '45s (Dinâmico)' },
                            { s: 60, l: '60s (Padrão Viral)' },
                            { s: 90, l: '90s (Reels)' },
                            { s: 120, l: '2 min (Narrativa)' },
                            { s: 180, l: '3 min (Completo)' },
                          ].map(({ s, l }) => (
                            <button
                              key={s}
                              type="button"
                              className={`pill ${maxClipDuration === s ? 'active' : ''}`}
                              onClick={() => setMaxClipDuration(s)}
                            >
                              {l}
                            </button>
                          ))}
                        </div>
                      </div>

                      {maxClipDuration > 60 && (
                        <div style={{
                          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                          padding: '10px 12px', background: 'var(--surface-2)', borderRadius: 10, border: '1px solid var(--border)'
                        }}>
                          <div>
                            <div style={{ fontSize: '.82rem', fontWeight: 700 }}>Dividir em partes se passar de 60s</div>
                            <div style={{ fontSize: '.72rem', color: 'var(--text-muted)' }}>
                              {splitLongClips
                                ? 'Gera Parte 1, Parte 2… cortando em pausas naturais da fala (compatível com Shorts)'
                                : 'Mantém 1 vídeo longo único sem fatiar'}
                            </div>
                          </div>
                          <button
                            type="button"
                            className={`btn btn-xs ${splitLongClips ? 'btn-primary' : 'btn-outline'}`}
                            onClick={() => setSplitLongClips(!splitLongClips)}
                          >
                            {splitLongClips ? 'Dividir ✂️' : 'Vídeo Único 🎬'}
                          </button>
                        </div>
                      )}

                      <div className="choice-grid-2">
                        {/* Quantidade de clipes */}
                        <div style={{ padding: '10px 12px', background: 'var(--surface-2)', borderRadius: 10, border: '1px solid var(--border)' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div>
                              <div style={{ fontSize: '.8rem', fontWeight: 700 }}>Quantidade de Clipes</div>
                              <div style={{ fontSize: '.71rem', color: 'var(--text-muted)' }}>
                                {autoClips ? 'IA gera todos os clímax (nota ≥ 7)' : `Limite fixo: ${maxClips} clipe(s)`}
                              </div>
                            </div>
                            <button
                              type="button"
                              className={`btn btn-xs ${autoClips ? 'btn-primary' : 'btn-outline'}`}
                              onClick={() => setAutoClips(!autoClips)}
                            >
                              {autoClips ? 'IA Decide 🤖' : 'Manual ⚙️'}
                            </button>
                          </div>
                          {!autoClips && (
                            <div style={{ marginTop: 8 }}>
                              <input
                                type="range"
                                min={1}
                                max={10}
                                value={maxClips}
                                onChange={e => setMaxClips(+e.target.value)}
                                style={{ width: '100%', accentColor: 'var(--primary)' }}
                              />
                            </div>
                          )}
                        </div>

                        {/* Jump Cut Inteligente */}
                        <div style={{ padding: '10px 12px', background: 'var(--surface-2)', borderRadius: 10, border: '1px solid var(--border)' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div>
                              <div style={{ fontSize: '.8rem', fontWeight: 700 }}>Jump Cut Inteligente ⚡</div>
                              <div style={{ fontSize: '.71rem', color: 'var(--text-muted)' }}>
                                {jumpCut ? 'Remove silêncios (>0.5s) para retenção' : 'Mantém pausas originais'}
                              </div>
                            </div>
                            <button
                              type="button"
                              className={`btn btn-xs ${jumpCut ? 'btn-primary' : 'btn-outline'}`}
                              onClick={() => setJumpCut(!jumpCut)}
                            >
                              {jumpCut ? 'Ativo ⚡' : 'Off'}
                            </button>
                          </div>
                        </div>
                      </div>
                    </>
                  ) : (
                    <>
                      <div>
                        <div className="label" style={{ marginBottom: 8 }}>
                          <span>Duração de cada parte sequencial: <b style={{ color: 'var(--primary-lit)' }}>{parts}s</b></span>
                        </div>
                        <div className="pill-row">
                          {[30, 45, 60, 90, 120, 180].map(s => (
                            <button
                              key={s}
                              type="button"
                              className={`pill ${parts === s ? 'active' : ''}`}
                              onClick={() => setParts(s)}
                            >
                              {s}s
                            </button>
                          ))}
                        </div>
                      </div>

                      <div>
                        <div className="label" style={{ marginBottom: 8 }}>
                          <span>Quantidade de Partes a Gerar</span>
                          <span style={{ fontSize: '.72rem', color: 'var(--text-dim)' }}>Corte inteligente nas pausas de voz</span>
                        </div>
                        <div className="pill-row">
                          {[
                            { v: 0, l: '🎬 Vídeo Inteiro (Automático)' },
                            { v: 2, l: '2 partes' },
                            { v: 3, l: '3 partes' },
                            { v: 5, l: '5 partes' },
                            { v: 10, l: '10 partes' },
                            { v: 20, l: '20 partes' },
                            { v: 50, l: 'Até 50 partes' },
                          ].map(({ v, l }) => (
                            <button
                              key={v}
                              type="button"
                              className={`pill ${maxSeqParts === v ? 'active' : ''}`}
                              onClick={() => setMaxSeqParts(v)}
                            >
                              {l}
                            </button>
                          ))}
                        </div>
                      </div>
                    </>
                  )}
                </div>
              )}
            </section>

            {/* ── PASSO 3: DESTINO & AGENDAMENTO ────────────────── */}
            <section className="step-block">
              <div className="step-header">
                <div className="step-title-wrap">
                  <span className="step-number">3</span>
                  <div>
                    <h2 className="step-title">Destino & Publicação</h2>
                    <p className="step-sub">Publique automaticamente nas redes ou gere apenas para download local</p>
                  </div>
                </div>
              </div>

              {/* Publicar vs Apenas Baixar */}
              <div className="choice-grid-2" style={{ marginBottom: destinationMode === 'publish' ? 16 : 0 }}>
                <button
                  type="button"
                  className={`choice-card ${destinationMode === 'publish' ? 'selected' : ''}`}
                  onClick={() => setDestMode('publish')}
                >
                  <div className="choice-card-top">
                    <span>🚀 Publicar nas Redes</span>
                    <span className="badge badge-success" style={{ fontSize: '.62rem', padding: '1px 6px' }}>Automático</span>
                  </div>
                  <div className="choice-card-desc">
                    Envia os cortes prontos com título e copy viral para o Buffer Gateway ou redes conectadas.
                  </div>
                </button>

                <button
                  type="button"
                  className={`choice-card ${destinationMode === 'download_only' ? 'selected' : ''}`}
                  onClick={() => setDestMode('download_only')}
                >
                  <div className="choice-card-top">
                    <span>📥 Apenas Gerar & Baixar</span>
                  </div>
                  <div className="choice-card-desc">
                    Apenas renderiza os vídeos 9:16 para você assistir e baixar aqui na Galeria do Studio.
                  </div>
                </button>
              </div>

              {destinationMode === 'publish' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  {/* Seleção de Canais */}
                  <div>
                    <div className="label" style={{ marginBottom: 6 }}>Canais de Destino</div>
                    <div className="pill-row">
                      {PLATFORMS.map(({ id, label, emoji }) => (
                        <button
                          key={id}
                          type="button"
                          className={`pill ${platforms.includes(id) ? 'active' : ''}`}
                          onClick={() => togglePlatform(id)}
                        >
                          {emoji} {label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Modo de Disparo */}
                  <div>
                    <div className="label" style={{ marginBottom: 6 }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                        <Clock size={13} /> Quando Publicar no Buffer
                      </span>
                    </div>
                    <div className="choice-grid-3">
                      {[
                        { id: 'shareNow',   l: '⚡ Imediato',      d: 'Publica assim que o corte finalizar' },
                        { id: 'addToQueue', l: '📥 Fila do Buffer', d: 'Entra no próximo horário da grade' },
                        { id: 'scheduled',  l: '📅 Agendado',      d: 'Data e hora exatas programadas' },
                      ].map(({ id, l, d }) => (
                        <button
                          key={id}
                          type="button"
                          className={`choice-card ${publishMode === id ? 'selected' : ''}`}
                          onClick={() => setPublishMode(id)}
                        >
                          <div className="choice-card-top">{l}</div>
                          <div className="choice-card-desc">{d}</div>
                        </button>
                      ))}
                    </div>
                  </div>

                  {publishMode === 'scheduled' && (
                    <div style={{
                      padding: '12px 14px',
                      background: 'var(--surface-2)',
                      borderRadius: 10,
                      border: '1px solid var(--border)'
                    }}>
                      <label className="label" style={{ marginBottom: 6 }}>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <Calendar size={14} /> Data e Hora do Disparo
                        </span>
                        <span style={{ fontSize: '.7rem', color: 'var(--text-dim)' }}>Convertido automaticamente para UTC</span>
                      </label>
                      <input
                        type="datetime-local"
                        className="input"
                        style={{ fontSize: '.86rem', padding: '9px 12px' }}
                        value={dueAt}
                        min={new Date().toISOString().slice(0, 16)}
                        onChange={e => setDueAt(e.target.value)}
                      />
                    </div>
                  )}
                </div>
              )}

              {/* ── Trava de Segurança: Aprovação Humana ── */}
              <div style={{
                marginTop: 14,
                padding: '11px 14px',
                background: 'rgba(56,189,248,0.06)',
                borderRadius: 10,
                border: '1px solid rgba(56,189,248,0.2)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 12
              }}>
                <div>
                  <div style={{ fontSize: '.84rem', fontWeight: 600, color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <ShieldCheck size={15} color="#38bdf8" /> Modo Aprovação Prévia (Human-in-the-Loop)
                  </div>
                  <div style={{ fontSize: '.74rem', color: 'var(--text-dim)', marginTop: 2 }}>
                    Renderiza os cortes e aguarda sua validação na galeria antes de publicar nas redes sociais.
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={requiresApproval}
                  onChange={e => setRequiresApproval(e.target.checked)}
                  style={{ width: 18, height: 18, accentColor: '#38bdf8', cursor: 'pointer' }}
                />
              </div>
            </section>

            {/* ── CTA PRINCIPAL ─────────────────────────────────── */}
            <button
              type="button"
              className="btn btn-cta"
              onClick={submit}
              disabled={!canSubmit}
            >
              {loading ? (
                <>
                  <RefreshCw size={18} style={{ animation: 'spin 1.2s linear infinite' }} />
                  {uploadPct > 0 ? `Enviando vídeo (${uploadPct}%)…` : 'Iniciando Pipeline IA…'}
                </>
              ) : (
                <>
                  <Send size={18} />
                  {destinationMode === 'publish' ? 'Processar & Publicar Cortes 9:16' : 'Processar & Gerar Cortes 9:16'}
                </>
              )}
            </button>
          </div>

          {/* ════════════════════════════════════════════════════════
              COLUNA DIREITA: LIVE 9:16 PREVIEW & ACTIVE PIPELINE
             ════════════════════════════════════════════════════════ */}
          <aside className="studio-sidebar">

            {/* ── Card 1: Simulador Smartphone 9:16 Ao Vivo ──────── */}
            <div className="phone-preview-card">
              <div style={{
                width: '100%', display: 'flex', alignItems: 'center',
                justifyContent: 'space-between', marginBottom: 12
              }}>
                <span style={{ fontSize: '.82rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Smartphone size={14} style={{ color: 'var(--primary-lit)' }} />
                  Preview 9:16 ao Vivo
                </span>
                <span className="badge badge-muted" style={{ fontSize: '.66rem' }}>
                  {aspectMode === 'fill' ? 'Tela Cheia' : aspectMode === 'split' ? '👥 Split Podcast' : '🌫️ Fundo Blur'}
                </span>
              </div>

              <div className={`phone-frame ${aspectMode === 'blur' ? 'phone-blur-bars' : ''} ${aspectMode === 'split' ? 'phone-split-frame' : ''}`}>
                <div className="phone-scene-bg" />

                <div>
                  <div className="phone-notch" />
                  {enableHeadline && (
                    <div style={{
                      background: 'rgba(0,0,0,0.88)',
                      color: '#fff',
                      fontSize: '.58rem',
                      fontWeight: 800,
                      padding: '3px 6px',
                      textAlign: 'center',
                      borderBottom: '2px solid #eab308',
                      letterSpacing: '.3px',
                      textTransform: 'uppercase'
                    }}>
                      TÍTULO DO CORTE 🔥
                    </div>
                  )}
                  {enableHook ? (
                    <div className="phone-hook-banner">
                      {hookText.trim() || '🔥 GANCHO IA (PRIMEIROS 5S)'}
                    </div>
                  ) : (
                    <div style={{ height: enableHeadline ? 6 : 24 }} />
                  )}
                </div>

                <div className="phone-center-subject">
                  <Film size={28} style={{ opacity: 0.65, color: 'var(--primary-lit)' }} />
                  <div style={{ fontSize: '.7rem', fontWeight: 700 }}>
                    {tab === 'highlights' ? 'Clímax IA Detectado' : 'Corte Sequencial'}
                  </div>
                  <div style={{ fontSize: '.63rem', color: 'var(--text-muted)' }}>
                    {tab === 'highlights' ? `${maxClipDuration}s` : `${parts}s por parte`}
                    {jumpCut && tab === 'highlights' ? ' • Jump Cut ⚡' : ''}
                  </div>
                </div>

                <div className="phone-sub-area">
                  {subtitleStyle === 'karaoke' && (
                    <div className="phone-sub-karaoke">
                      ESSE É O <span className="active-word">SEGREDO</span> VIRAL
                    </div>
                  )}
                  {subtitleStyle === 'simple' && (
                    <div className="phone-sub-simple">
                      Esse é o segredo para reter a audiência até o final
                    </div>
                  )}
                  {subtitleStyle === 'none' && (
                    <div style={{ fontSize: '.65rem', color: 'var(--text-dim)' }}>
                      (Sem legendas sobrepostas)
                    </div>
                  )}
                </div>
              </div>

              {/* Resumo das specs ativas */}
              <div style={{
                width: '100%', marginTop: 14, display: 'flex',
                flexWrap: 'wrap', gap: 6, justifyContent: 'center'
              }}>
                <span className="badge badge-muted">1080×1920</span>
                <span className="badge badge-info" style={{ fontSize: '.64rem' }}>
                  {nichePreset === 'emotional' ? '🤝 Ajuda/Emoção' : nichePreset === 'debate' ? '🎙️ Debate' : '⚡ Geral'}
                </span>
                <span className="badge badge-muted">
                  {subtitleStyle === 'karaoke' ? '🎤 Karaokê' : subtitleStyle === 'simple' ? '💬 Simples' : '🚫 S/ Legenda'}
                </span>
                <span className="badge badge-muted">
                  {destinationMode === 'publish' ? '🚀 Auto-Post' : '📥 Download'}
                </span>
                {enableBgm && <span className="badge badge-warn" style={{ fontSize: '.62rem' }}>🎵 BGM Neutro</span>}
                {speedBoost > 1.0 && <span className="badge badge-info" style={{ fontSize: '.62rem' }}>⚡ 1.03x</span>}
                {enableHeadline && <span className="badge badge-muted" style={{ fontSize: '.62rem' }}>🏷️ Headline</span>}
              </div>
            </div>

            {/* ── Card 2: Rastreador Ao Vivo (quando há job ativo) ── */}
            {activeRunningJob && (
              <div className="card" style={{ padding: 18, borderColor: 'rgba(124, 58, 237, 0.4)' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                  <div>
                    <div style={{ fontSize: '.84rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 6 }}>
                      <RefreshCw size={13} style={{ color: 'var(--primary-lit)', animation: 'spin 2s linear infinite' }} />
                      Pipeline em Execução
                    </div>
                    <code style={{ fontSize: '.7rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                      Job #{activeRunningJob.job_id.slice(0, 8)}
                    </code>
                  </div>
                  <span className={`badge ${(STATUS_META[activeRunningJob.status] || STATUS_META.queued).cls}`}>
                    {(STATUS_META[activeRunningJob.status] || STATUS_META.queued).label}
                  </span>
                </div>

                <div className="progress-track" style={{ marginBottom: 12 }}>
                  <div className="progress-bar" style={{ width: `${PROGRESS[activeRunningJob.status] || 15}%` }} />
                </div>

                <div className="pipeline-stepper">
                  {PIPELINE_STEPS.map(s => {
                    const curStep = (STATUS_META[activeRunningJob.status] || STATUS_META.queued).step
                    const isDone = curStep > s.num
                    const isActive = curStep === s.num
                    return (
                      <div key={s.num} className={`pipeline-step ${isActive ? 'active' : ''} ${isDone ? 'done' : ''}`}>
                        <div className="pipeline-dot">
                          {isDone ? '✓' : s.num}
                        </div>
                        <span>{s.label}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

          </aside>
        </div>

        {/* ════════════════════════════════════════════════════════════
            GALERIA DE CLIPES & HISTÓRICO DE JOBS
           ════════════════════════════════════════════════════════════ */}
        <section style={{ marginTop: 36 }}>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            flexWrap: 'wrap', gap: 12, marginBottom: 16
          }}>
            <div>
              <h2 style={{ fontSize: '1.2rem', fontWeight: 800 }}>
                Galeria de Clipes & Processamentos ({jobs.length})
              </h2>
              <p style={{ fontSize: '.8rem', color: 'var(--text-muted)' }}>
                Assista aos cortes 9:16 gerados, copie a legenda viral da IA ou baixe cada parte
              </p>
            </div>

            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <div className="pill-row">
                {[
                  { id: 'all',    label: 'Todos' },
                  { id: 'done',   label: 'Concluídos' },
                  { id: 'active', label: 'Em Andamento' },
                  { id: 'failed', label: 'Falhas' },
                ].map(f => (
                  <button
                    key={f.id}
                    type="button"
                    className={`pill ${jobFilter === f.id ? 'active' : ''}`}
                    onClick={() => setJobFilter(f.id)}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
              <button
                type="button"
                className="btn btn-outline btn-sm"
                onClick={() => fetchJobs(false)}
              >
                <RefreshCw size={13} /> Atualizar
              </button>
            </div>
          </div>

          {jobsLoading ? (
            <div className="card" style={{ textAlign: 'center', padding: 36, color: 'var(--text-muted)' }}>
              Carregando histórico de vídeos…
            </div>
          ) : filteredJobs.length === 0 ? (
            <div className="card" style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
              <Film size={32} style={{ opacity: 0.4, marginBottom: 8 }} />
              <div style={{ fontWeight: 700, color: 'var(--text)' }}>Nenhum corte encontrado neste filtro</div>
              <div style={{ fontSize: '.8rem', marginTop: 4 }}>
                Cole um link do YouTube/Drive ou envie um vídeo acima para criar seus primeiros cortes 9:16.
              </div>
            </div>
          ) : (
            <div className="jobs-grid">
              {filteredJobs.map(job => {
                const meta = STATUS_META[job.status] || STATUS_META.queued
                const pct = PROGRESS[job.status] || 0
                const isRunning = !['done', 'failed', 'cancelled'].includes(job.status)
                const outputs = job.output_files || []
                const activeClipIndex = selectedClipIdx[job.job_id] || 0
                const currentVideoUrl = outputs[activeClipIndex] || outputs[0]

                return (
                  <div key={job.job_id} className="job-card">
                    {/* Header do Job Card */}
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                        <span className={`badge ${meta.cls}`}>
                          {job.status === 'done' && <CheckCircle2 size={12} />}
                          {job.status === 'failed' && <AlertCircle size={12} />}
                          {meta.label}
                        </span>

                        <code style={{ fontSize: '.74rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                          #{job.job_id.slice(0, 8)}
                        </code>

                        {job.channel_name && (
                          <span className="badge badge-info" title={job.channel_handle || ''}>
                            🎙️ {job.channel_name}
                          </span>
                        )}

                        {job.cut_mode && (
                          <span className="badge badge-muted">
                            {String(job.cut_mode).includes('highlight') ? '⚡ IA Highlights' : '✂️ Sequencial'}
                          </span>
                        )}

                        {job.publish_mode === 'addToQueue' && (
                          <span className="badge badge-info">📥 Fila Buffer</span>
                        )}
                        {job.publish_mode === 'scheduled' && (
                          <span className="badge badge-warn">
                            📅 {job.due_at ? new Date(job.due_at).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : 'Agendado'}
                          </span>
                        )}
                        {(!job.publish_mode || job.publish_mode === 'shareNow') && (
                          <span className="badge badge-muted">⚡ Disparo Imediato</span>
                        )}

                        {job.created_at && (
                          <span style={{ fontSize: '.72rem', color: 'var(--text-dim)' }}>
                            {new Date(job.created_at).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
                          </span>
                        )}
                      </div>

                      {/* Ações de Aprovação / Execução / Cancelamento */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                        {job.status === 'done' && (
                          <>
                            {job.approval_status === 'pending' && (
                              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                <span className="badge badge-warn" style={{ gap: 4 }}>
                                  <Clock size={11} /> Aguardando Aprovação
                                </span>
                                <button
                                  type="button"
                                  className="btn btn-xs"
                                  style={{ background: '#10b981', color: '#fff', gap: 5, padding: '4px 10px', fontWeight: 600 }}
                                  disabled={actionLoadingId === job.job_id}
                                  onClick={() => handlePublishJob(job.job_id)}
                                >
                                  <Send size={12} /> {actionLoadingId === job.job_id ? 'Publicando…' : 'Aprovar & Publicar'}
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-outline btn-xs"
                                  style={{ color: '#f87171', borderColor: 'rgba(239, 68, 68, 0.3)' }}
                                  onClick={() => handleRejectJob(job.job_id)}
                                >
                                  Rejeitar
                                </button>
                              </div>
                            )}
                            {job.approval_status === 'published' && (
                              <span className="badge badge-success">🚀 Publicado</span>
                            )}
                            {job.approval_status === 'rejected' && (
                              <span className="badge badge-danger">🚫 Rejeitado</span>
                            )}
                          </>
                        )}

                        {isRunning && (
                          <>
                            {confirmCancelId === job.job_id ? (
                              <>
                                <span style={{ fontSize: '.74rem', color: '#f87171', fontWeight: 600 }}>Confirmar parada?</span>
                                <button
                                  type="button"
                                  className="btn btn-xs"
                                  style={{ background: 'var(--danger)', color: '#fff' }}
                                  onClick={() => cancelJob(job.job_id)}
                                >
                                  Sim, parar
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-outline btn-xs"
                                  onClick={() => setConfirmCancelId(null)}
                                >
                                  Não
                                </button>
                              </>
                            ) : (
                              <button
                                type="button"
                                className="btn btn-outline btn-xs"
                                style={{ color: '#f87171', borderColor: 'rgba(239, 68, 68, 0.35)' }}
                                onClick={() => setConfirmCancelId(job.job_id)}
                              >
                                <Trash2 size={12} /> Parar Job
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    </div>

                    {/* Título ou Gancho se disponível */}
                    {(job.generated_title || job.hook_text) && (
                      <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
                        {job.generated_title && (
                          <span style={{ fontSize: '.92rem', fontWeight: 700, color: 'var(--text)' }}>
                            🎬 {job.generated_title}
                          </span>
                        )}
                        {job.hook_text && (
                          <span className="badge badge-warn" style={{ fontSize: '.72rem' }}>
                            🔥 Gancho: "{job.hook_text}"
                          </span>
                        )}
                      </div>
                    )}

                    {/* Barra de progresso para jobs em andamento */}
                    {isRunning && (
                      <div style={{ marginTop: 12 }}>
                        <div className="progress-track">
                          <div className="progress-bar" style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    )}

                    {/* Mensagem de erro para jobs com falha */}
                    {(job.status === 'failed' || job.status === 'cancelled') && (
                      <div style={{
                        marginTop: 10, padding: '10px 12px',
                        background: 'rgba(239, 68, 68, 0.08)',
                        border: '1px solid rgba(239, 68, 68, 0.25)',
                        borderRadius: 8, fontSize: '.78rem', color: '#fca5a5'
                      }}>
                        ❌ {job.error_message || 'Processamento interrompido.'}
                      </div>
                    )}

                    {/* Galeria de Clipes & Copy IA quando concluído */}
                    {job.status === 'done' && outputs.length > 0 && (
                      <div className="job-output-layout">
                        {/* Player 9:16 */}
                        <div>
                          <video
                            key={currentVideoUrl}
                            src={currentVideoUrl}
                            controls
                            playsInline
                            preload="metadata"
                            className="job-video-player"
                          />
                        </div>

                        {/* Partes, Downloads e Copy Viral */}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                          <div>
                            <div className="label" style={{ marginBottom: 6 }}>
                              <span>Clipes Gerados ({outputs.length})</span>
                              <span style={{ fontSize: '.72rem', color: '#34d399' }}>Prontos em 9:16 HD</span>
                            </div>
                            <div className="pill-row">
                              {outputs.map((fileUrl, idx) => (
                                <button
                                  key={fileUrl}
                                  type="button"
                                  className={`pill ${activeClipIndex === idx ? 'active' : ''}`}
                                  onClick={() => setSelectedClipIdx(prev => ({ ...prev, [job.job_id]: idx }))}
                                >
                                  <Play size={11} style={{ marginRight: 4, display: 'inline' }} />
                                  Parte {idx + 1}
                                </button>
                              ))}
                            </div>
                          </div>

                          {/* Botões de Download */}
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                            <a
                              href={currentVideoUrl}
                              download
                              className="btn btn-primary btn-sm"
                              style={{ textDecoration: 'none' }}
                            >
                              <Download size={14} />
                              Baixar Parte {activeClipIndex + 1} (.MP4)
                            </a>
                            {outputs.length > 1 && outputs.map((fileUrl, idx) => (
                              idx !== activeClipIndex && (
                                <a
                                  key={fileUrl}
                                  href={fileUrl}
                                  download
                                  className="btn btn-outline btn-sm"
                                  style={{ textDecoration: 'none' }}
                                >
                                  <Download size={13} /> Parte {idx + 1}
                                </a>
                              )
                            ))}
                          </div>

                          {/* Copy / Legenda gerada pela IA */}
                          {job.generated_caption && (
                            <div>
                              <div className="label" style={{ marginBottom: 6 }}>
                                <span>Copy Viral & Hashtags Geradas pela IA</span>
                                <button
                                  type="button"
                                  className="btn btn-outline btn-xs"
                                  onClick={() => copyToClipboard(job.generated_caption, job.job_id)}
                                >
                                  {copiedId === job.job_id ? <Check size={12} /> : <Copy size={12} />}
                                  {copiedId === job.job_id ? 'Copiado!' : 'Copiar Legenda'}
                                </button>
                              </div>
                              <div className="copy-box">
                                {job.generated_caption}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </section>
      </div>

      {/* ── Modal de Canais Autorizados (Whitelist) ─────────────── */}
      {showChannelsModal && (
        <div style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0, 0, 0, 0.75)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 9999,
          padding: 16,
        }}>
          <div className="card" style={{
            width: '100%',
            maxWidth: 680,
            maxHeight: '90vh',
            display: 'flex',
            flexDirection: 'column',
            padding: 0,
            overflow: 'hidden',
            border: '1px solid rgba(56, 189, 248, 0.3)',
            boxShadow: '0 20px 50px rgba(0,0,0,0.5)',
          }}>
            {/* Header Modal */}
            <div style={{
              padding: '16px 20px',
              borderBottom: '1px solid var(--border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              background: 'var(--surface-2)',
            }}>
              <div>
                <h3 style={{ fontSize: '1.05rem', fontWeight: 800, display: 'flex', alignItems: 'center', gap: 8, margin: 0 }}>
                  <ShieldCheck size={18} color="#38bdf8" /> Whitelist de Canais Autorizados
                </h3>
                <p style={{ fontSize: '.75rem', color: 'var(--text-dim)', margin: '4px 0 0 0' }}>
                  Apenas canais ativos nesta lista passam pelo Pre-flight Check para evitar strikes e processos.
                </p>
              </div>
              <button
                type="button"
                className="btn btn-outline btn-xs"
                style={{ padding: 6 }}
                onClick={() => setShowChannelsModal(false)}
              >
                <X size={16} />
              </button>
            </div>

            {/* Conteúdo com Scroll */}
            <div style={{ padding: 20, overflowY: 'auto', flex: 1 }}>
              {/* Formulário de Cadastro Rápido */}
              <form onSubmit={handleAddChannel} style={{
                padding: 14,
                background: 'var(--surface-2)',
                borderRadius: 10,
                border: '1px solid var(--border)',
                marginBottom: 20,
              }}>
                <div style={{ fontSize: '.84rem', fontWeight: 700, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Plus size={14} color="#38bdf8" /> Adicionar Canal à Whitelist
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 10, marginBottom: 10 }}>
                  <div>
                    <label className="label" style={{ fontSize: '.74rem', marginBottom: 4 }}>URL ou @handle do Canal *</label>
                    <input
                      type="text"
                      className="input"
                      placeholder="Ex: @flowpdc ou link do YouTube"
                      value={newChanUrl}
                      onChange={e => setNewChanUrl(e.target.value)}
                      style={{ fontSize: '.82rem', padding: '7px 10px' }}
                    />
                  </div>
                  <div>
                    <label className="label" style={{ fontSize: '.74rem', marginBottom: 4 }}>Nome Amigável</label>
                    <input
                      type="text"
                      className="input"
                      placeholder="Ex: Flow Podcast"
                      value={newChanName}
                      onChange={e => setNewChanName(e.target.value)}
                      style={{ fontSize: '.82rem', padding: '7px 10px' }}
                    />
                  </div>
                  <div style={{ maxWidth: 140 }}>
                    <label className="label" style={{ fontSize: '.74rem', marginBottom: 4 }}>Carência (Horas)</label>
                    <input
                      type="number"
                      className="input"
                      min="0"
                      max="168"
                      value={newChanDelay}
                      onChange={e => setNewChanDelay(e.target.value)}
                      style={{ fontSize: '.82rem', padding: '7px 10px' }}
                    />
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 10 }}>
                  <button
                    type="submit"
                    className="btn btn-sm btn-primary"
                    disabled={addingChannel}
                    style={{ gap: 6 }}
                  >
                    {addingChannel ? <RefreshCw size={14} style={{ animation: 'spin 1.2s linear infinite' }} /> : <Plus size={14} />}
                    {addingChannel ? 'Verificando…' : 'Adicionar à Whitelist'}
                  </button>
                </div>
              </form>

              {/* Lista de Canais */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {channelsLoading ? (
                  <div style={{ textAlign: 'center', padding: 20, color: 'var(--text-dim)', fontSize: '.85rem' }}>
                    Carregando canais autorizados…
                  </div>
                ) : authorizedChannels.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: 24, color: 'var(--text-dim)', fontSize: '.85rem' }}>
                    Nenhum canal homologado ainda.
                  </div>
                ) : (
                  authorizedChannels.map(ch => (
                    <div
                      key={ch.id}
                      style={{
                        padding: '12px 14px',
                        background: 'var(--surface-1)',
                        border: '1px solid var(--border)',
                        borderRadius: 8,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: 12,
                        opacity: ch.is_active ? 1 : 0.6,
                      }}
                    >
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <span style={{ fontWeight: 700, fontSize: '.9rem', color: 'var(--text-main)' }}>
                            {ch.name}
                          </span>
                          {ch.handle && (
                            <span style={{ fontSize: '.75rem', color: '#38bdf8', fontFamily: 'var(--font-mono)' }}>
                              {ch.handle}
                            </span>
                          )}
                          <span className={`badge ${ch.is_active ? 'badge-success' : 'badge-muted'}`} style={{ fontSize: '.68rem', padding: '2px 6px' }}>
                            {ch.is_active ? 'Ativo' : 'Inativo'}
                          </span>
                          <span className="badge badge-muted" style={{ fontSize: '.68rem', padding: '2px 6px' }}>
                            ⏳ {ch.min_delay_hours}h carência
                          </span>
                        </div>
                        {ch.policy_notes && (
                          <div style={{ fontSize: '.72rem', color: 'var(--text-dim)', marginTop: 3 }}>
                            {ch.policy_notes}
                          </div>
                        )}
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <button
                          type="button"
                          className="btn btn-outline btn-xs"
                          onClick={() => handleToggleChannel(ch)}
                          style={{ fontSize: '.72rem', padding: '3px 8px' }}
                        >
                          {ch.is_active ? 'Pausar' : 'Ativar'}
                        </button>
                        <button
                          type="button"
                          className="btn btn-outline btn-xs"
                          onClick={() => handleDeleteChannel(ch.id)}
                          style={{ color: '#f87171', borderColor: 'rgba(239,68,68,0.3)', padding: '3px 6px' }}
                          title="Remover da Whitelist"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}
