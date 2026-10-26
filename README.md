# 🎬 VideoFlow

Automatize o download, corte inteligente e publicação de vídeos curtos no **Instagram Reels**, **TikTok** e **Kwai** — 100% gratuito, self-hosted.

---

## ✨ Funcionalidades

| Feature | Descrição |
|---|---|
| 📥 **Download** | YouTube (via yt-dlp) ou Google Drive |
| 🤖 **IA — Highlights** | Whisper transcreve + LLM local (phi3:mini) rankeia os melhores momentos |
| ✂️ **Divisão sequencial** | Corta o vídeo em partes iguais (ex: 60s cada) |
| 📐 **Conversão 9:16** | FFmpeg converte para vertical com fundo desfocado (blur background) |
| 📱 **Publicação automática** | Instagram Reels (Graph API) e TikTok (Content Posting API v2) |
| 📣 **Kwai** | Prepara arquivo + notifica usuário para upload manual |
| 🔐 **Login com Google** | OAuth 2.0 — sem cadastro por senha |
| 🗓️ **Agendamento** | Celery Beat para agendar publicações |
| 🖥️ **UI moderna** | React + Vite, dark glassmorphism |

---

## 🛠 Stack

```
Backend   FastAPI + Celery + Redis + PostgreSQL
IA        Whisper (local) + Ollama phi3:mini (local)
Vídeo     FFmpeg + yt-dlp
Auth      Google OAuth 2.0 → JWT interno (python-jose)
Frontend  React 18 + Vite + react-router-dom
Infra     Docker Compose (Oracle Cloud A1 Always Free)
SSL       Let's Encrypt via Certbot (gratuito)
```

---

## 📁 Estrutura do projeto

```
videoflow/
├── api/
│   ├── main.py                  # FastAPI app + middlewares
│   ├── jwt_auth.py              # issue/decode JWT
│   └── routers/
│       ├── jobs.py              # POST /api/v1/jobs, GET /api/v1/jobs/:id
│       └── auth.py              # OAuth flows (Google, Instagram, TikTok)
├── models/
│   ├── database.py              # SQLAlchemy engine + Job model
│   └── user.py                  # User model com tokens criptografados
├── workers/
│   ├── celery_app.py            # configuração Celery
│   └── pipeline_task.py         # orquestrador: download → IA → FFmpeg → publish
├── services/
│   ├── downloader.py            # yt-dlp + Google Drive API
│   ├── ai_analyzer.py           # Whisper + Ollama + fallback librosa
│   ├── video_processor.py       # FFmpeg: corte + 9:16 blur
│   └── publishers/
│       ├── instagram.py         # Graph API v20
│       ├── tiktok.py            # Content Posting API v2
│       └── kwai.py              # notificação manual
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # AuthContext + rotas
│   │   ├── index.css            # design system dark
│   │   ├── pages/
│   │   │   ├── Login.jsx
│   │   │   ├── Dashboard.jsx
│   │   │   ├── Settings.jsx
│   │   │   └── AuthCallback.jsx
│   │   └── components/Nav.jsx
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
├── nginx/nginx.conf             # reverse proxy + SSL
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── config.py
├── .env.example
├── setup_ssl.sh
└── DEPLOY.md
```

---

## 🚀 Início rápido (desenvolvimento local)

### Pré-requisitos

- Docker + Docker Compose
- Node.js 20+
- Python 3.11+ (opcional, para rodar sem Docker)

### 1. Clone e configure

```bash
git clone https://github.com/seu-user/videoflow.git
cd videoflow

cp .env.example .env
# Edite .env com suas credenciais (ver seção abaixo)
```

### 2. Gere a FERNET_KEY

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Cole o resultado em FERNET_KEY= no .env
```

### 3. Suba o backend

```bash
# Baixar modelo Ollama (primeira vez, ~2.3 GB)
docker compose up ollama -d
sleep 15
docker exec ollama ollama pull phi3:mini

# Subir todos os serviços
docker compose up -d

# Verificar
curl http://localhost:8000/health
# → {"status":"ok"}
```

### 4. Suba o frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

---

## ⚙️ Variáveis de ambiente

Copie `.env.example` para `.env` e preencha:

| Variável | Descrição |
|---|---|
| `APP_SECRET_KEY` | String aleatória ≥ 32 chars (assina JWT e sessão) |
| `FERNET_KEY` | Chave Fernet para criptografar tokens OAuth no banco |
| `DATABASE_URL` | URL PostgreSQL async (`postgresql+asyncpg://...`) |
| `CELERY_BROKER_URL` | `redis://redis:6379/0` |
| `GOOGLE_CLIENT_ID` | OAuth 2.0 Client ID do Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | OAuth 2.0 Client Secret |
| `GOOGLE_REDIRECT_URI` | `http://localhost:8000/auth/google/callback` (dev) |
| `INSTAGRAM_APP_ID` | Facebook App ID (com permissão `instagram_content_publish`) |
| `INSTAGRAM_APP_SECRET` | Facebook App Secret |
| `TIKTOK_CLIENT_KEY` | TikTok Developer Portal — Client Key |
| `TIKTOK_CLIENT_SECRET` | TikTok Developer Portal — Client Secret |
| `WHISPER_MODEL` | `base` (padrão) · `small` · `medium` |
| `OLLAMA_MODEL` | `phi3:mini` (padrão) · `gemma2:2b` |

---

## 🔑 Setup das APIs OAuth

### Google (login + Drive)

1. [console.cloud.google.com](https://console.cloud.google.com) → **APIs & Services → Credentials**
2. Criar **OAuth 2.0 Client ID** → tipo: Web Application
3. Redirect URI: `http://localhost:8000/auth/google/callback`
4. Ativar APIs: **Google Drive API** + **People API**
5. Copiar Client ID e Secret para o `.env`

### Instagram

1. [developers.facebook.com](https://developers.facebook.com) → criar App → tipo: **Business**
2. Adicionar produto: **Instagram Graph API**
3. Escopos necessários: `instagram_basic`, `instagram_content_publish`, `pages_show_list`
4. Redirect URI: `http://localhost:8000/auth/instagram/callback`
5. ⚠️ Aprovação da Meta pode levar 1–7 dias

### TikTok

1. [developers.tiktok.com](https://developers.tiktok.com) → criar App
2. Produto: **Content Posting API**
3. Escopos: `video.publish`, `video.upload`
4. Redirect URI: `http://localhost:8000/auth/tiktok/callback`
5. ⚠️ Aprovação pode levar 3–14 dias

---

## 📡 API Endpoints

### Jobs

| Método | Endpoint | Descrição |
|---|---|---|
| `POST` | `/api/v1/jobs` | Cria e enfileira um novo job |
| `GET` | `/api/v1/jobs/:id` | Consulta status e outputs de um job |

**Payload de criação:**
```json
{
  "source_type": "youtube",
  "source_url": "https://youtube.com/watch?v=XXXX",
  "cut_mode": "highlights",
  "max_clips": 3,
  "max_clip_duration": 60,
  "platforms": ["instagram", "tiktok"]
}
```

**Status possíveis:** `queued` → `downloading` → `analyzing` → `processing` → `publishing` → `done` / `failed`

### Auth

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/auth/google/login` | Redireciona para login Google |
| `GET` | `/auth/google/callback` | Callback OAuth → emite JWT |
| `GET` | `/auth/me` | Retorna perfil do usuário autenticado |
| `POST` | `/auth/refresh` | Renova access token com refresh token |
| `GET` | `/auth/instagram/login` | Conecta conta Instagram (requer JWT) |
| `GET` | `/auth/tiktok/login` | Conecta conta TikTok (requer JWT) |

---

## 🏗 Arquitetura

```
Browser
  │  Login Google → /auth/google/login
  │  JWT salvo no localStorage
  │
  ▼
FastAPI (porta 8000)
  │  POST /api/v1/jobs
  │  → cria Job no PostgreSQL
  │  → enfileira task no Redis
  │
  ▼
Celery Worker (concurrency=1)
  ├─ Download (yt-dlp / Drive API)
  ├─ Whisper local → transcrição
  ├─ Ollama phi3:mini → ranking de segmentos
  ├─ FFmpeg → corte + conversão 9:16
  └─ Publishers
       ├─ Instagram Graph API
       ├─ TikTok API v2
       └─ Kwai → notificação manual
```

---

## ☁️ Deploy — Oracle Cloud Always Free

> VM Ampere A1: **2 vCPU + 12 GB RAM** permanente e gratuito.

Consulte o guia completo em [`DEPLOY.md`](./DEPLOY.md).

```bash
# Resumo
bash setup_ssl.sh meudominio.com email@exemplo.com
docker compose up ollama -d && docker exec ollama ollama pull phi3:mini
docker compose up -d
curl https://meudominio.com/health
```

**Orçamento de RAM em pico:**

| Serviço | RAM |
|---|---|
| FastAPI | 300 MB |
| Celery Worker | 4.5 GB (Whisper + FFmpeg) |
| Ollama phi3:mini | 2.3 GB (idle = descarregado) |
| Redis + PostgreSQL | 550 MB |
| Nginx + Beat | 200 MB |
| **Total pico** | **~8.5 GB** ✅ |

> Whisper e Ollama **nunca carregam simultaneamente** — o worker os usa em sequência.

---

## 🗺 Roadmap

- [x] Download YouTube + Google Drive
- [x] Corte sequencial + conversão 9:16
- [x] IA local: Whisper + Ollama
- [x] Publicação Instagram + TikTok
- [x] Login com Google + sistema de usuários
- [x] UI React glassmorphism
- [ ] Preview dos clips antes de publicar
- [ ] Legenda automática (subtítulos queimados no vídeo)
- [ ] Agendamento com calendário na UI
- [ ] Webhook de notificação pós-publicação
- [ ] Suporte a múltiplas contas por plataforma

---

## 📄 Licença

MIT — use à vontade.
