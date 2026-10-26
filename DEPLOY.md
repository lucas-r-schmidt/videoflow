# 🚀 Guia de Deploy — Oracle Cloud A1 (Always Free)

## Pré-requisitos

- VM Oracle A1 criada (Ubuntu 22.04 ARM64)
- Domínio apontando para o IP público da VM
- Portas abertas no **Security List** da Oracle:
  - 22 (SSH), 80 (HTTP), 443 (HTTPS), 8000 (opcional, debug)

---

## 1. Preparar a VM

```bash
# Atualizar sistema
sudo apt-get update && sudo apt-get upgrade -y

# Instalar Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Instalar Docker Compose plugin
sudo apt-get install -y docker-compose-plugin

# Verificar
docker compose version
```

---

## 2. Clonar o projeto

```bash
git clone https://github.com/seu-user/video-automation.git
cd video-automation
```

---

## 3. Configurar variáveis de ambiente

```bash
cp .env.example .env
nano .env   # preencher todos os campos

# Gerar FERNET_KEY
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Colar o resultado no .env → FERNET_KEY=...
```

---

## 4. Obter certificado SSL (antes do Nginx subir)

```bash
chmod +x setup_ssl.sh
bash setup_ssl.sh seudominio.com seu@email.com
```

---

## 5. Atualizar nginx.conf com seu domínio

```bash
sed -i 's/seudominio.com/meudominio.com/g' nginx/nginx.conf
```

---

## 6. (Opcional) Baixar modelo Ollama — Pule se usar GROQ_API_KEY

> **Nota:** Com `GROQ_API_KEY` configurada no `.env`, a transcrição e análise rodam na nuvem da Groq. O Ollama não é iniciado e esta etapa pode ser **ignorada**, economizando 2.3 GB de disco e ~3 GB de RAM.

Se optar por rodar LLM localmente:
```bash
docker compose --profile local-llm up ollama -d
sleep 10
docker exec -it ollama ollama pull phi3:mini
docker compose --profile local-llm stop ollama
```

---

## 7. Subir todos os serviços

```bash
docker compose up -d

# Verificar status
docker compose ps

# Verificar logs do worker
docker compose logs -f worker
```

---

## 8. Verificar saúde da API

```bash
curl https://seudominio.com/health
# Esperado: {"status":"ok"}
```

---

## 9. Testar primeiro job

```bash
curl -X POST https://seudominio.com/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "youtube",
    "source_url": "https://www.youtube.com/watch?v=EXEMPLO",
    "cut_mode": "sequential",
    "part_duration": 60,
    "platforms": []
  }'

# Copiar o job_id retornado e consultar status
curl https://seudominio.com/api/v1/jobs/{job_id}
```

---

## Operações do dia a dia

```bash
# Atualizar yt-dlp (fazer semanalmente)
docker exec worker yt-dlp -U

# Ver uso de RAM em tempo real
docker stats --no-stream

# Reiniciar worker (se travar)
docker compose restart worker

# Ver fila Celery
docker exec redis redis-cli LLEN celery

# Backup do banco
docker exec postgres pg_dump -U app video_automation > backup.sql

# Atualizar a aplicação
git pull
docker compose build
docker compose up -d
```

---

## Monitoramento de RAM (referência)

```bash
watch -n 5 'docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}"'
```

Saída esperada em idle:
```
NAME              MEM USAGE
api               120MiB / 12GiB
celery_worker     180MiB / 12GiB   ← sobe para ~4GB durante job
celery_beat        80MiB / 12GiB
redis             50MiB  / 12GiB
postgres          90MiB  / 12GiB
ollama            200MiB / 12GiB   ← sobe para ~2.3GB quando ativo
nginx             10MiB  / 12GiB
```
