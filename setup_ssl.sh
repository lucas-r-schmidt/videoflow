#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  setup_ssl.sh — Obtém certificado Let's Encrypt via Certbot
#  Execute UMA VEZ na VM da Oracle antes do docker compose up
#  Uso: bash setup_ssl.sh seudominio.com seu@email.com
# ─────────────────────────────────────────────────────────────

set -e

DOMAIN=${1:?"Uso: $0 <dominio> <email>"}
EMAIL=${2:?"Uso: $0 <dominio> <email>"}
CERT_DIR="./nginx/certs"

echo "▶ Instalando Certbot..."
sudo apt-get update -q
sudo apt-get install -y certbot

echo "▶ Obtendo certificado para $DOMAIN..."
# Standalone: certbot sobe um servidor HTTP temporário na porta 80
# Garanta que a porta 80 esteja aberta no Security List da Oracle
sudo certbot certonly \
  --standalone \
  --non-interactive \
  --agree-tos \
  --email "$EMAIL" \
  -d "$DOMAIN"

echo "▶ Copiando certificados para $CERT_DIR..."
mkdir -p "$CERT_DIR"
sudo cp -rL /etc/letsencrypt "$CERT_DIR/"
sudo chown -R "$USER:$USER" "$CERT_DIR"

echo "▶ Configurando renovação automática (cron a cada 12h)..."
(crontab -l 2>/dev/null; echo "0 */12 * * * certbot renew --quiet && docker compose -f $(pwd)/docker-compose.yml exec nginx nginx -s reload") | crontab -

echo "✅ SSL configurado! Atualize nginx.conf com o domínio: $DOMAIN"
echo "   Depois execute: docker compose up -d"
