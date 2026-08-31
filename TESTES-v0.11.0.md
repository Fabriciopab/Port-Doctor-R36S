# Verificações da versão 0.11.0 — 31/08/2026

Registro histórico anterior à publicação. O repositório já foi publicado; a checagem posterior do canal/download está em [TESTES-v0.11.2.md](TESTES-v0.11.2.md). Os limites físicos abaixo continuam válidos.

## Executado

- 24 testes novos locais: quatro perfis, bloqueios de SoC/frequência/temperatura/
  carga, limites inalterados, zram própria, páginas em uso, falta de memória,
  dispositivos alheios, registro após falha e liberação EBUSY do kernel.
- Os primeiros 22 passaram também no próprio R36S com sistema simulado em
  pastas temporárias. Os dois testes EBUSY foram adicionados após o ensaio real.
- Regressão local: 12 testes anteriores de bateria/verificação, 29 de arquivos/
  rede (quatro exclusivos de Linux pulados no Windows), 23 do atualizador,
  três roteiros Lua e validação estrutural dos pacotes.
- 17 telas abertas pelo LÖVE do console, sem erro no roteiro, com capturas
  reais para conferir perfis, zram, guia da rede, ícones e Pix.
- Ensaio físico breve: ondemand → performance → ondemand, sem alterar os
  limites 1.008.000/1.512.000 kHz. O bloqueio térmico não precisou ser excedido
  para testar; condições de risco foram simuladas, não provocadas no aparelho.
- Zram própria zram1 de 447 MiB (50% dos 895 MiB visíveis), ativa e confirmada,
  depois removida sem páginas em uso. zram0 do firmware permaneceu intacta.
- O primeiro ensaio detectou EBUSY transitório ao liberar o dispositivo. Foi
  adicionado retry limitado a dois segundos, só para EBUSY e rechecando ausência
  de uso a cada tentativa. O novo ensaio de criação/restauração passou.
- Sintaxe do preparador PowerShell validada sem executá-lo: nenhuma conta,
  senha, permissão de pasta ou regra de firewall do computador foi alterada.

## Limites

Não é teste prolongado de temperatura, autonomia, desgaste da bateria, desempenho
ou de todos os jogos. Não inclui overclock nem modifica tensão/DTB/kernel. O
limite preventivo de 65 °C não é uma certificação do fabricante.

O ambiente físico é o aparelho que o mantenedor identifica como
R36S-V30-2025-11-18-2603, com dArkOSRE/Debian 13, RK3326 e kernel 4.4.189.

Compartilhamento Windows ponta a ponta depende de executar o preparador em
rede privada e importar a configuração. A publicação e a atualização por uma
release real do GitHub ainda dependem da criação do repositório público.
Não afirmar atualização online validada enquanto essa etapa estiver pendente.
