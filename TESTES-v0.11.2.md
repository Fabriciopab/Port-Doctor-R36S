# Publicação e verificação da 0.11.2 — 31/08/2026

## Confirmado

- Repositório público `Fabriciopab/Port-Doctor-R36S`, com código, licença MIT, créditos/Pix e guias de instalação e funções.
- Regressões locais: 12 testes de bateria/verificação, 29 de arquivos/rede (quatro exclusivos de Linux pulados no Windows), 23 do atualizador e 24 de perfis/zram, além dos ciclos de reparo/capas e três roteiros Lua.
- Testes e empacotamento no GitHub Actions/Linux concluídos com sucesso: [execução da release](https://github.com/Fabriciopab/Port-Doctor-R36S/actions/runs/33360190983).
- ZIP real passa pelo validador do protocolo 1. A documentação adicional fica em `portdoctor/docs/`, não na raiz.
- Download HTTPS real dos cinco assets da [release 0.11.2](https://github.com/Fabriciopab/Port-Doctor-R36S/releases/tag/v0.11.2); tamanho e SHA-256 conferidos com os metadados do GitHub.
- Instalador aninhado contém o mesmo pacote direto publicado e marca seu script com permissão Unix 0755.
- Em uma instalação simulada e temporária com versão 0.11.0, o atualizador encontrou a 0.11.2, mostrou a oferta, baixou e preparou o pacote oficial com sucesso. O instalador não foi executado nesse ensaio.
- Distribuição USB não contém cadastro de senha padrão embutida; preserva credenciais existentes. Configurações pessoais, logs e credenciais não são incluídos nos pacotes.

## Limites

Esta publicação não reinstalou o aplicativo no console nem repetiu testes físicos de cada função. O ensaio online verificou consulta, download e preparação no computador, não uma instalação ponta a ponta pela conexão do R36S.

Os testes físicos anteriores e seus limites estão em [TESTES-v0.11.0.md](TESTES-v0.11.0.md). A revisão de referência é **R36S-V30-2025-11-18-2603 com dArkOSRE**, informada pelo mantenedor. Não há certificação para clones, outros firmwares, autonomia, temperatura prolongada ou todos os jogos.

## Correção da 0.11.1

A checagem cruzada após a primeira publicação detectou que manuais extras na raiz faziam o atualizador antigo recusar o pacote. A 0.11.2 corrige a organização e inclui teste de regressão do ZIP real. Use a última release, não a 0.11.1 para atualização automática.

**fabriciopab** · **fabricio@byteforce-ai.com** · Pix voluntário: **fabriciopab@hotmail.com**.
