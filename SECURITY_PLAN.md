# Plano de Ação de Segurança da Informação

Este plano organiza as iniciativas necessárias para garantir que o Chat Seguro
atenda aos pilares clássicos de segurança da informação — **Confidencialidade**,
**Integridade**, **Disponibilidade**, além de **Autenticidade** e **Auditabilidade**
como extensões práticas. Cada item possui um objetivo claro, responsáveis
implícitos (squad de aplicação) e indicadores de sucesso.

## 1. Confidencialidade

- **Camada de Transporte**: manter TLS obrigatório entre clientes, bridge web e
  servidor TLS (já implantado). Auditoria trimestral de certificados e renovação
  automatizada.
- **Criptografia de Ponta a Ponta**: continuar utilizando ECDH +
  Salsa20/Poly1305 com rotação automática de chaves de sessão por conversa.
  Metas: cobertura de 100 % das mensagens e revisão semestral de bibliotecas
  criptográficas.
- **Gestão de Credenciais**: armazenar senhas com PBKDF2-HMAC-SHA256 e salt
  individual; nunca registrar segredos em texto puro. Revisar código via Ruff e
  Pyright em cada PR.
- **MFA Obrigatório**: enviar códigos de uso único por e-mail em cada login e
  expirá-los em 5 minutos para mitigar sequestro de sessão.

## 2. Integridade

- **Assinaturas de Mensagens**: manter MAC via Poly1305. Futuro: adicionar
  assinaturas digitais opcionais para mensagens críticas.
- **Proteção de Dados em Repouso**: validar hashing de conversas locais no
  cliente e permitir chave mestra opcional. Realizar checksum periódico dos
  arquivos `pubkeys.json` e `users.json`.
- **Fluxo de CI**: executar Ruff (configuração em `ruff.toml`) e Pyright padrão
  para detectar erros lógicos antes de liberar builds.

## 3. Disponibilidade

- **Monitoramento**: expor `/api/status` (já disponível) e coletar métricas com
  alertas caso o número de sessões caia abruptamente.
- **Reinício Automático**: configurar systemd/supervisord para reiniciar os
  serviços `server.py` e `web_bridge.py` em falhas.
- **Backups**: snapshot diário dos arquivos de estado (`users.json`,
  `pubkeys.json`, conversas) com retenção mínima de 30 dias.
- **Teste de Carga**: realizar testes trimestrais de WebSocket e TLS para
  validar comportamento com >100 sessões simultâneas.

## 4. Autenticidade & Autorização

- **Registro Vinculado a E-mail**: exigir e-mail único e ID público para o chat
  durante o cadastro. Validar domínio com `EmailStr` (Pydantic) e enviar link
  de confirmação em fases futuras.
- **Fluxo MFA**: tokens randômicos e códigos de 6 dígitos enviados por e-mail.
  Rejeitar tentativas após 5 minutos ou três erros consecutivos.
- **Sessões**: associar cada sessão ativa a um `client_id` validado e revogar
  em logout/timeout. Não permitir login automático apenas com o ID.

## 5. Auditabilidade

- **Logs Estruturados**: padronizar logs JSON para autenticação, MFA e criação
  de grupos, garantindo rastreabilidade.
- **Trilhas de Auditoria**: registrar hora, IP e cliente de cada login e
  tentativa de MFA. Retenção mínima de 90 dias.
- **Alertas**: disparar alertas internos após 5 falhas de MFA para a mesma
  conta em 10 minutos.

## 6. Próximos Passos

1. Implementar MFA por e-mail e cadastro seguro (entrega atual).
2. Automatizar backups criptografados e testes de restauração.
3. Adicionar assinatura digital opcional para mensagens críticas.
4. Construir painel de observabilidade com métricas de disponibilidade.
5. Programar exercícios de resposta a incidentes semestrais.

Este documento deve ser revisado trimestralmente e atualizado conforme novas
ameaças, requisitos regulatórios ou mudanças arquiteturais.

