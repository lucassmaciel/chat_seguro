# Funcionamento dos Pilares de Segurança

Este documento descreve, em detalhes, como cada pilar (confidencialidade, integridade,
disponibilidade e autenticidade) está implementado no Chat Seguro após as últimas
melhorias.

## Confidencialidade
- **Transporte TLS**: o servidor reutiliza o certificado e chave privada armazenados no
  SQLite; o contexto TLS é carregado em memória usando arquivos temporários curtos e com
  remoção imediata.
- **Criptografia em repouso**: toda mensagem recebida é recriptografada pelo servidor com
  `SecretBox` (chave derivada de `MESSAGE_STORE_KEY_B64` ou do material TLS). O payload
  que já chega cifrado dos clientes é encapsulado novamente antes de ser salvo.
- **Proteção de chaves de cliente**: o keystore local exige `LOCAL_KEY_SECRET` em base64
  com pelo menos 32 bytes; as chaves privadas (Box + assinatura) são armazenadas cifradas
  em SQLite com BLAKE2b + SecretBox.

## Integridade
- **Tags autenticadas**: cada mensagem persiste um `auth_tag` HMAC-SHA256. Qualquer
  alteração no banco (blob ou tag) provoca descarte silencioso e log de alerta na
  leitura.
- **Prova de posse de chave**: rotações de chave pública só são aplicadas se o cliente
  apresentar assinatura válida do payload `client_id:pubkey:signing_pubkey` usando a
  chave de assinatura previamente registrada.
- **Validação de entregas**: mensagens são decriptadas e verificadas antes de serem
  devolvidas para os clientes; falhas na verificação não vazam conteúdo adulterado.

## Disponibilidade
- **Limite de fila por destinatário**: `MAX_PENDING_PER_CLIENT` controla o tamanho da
  caixa de mensagens. Se o limite é atingido, mensagens mais antigas são descartadas para
  evitar saturação do banco e atrasos de entrega.
- **Concorrência segura**: operações de leitura e remoção de mensagens usam transações
  com bloqueio imediato (`BEGIN IMMEDIATE`) para garantir consumo idempotente mesmo sob
  múltiplas requisições simultâneas.
- **Gestão de grupos**: mensagens de grupo são entregues individualmente para cada
  membro restante; remoções de membros atualizam imediatamente a tabela de assinantes.

## Autenticidade
- **Rotação com prova**: a publicação de nova chave exige assinatura com a chave de
  assinatura previamente conhecida. Sem `proof`, a atualização é rejeitada.
- **Distribuição de chaves de grupo**: o administrador cria e distribui chaves simétricas
  de grupo cifradas individualmente com Box; apenas membros com a chave conseguem
  descriptografar mensagens de grupo.
- **Controle de membros**: um endpoint dedicado permite que apenas o administrador
  remova integrantes de um grupo, garantindo que a composição do grupo seja confiável.

## Configurações relevantes
- `MESSAGE_STORE_KEY_B64`: chave base64 de 32 bytes usada para criptografia e HMAC das
  mensagens persistidas.
- `MAX_PENDING_PER_CLIENT`: limite máximo de mensagens pendentes por destinatário
  (default: 500).
- `LOCAL_KEY_SECRET`: chave base64 de 32 bytes necessária para proteger o keystore local
  do cliente.
