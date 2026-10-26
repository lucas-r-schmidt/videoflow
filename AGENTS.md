# Regras do Projeto — VideoFlow

## 1. Fluxo de Desenvolvimento e Deploy (Local-First)

* **Desenvolvimento e Validação Local Obrigatória**:
  * Todas as alterações de código (backend, workers, frontend e banco de dados) devem ser feitas e validadas localmente em primeiro lugar.
  * O build do frontend (`npm run build`) e a verificação de integridade/sintaxe devem ser validados na máquina local.

* **Sincronização com a VM Oracle Cloud**:
  * **PROIBIDO** enviar arquivos (`scp`), aplicar migrações ou reiniciar serviços/containers na VM de produção sem confirmação ou comando explícito do usuário (ex: *"Pode subir para a Oracle"*, *"Deploy"*, *"Atualizar a VM"*).
  * O fluxo correto é sempre:
    1. Implementar e validar na máquina local.
    2. Apresentar as mudanças para o usuário testar e aprovar.
    3. Somente após a autorização explícita, realizar o deploy na VM Oracle.

## 2. Procedimento Padrão de Deploy (Quando Autorizado)

1. **Banco de Dados (PostgreSQL)**:
   * Aplicar migrações/alterações de schema (`ALTER TABLE ...`) via `docker exec postgres psql` antes de subir código dependente.
2. **Backend**:
   * Transferir arquivos alterados via `scp` para `/home/ubuntu/videoflow/`.
   * Copiar para os containers Docker (`api`, `celery_worker`, `celery_beat`) com `docker cp`.
   * Reiniciar os containers necessários (`sudo docker restart api celery_worker celery_beat`).
3. **Frontend**:
   * Gerar build local (`npm run build`).
   * Transferir pasta `dist/` para a VM.
   * Publicar arquivos em `/var/www/videoflow/`.
4. **Health Check**:
   * Validar logs dos containers e resposta do endpoint `/health`.
