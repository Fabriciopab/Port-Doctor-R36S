# Roadmap do Port Doctor R36S

O objetivo é transformar o Port Doctor em uma central local de diagnóstico, instalação, recuperação e manutenção, sem distribuir jogos, BIOS ou dados proprietários. Cada função deve ser testável, reversível quando possível e segura para os dois cartões.

## 0.12 — Port Hub local

- Instalar ports de uma pasta compartilhada do Windows.
- Escolher cartão 1 ou cartão 2.
- Validar pacote, espaço e conflitos.
- Copiar de forma transacional e conferir o resultado.
- Ajustar launchers e integrar com capas e diagnóstico existentes.

## Próximas entregas prioritárias

### Gerenciador de ports

- Comparar a versão instalada com um manifesto local opcional.
- Atualizar somente arquivos do port, preservando saves e configurações.
- Criar backup antes de atualizar e oferecer restauração.
- Instalação em fila e opção “instalar todos”.
- Detectar pacotes incompletos antes da cópia.

### Centro de saves

- Localizar saves conhecidos de ports e emuladores.
- Fazer backup para o computador pela rede.
- Restaurar com prévia e confirmação.
- Comparar data e tamanho para evitar substituir um save novo por um antigo.
- Produzir relatório sem expor conteúdo pessoal.

### Saúde dos cartões

- Verificar espaço, montagem somente leitura e erros de entrada/saída.
- Identificar desligamento incorreto e sistemas de arquivos que precisam ser examinados no computador.
- Criar inventário exportável de jogos, saves e capas.
- Avisar sobre pouco espaço antes de uma instalação ou atualização.

### Central de compatibilidade

- Registrar modelo, firmware, arquitetura e resultado dos testes feitos no próprio aparelho.
- Associar erros conhecidos a reparos já validados.
- Exportar relatório pronto para abrir uma issue, sem senhas ou dados proprietários.
- Importar pacotes de compatibilidade assinados e verificáveis.

### Experiência de uso

- Busca e filtros nos ports.
- Indicador real de progresso durante cópias longas.
- Histórico de instalações, atualizações, reparos e restaurações.
- Assistente inicial que testa cartões, rede, PortMaster e permissões.
- Traduções mantidas separadamente da lógica do programa.

## Limites permanentes

- Não baixar nem distribuir jogos, BIOS ou arquivos proprietários.
- Não prometer correção universal.
- Não alterar kernel, DTB, clocks, tensão ou bibliotecas centrais sem uma integração específica, validada e claramente confirmada.
- Não sobrescrever saves ou jogos silenciosamente.
- Não esconder falhas: toda alteração relevante deve produzir um resultado e, quando aplicável, um backup.
