# Perfis e memória: decisões de segurança

Referência: aparelho identificado pelo mantenedor como **R36S-V30-2025-11-18-2603**,
dArkOSRE/Debian 13, kernel 4.4.189, RK3326. A leitura no aparelho mostrou limite
de CPU 1.512.000 kHz, governors ondemand/conservative/performance disponíveis,
916.856 KiB de RAM visível e zram com lzo. Isso não valida todas as revisões.

## Quatro modos, não quatro níveis de overclock

| Perfil | Uso sugerido | Alterações |
| --- | --- | --- |
| Padrão do aparelho | Primeira escolha quando tudo funciona | Desfaz somente mudanças registradas pelo Doctor neste boot |
| Equilibrado | Uso diário | Governor sob demanda disponível; não aumenta brilho nem limites |
| Economia | Jogos leves/autonomia | Brilho até 30% e conservative quando disponível |
| Desempenho | Teste pontual de jogos exigentes | Performance no limite já definido pelo firmware |

O Linux expõe os governors e limites de política; performance solicita o máximo
permitido na política, enquanto modos sob demanda acompanham a carga.
[Documentação oficial CPUFreq](https://www.kernel.org/doc/html/latest/admin-guide/pm/cpufreq.html).

O Doctor não escreve em scaling_min_freq/scaling_max_freq, tensão, GPU, DTB,
carregamento ou proteções térmicas. Não instala um overclock: frequências que
funcionam em um aparelho não podem ser certificadas para a comunidade inteira.
O [projeto dArkOSRE](https://github.com/southoz/dArkOSRE-R36) atende diferentes
revisões e clones; o nome comercial R36S não basta para garantir equivalência.

Para Desempenho, o app recusa SoC diferente de RK3326, limite desconhecido ou
acima de 1,512 GHz, sensores ausentes/temperatura >=65 °C e bateria <20% quando
informada. **65 °C e 20% são políticas preventivas do app, não limites publicados
pelo fabricante.** A checagem é apenas na ativação. Não existe vigilância térmica
contínua do Doctor; as proteções do firmware ficam intactas. Calor/instabilidade
exigem voltar ao Equilibrado/Padrão. Nenhuma promessa de segurança absoluta.

## Zram

Zram guarda páginas comprimidas na própria RAM. Área lógica maior não significa
RAM física adicional. Compressão exige CPU e dados pouco compressíveis podem
reduzir o benefício. O kernel exige desativar/resetar antes de mudar tamanho.
[Documentação oficial zram](https://www.kernel.org/doc/Documentation/blockdev/zram.txt).

Recomendação principal: preservar o padrão se não há falta de memória. Opções
25%, 50% (ponto de partida sugerido) e 75% são escolhas conservadoras do projeto,
não benchmarks nem recomendação oficial de Rockchip. Calcula-se sobre a RAM
visível, arredondando para MiB inteiros; nesse aparelho 50% resulta em 447 MiB.

- Cria somente dispositivo novo pelo hot_add. Não modifica áreas do firmware.
- Recusa manutenção com pouca RAM disponível e desativação de swap com páginas
  em uso. Não força swapoff, não limpa caches e não mata jogos para liberar RAM.
- Confere cada operação e conserva registro de propriedade em /run. Falha de
  ativação mantém o registro; Padrão remove apenas a área própria se estiver livre.
- Não muda swappiness, algoritmo de compressão, swap em disco ou inicialização.
- Vale neste boot. Reiniciar descarta a área própria e deixa o firmware iniciar
  normalmente. Jogos/launchers podem configurar sua própria memória depois.
- Testes com sistema simulado não substituem ensaio prolongado com cada jogo.

## Rede no Windows

O assistente adiciona uma conta e permissões somente após confirmação local.
Não compartilhe dados pessoais junto das ROMs. A regra nova usa rede Private e
origem LocalSubnet; não altera regras preexistentes nem abre portas no roteador.
[Firewall da Microsoft](https://learn.microsoft.com/en-us/powershell/module/netsecurity/new-netfirewallrule)
e [compartilhamento SMB](https://learn.microsoft.com/en-us/powershell/module/smbshare/new-smbshare).
O .conf transporta credencial em Base64: não envie ao GitHub nem a terceiros.
