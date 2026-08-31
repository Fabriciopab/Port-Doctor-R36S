# Verificação da versão 0.10.0 — 30/08/2026

## Ambiente

R36S do mantenedor, identificado por ele como **R36S-V30-2025-11-18-2603**.
dArkOSRE/Debian 13, ARM64 com ARMHF, kernel 4.4.189, Mali-G31, tela 640×480,
LÖVE 11.5 do PortMaster e cartão `/roms` em exFAT. A identificação da revisão
é fornecida pelo mantenedor; não é uma certificação independente de hardware.

## Resultados

- 23 testes automatizados do atualizador passaram no computador, no `/tmp`
  do console e novamente com os arquivos temporários no cartão exFAT.
- Cobertura: versão, origem HTTPS permitida, repositório do mantenedor,
  pacote obrigatório, SHA-256, download parcial, espaço insuficiente,
  caminhos/links perigosos, nomes duplicados, pacote alterado, confirmação,
  preparação sem instalação, resultado e bloqueio de repetição após falha.
- As chamadas ao GitHub e a execução do instalador nesses 23 testes são
  **simuladas**. Eles verificam o comportamento do código sem baixar uma
  release real ou trocar a instalação de uso do mantenedor.
- Testes locais da interface verificam menus, arquivos e o novo fluxo de
  atualização: consulta → confirmação → download preparado → saída do app.
  Também verificam a chave Pix, contribuição opcional e aviso de modelo.
- As 13 páginas do roteiro visual abriram no console sem erro do LÖVE.
  Capturas reais foram usadas para conferir ícones, textos e alinhamento.
  Um contorno de ícone incompleto no GLES foi corrigido após essa inspeção.
- Foram mantidos os testes de regressão das funções de bateria e arquivos.
  Nenhum jogo real foi excluído e nenhum pagamento foi realizado.

## Pendência explícita

Não havia repositório público do Port Doctor definido. O manifesto usa
`github_repository: null`. A consulta sem canal informa essa condição e
não acessa a rede. Download e instalação ponta a ponta de uma release real
**ainda precisam ser validados após a publicação do canal oficial**.

SHA-256 confere integridade com os metadados HTTPS do GitHub, não é uma
assinatura independente. Backups são preservados, mas uma interrupção de
energia durante a troca de arquivos pode exigir reinstalação pelo menu Tools.
Não promete corrigir todos os ports nem atualiza o firmware do aparelho.
