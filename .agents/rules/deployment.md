# Regras de Desenvolvimento e Deploy

- **Local-First**: Qualquer modificação, refatoração ou nova funcionalidade deve ser executada e validada exclusivamente na máquina local primeiro.
- **Deploy na VM Oracle**: Nunca sincronizar (`scp`), alterar banco remoto ou reiniciar containers na VM sem a aprovação ou pedido explícito do usuário.
- **Validação pré-deploy**: Build do frontend e validação de sintaxe devem ter sucesso local antes de qualquer envio.
