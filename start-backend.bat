@echo off
echo ==============================================
echo  Iniciando VideoFlow - Ambiente Local
echo ==============================================

echo [1/2] Verificando Docker...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Docker nao esta rodando!
    echo Abra o Docker Desktop e aguarde inicializar, depois execute este script novamente.
    pause
    exit /b 1
)

echo [2/2] Subindo servicos de backend (Postgres, Redis, API, Worker)...
docker compose -f docker-compose.local.yml up -d --build


echo.
echo ==============================================
echo Backend pronto!
echo API rodando em: http://localhost:8000
echo Documentacao Swagger: http://localhost:8000/docs
echo ==============================================
echo Para iniciar o frontend, execute start-frontend.bat ou:
echo   cd frontend ^&^& npm run dev
echo.
pause
