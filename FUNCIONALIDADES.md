# Manual das funcionalidades do Port Doctor R36S

Referência detalhada dos recursos, organizados por versão de introdução. Para começar, consulte o [guia de instalação](INSTALACAO.md) e a [página principal](README.md). Versão atual: **0.11.3**; canal oficial: **Fabriciopab/Port-Doctor-R36S**.

## 0.11.3 — dArkOSRE e pacotes Unity

O sistema foi testado no **dArkOSRE (Debian 13)**, no R36S identificado pelo mantenedor como **R36S-V30-2025-11-18-2603**. O aviso aparece na tela inicial, no Sobre e em Modelo e sistema testados. Não certifica todos os firmwares ou jogos.

Em **Meus ports → selecione o jogo → Correções**, ports que incluem `unityloader` oferecem **Verificar pacote Unity**. Execute com o jogo fechado. A leitura identifica arquitetura e SHA-256 dos binários e compara os dados com `gamedata/META-INF/MANIFEST.MF`, quando disponível. Mostra arquivos ausentes, diferentes ou entradas recusadas. **X** salva o relatório.

Nenhum save, biblioteca ou configuração é alterado por essa verificação. Um manifesto local não autentica o publicador e um resultado sem diferenças não comprova que o jogo abre. Para o Hollow Knight investigado, consulte os [resultados físicos e limitações](TESTES-v0.11.3.md).

Utilitário comunitário de diagnóstico e manutenção protegida para handhelds Linux compatíveis com PortMaster, criado por **fabriciopab**.

- GitHub: https://github.com/Fabriciopab
- Contato: fabricio@byteforce-ai.com
- Pix para apoiar o avanço do projeto: **fabriciopab@hotmail.com** (contribuição voluntária).

**Atestado no R36S-V30-2025-11-18-2603**, com dArkOSRE no aparelho usado nos testes. Identificação da revisão informada pelo mantenedor. Outras revisões, clones e firmwares não têm funcionamento garantido; isso não é uma certificação de todos os jogos/reparos.

## Novidades da versão 0.11.0

- **Quatro perfis:** Padrão (restaura alterações do Doctor), Equilibrado (CPU sob demanda), Economia (brilho até 30% + conservative disponível) e Desempenho (governor performance). Brilho manual continua disponível. Perfis valem até reiniciar; não há overclock nem alteração de tensão, frequência máxima/mínima, GPU, DTB ou kernel.
- **Desempenho com bloqueios preventivos:** somente RK3326 com limite já configurado até 1,512 GHz, sensores presentes abaixo de 65 °C e carga não inferior a 20% quando reportada. O limiar é uma política conservadora do projeto, não uma especificação do fabricante. A checagem ocorre na ativação, não há monitor contínuo do Doctor. As proteções do firmware não são desligadas. Se aquecer/ficar instável, restaure o padrão.
- **Memória e zram:** mostra RAM disponível, área lógica, memória comprimida e opções de 25%, 50% e 75% da RAM visível. Mantenha o padrão se o jogo já funciona; 50% é sugestão inicial do projeto para investigar falta de memória, não ganho de FPS garantido.
- Só cria uma área própria usando o suporte dinâmico do kernel; não formata nem substitui zram do firmware. Recusa trocar/desativar com páginas em uso, pouca RAM ou dispositivo alterado. Não cria swap no cartão, não muda swappiness e não carrega módulos/kernel. Vale até reiniciar. Se estiver em uso, feche os jogos e reinicie antes de escolher outro tamanho.
- **Jogos em rede:** a primeira opção explica o preparador do PC, pasta, senha e importação. O ZIP Windows-Rede contém o `.cmd`, o `.ps1` e o guia, sem credenciais. A pasta inteira deve ser extraída no Windows; o usuário abre o `.cmd`, escolhe a pasta e a senha e copia o `.conf` gerado para tools. Tudo depois é feito pelo Doctor.
- Preparador do Windows restrito a pasta dedicada e rede Privada, com regra SMB TCP 445 para LocalSubnet. Não ativa SMB1 nem desliga o firewall. Adiciona acesso de gravação para saves preservando permissões anteriores. Exige confirmação no computador. Nunca publique o `.conf`, pois Base64 não é criptografia.

As recomendações e seus limites estão em [SEGURANCA-DESEMPENHO.md](SEGURANCA-DESEMPENHO.md). Não existe configuração universalmente segura/rápida para clones, firmwares modificados e todos os jogos. Nenhum perfil é ativado pela instalação.

## Novidades da versão 0.10.0

- Ícones coloridos desenhados pelo próprio app em menus, listas e cabeçalhos. Não dependem de fontes de símbolos nem de downloads; textos grandes e telas inteiras foram mantidos.
- Tela **Contribuir com o projeto**, com a chave Pix completa. Contribuir é opcional e não desbloqueia funcionalidades.
- Identificação do modelo atestado na tela inicial e uma página de compatibilidade com os limites dos testes.
- **Atualizar Port Doctor**: consulta releases estáveis de um repositório público da conta Fabriciopab, mostra versão/tamanho/origem e pede confirmação. Depois baixa, confere SHA-256 e a estrutura do ZIP e fecha o app para instalar automaticamente usando o instalador local conhecido. Preserva conf, backups, pacotes de compatibilidade e jogos.
- Não altera o firmware/dArkOS, não atualiza o PortMaster e não executa instaladores recebidos pela internet. Pacotes incorretos, downloads parciais, links/caminhos inseguros, nomes duplicados e versões anteriores são recusados. O SHA-256 compara a integridade com os metadados do GitHub; não é uma assinatura independente.
- Sem canal configurado ou release publicada, informa claramente a pendência e não inicia downloads. O nome do repositório pode ser configurado pelo gamepad, sempre sob Fabriciopab. Estado e descarte de pacote pendente também ficam no menu.

A partir da 0.11.1, o pacote vem configurado para o repositório oficial **Fabriciopab/Port-Doctor-R36S**. Consulte [PUBLICAR-ATUALIZACOES.md](PUBLICAR-ATUALIZACOES.md) para detalhes. Sem internet, a consulta informa o erro e preserva a instalação atual. Não desligue durante a instalação; uma falha de energia pode exigir reinstalar pelo menu Tools usando o backup preservado.

## Novidades da versão 0.9.0

- Gerenciador dos cartões `/roms` e `/roms2`: abrir pastas, propriedades, copiar com conferência SHA-256, recortar/colar no mesmo sistema de arquivos, renomear e criar pastas com teclado no gamepad. Listas grandes são paginadas. Não sobrescreve arquivos existentes.
- Exclusão recuperável e desinstalação: **Meus ports → jogo → Desinstalar este jogo** identifica a pasta e os launchers por metadados e referências estáticas. Mostra os caminhos, tamanho e aviso de saves antes da confirmação. Associação desconhecida/compartilhada é recusada; nesse caso, selecione os arquivos manualmente no gerenciador.
- A pasta completa, **inclusive saves internos**, vai para `.portdoctor-trash` no cartão. Saves externos, bibliotecas compartilhadas e backups de reparos não são removidos. A lixeira permite recuperar o conjunto ou apagá-lo definitivamente, com duas confirmações. Só a exclusão definitiva libera espaço. Recarregue o EmulationStation após desinstalar/restaurar.
- Limpeza conservadora: encontra metadados `Thumbs.db`/`.DS_Store` com assinatura reconhecida e registros nativos repetidos `tombstone_*`, com mais de 30 dias. Preserva o registro nativo mais recente. A busca é nas pastas imediatas dos ports; não é um apagador genérico do sistema. Resultados vão primeiro para a lixeira.
- Rede: informações de interfaces, IP, MAC, DNS/gateway quando disponíveis e estado do Wi-Fi. Liga/desliga somente o rádio via NetworkManager, confere o estado e mantém USB/Ethernet e redes salvas. Sem esse backend, informa a limitação sem alterar o firmware. Cadastro de rede/senha continua no menu do firmware.
- USB/OTG continua separado: habilitar o rádio Wi-Fi não troca o DTB nem torna o dongle disponível no modo USB peripheral. A função anterior de restaurar OTG continua com confirmação e reinício.

O gerenciador não usa root. Recusa caminhos de sistema, pastas principais do cartão, BIOS, PortMaster, a própria instalação, links selecionados e montagens de rede/internas. Não segue links dentro de pastas excluídas. Cada plano expira em 15 minutos e confere se os arquivos mudaram antes de agir. Transferências entre cartões são por cópia; confira e depois exclua a origem. Nenhum jogo real é apagado nos testes automatizados.

No exFAT do kernel antigo do R36S, movimentações usam reserva exclusiva e rechecagem do destino, pois o driver não aceita a opção atômica de não substituir nomes existentes. **Não faça transferências USB/rede simultâneas** às operações. A lixeira não substitui um backup fora do cartão e não protege contra falha física ou interrupção de energia. Casos interrompidos mantêm um registro para recuperação dos itens remanescentes.

Referência de rede: [comandos oficiais do NetworkManager](https://networkmanager.pages.freedesktop.org/NetworkManager/NetworkManager/nmcli.html). Rádio habilitado não garante internet. Informações MAC/IP são locais e não são enviadas a serviços externos.

## Recursos introduzidos na versão 0.8.0

- Páginas independentes em tela inteira: menu → função → detalhes → confirmação → resultado. Textos de 22 px, títulos de 26 px e rolagem para mensagens longas; B sempre volta.
- Cada port reúne diagnóstico, reparo recomendado, verificação e restauração. Não é necessário procurar o problema em outra aba.
- Bateria: leitura dos sensores, consumo instantâneo estimado, brilho em passos de 10 pontos, economia opcional e restauração. O modo econômico limita o brilho a 30% e usa `conservative` somente quando o kernel oferece esse modo. Pode reduzir desempenho; vale neste boot e o firmware pode substituí-lo.
- Ajustes de bateria têm registro anterior, confirmação de gravação e reversão em caso de falha parcial. Não alteram carregamento, tensão, limites de frequência, Wi-Fi ou USB. Porcentagem e saúde são valores do sensor, não uma avaliação do desgaste.
- Verificação de reparos detecta também novas falhas nativas e bibliotecas diferentes que falharam depois da primeira correção. Ausência de erros produz resultado **inconclusivo**, nunca garantia de que o jogo funciona.
- Hollow Knight: detecção de SIGBUS em registros `tombstone_*` próximos ao horário do log. O perfil gráfico leve testado não resolveu a falha e **não é distribuído como correção automática comprovada**. Saves permanecem intactos.

Referências técnicas: [interfaces de bateria do Linux](https://www.kernel.org/doc/html/latest/power/power_supply_class.html) e [Bogodroid](https://github.com/binarycounter/Bogodroid). O diagnóstico não promete corrigir todo executável incompatível ou conjunto de dados incompleto.

## Recursos mantidos

- Interface 640×480 controlada inteiramente pelo gamepad.
- Verificação de arquitetura, kernel, glibc, memória e armazenamento.
- Detecção da camada ARMHF em sistemas AArch64 multiarch.
- Verificação de SDL2, EGL/GLES, ALSA, DRM, Mali, framebuffer e uinput.
- Inventário do HarbourMaster, catálogos, runtimes e bibliotecas do PortMaster.
- Análise de arquivos ELF, arquitetura e dependências diretas de cada port.
- Identificação de bibliotecas e carregadores ausentes por arquitetura.
- Leitura do `log.txt` com identificação da causa provável, separando falhas fatais de mensagens secundárias.
- Detecção de pacotes GameMaker incompletos que não contêm `game.droid`, sem oferecer uma correção enganosa nem baixar dados proprietários.
- Reconstrução reversível de arquivos `.port` do GMLoader criados com compressão incompatível, preservando `game.droid`, áudio e grupos de recursos em modo armazenado.
- Rejeição de contadores de memória impossíveis produzidos por versões do GMLoader com `mallinfo` incompatível em AArch64, evitando ativação indevida de zram.
- Detecção de builds H700/ROCKNIX incompatíveis com o R36S RK3326/dArkOS, diferenciando incompatibilidade de plataforma de simples falta de biblioteca.
- Receitas extensíveis para ports conhecidos; Blazing Beaks inclui os runtimes oficiais `dotnet-8.0.12.squashfs` e `gmtoolkit.squashfs`.
- Reparo local de bibliotecas truncadas ou ausentes somente após validar ELF, arquitetura e compatibilidade do conjunto pelo carregador dinâmico. A fonte pode ser um runtime do PortMaster ou outro port instalado; os arquivos são copiados, nunca movidos. Dependências com caminho absoluto são corrigidas no executável por `patchelf`.
- Reparo automático em uma ação: interpreta o log, pré-testa o executável, fecha dependências indiretas, aplica o conjunto compatível e repete o teste do carregador.
- Validação e liberação de runtimes `.squashfs` incluídos no próprio port quando o launcher exige um runtime ausente do catálogo global do PortMaster.
- Correção local de inicialização EGL/GLES: valida arquitetura e símbolos do provedor Mali antes de configurar o SDL apenas no launcher afetado, sem trocar drivers do sistema.
- Recuperação de JARs incompletos pela união validada das classes e recursos locais preservados, sem baixar arquivos do jogo.
- Diagnóstico específico de áudio Vorbis destruído por patch incompleto e de bibliotecas nativas x86 dentro de JARs AArch64; fontes proprietárias ausentes nunca são fabricadas ou baixadas.
- Suporte a pacotes opcionais em `portdoctor/compat-packs`, aceitos somente com licença, origem, arquitetura e SHA-256 declarados.
- Bloqueio explícito de transplante automático de `libc`, carregadores, drivers Mali/EGL/GLES e outras bibliotecas centrais.
- Alternativa ALSA por port quando OpenAL/PipeWire não funciona no firmware.
- Detecção de `Device or resource busy` e reparo FNA/SDL: usa Pulse quando disponível ou ALSA `dmix`, liberando apenas clientes de áudio conhecidos do usuário.
- Diagnóstico de falta de memória em casos reconhecidos. Há uma receita legada de zram de 768 MB por port; o gerenciador manual oferece tamanhos proporcionais, com verificações adicionais. Zram é swap comprimida na RAM, não no cartão SD, e não garante que o jogo passe a funcionar. Não aplique os dois mecanismos como se fossem memória física adicional.
- Correção de permissões de launchers, scripts e executáveis ELF.
- Instalação de runtimes declarados usando `runtime_check` do HarbourMaster.
- Atualização dos catálogos e do backend HarbourMaster com confirmação.
- Backup automático, restauração e verificação do último reparo diretamente pela interface. A ausência do erro no log não substitui o teste real de imagem, áudio e controles.
- Registro automático da capa no `gamelist.xml`, com backup.
- Gerenciador comunitário de capas baseado no PortMaster Cover Fix validado no aparelho: reconhece `cover.*` e `cove.*`, preserva o original, cria uma cópia com o nome exato do launcher `.sh` e atualiza o `gamelist.xml`.
- Acesso aos cartões por cabo USB/RNDIS, com diagnóstico de compatibilidade, backup duplo do DTB, validação SHA-256, ativação e restauração pela interface.
- Instalação automática apenas das dependências USB ausentes (`device-tree-compiler`, `dnsmasq` e Samba), sem `apt upgrade`.
- Jogos em rede por SMB/CIFS, incluindo importação protegida da configuração, conexão, desconexão, diagnóstico e instalação isolada de `cifs-utils`.
- Assistente do Windows para preparar a pasta compartilhada, incluído em `portdoctor/extras/network-windows/`.
- Exportação de relatórios para `portdoctor/conf/reports/`.

Esta versão permanece experimental enquanto amplia a cobertura de firmwares e dispositivos.

## Política de segurança

O Port Doctor não executa `apt upgrade`, não substitui drivers, não sobrescreve `/lib` e não copia bibliotecas de uma arquitetura para outra. Runtimes são instalados pelo HarbourMaster, cada ELF é validado antes do uso e cada reparo pede confirmação na tela. Dependências sem uma origem PortMaster segura são apenas identificadas no relatório.

As alterações de launcher ficam registradas em `portdoctor/conf/backups/`. Para bibliotecas, a versão validada é colocada em `libs.portdoctor/` dentro do próprio port, mantendo o sistema-base intacto. Correções de áudio nunca encerram processos desconhecidos, de outro usuário ou o EmulationStation. A ação **Desfazer último reparo** restaura o launcher e remove somente os arquivos criados pelo Port Doctor. Mudanças de USB que reiniciam o aparelho exigem confirmação em duas etapas e só são liberadas quando DTB, UDC e módulos RNDIS passam na verificação.

O gerenciador de capas não apaga `cover.*` nem `cove.*`: cria uma cópia compatível com o nome do launcher e atualiza o campo `<image>` do `gamelist.xml`, depois de criar um backup restaurável. O módulo de rede guarda a credencial em `/etc/r36s-network` com acesso restrito e não inclui a senha nos diagnósticos.

A distribuição pública USB não cria senha padrão. Preserva contas Samba existentes; uma instalação sem conta precisa configurá-la pelo firmware ou usar SFTP gráfico com credenciais próprias. O Doctor ainda não possui tela de cadastro de senha Samba. Alterar USB/OTG não depende de criar uma nova senha.

## Controles

| Botão | Ação |
| --- | --- |
| L1 / R1 | Atalho contextual quando indicado no rodapé |
| D-pad | Navegar |
| A | Atualizar, analisar ou confirmar reparo |
| X | Exportar relatório |
| Y | Recarregar a seção |
| B | Voltar ou sair com confirmação |

No gerenciador: **A** entra na pasta/abre arquivo para operações, **X** abre as opções do item selecionado, **B** sobe uma pasta e **Y** recarrega. Copie/recorte um item, navegue até o destino e escolha **Colar aqui**. Em **Opções desta pasta**, crie uma pasta. O teclado na tela é controlado pelo direcional e A, com opções Espaço, Apagar, ABC e OK.

## Ferramentas integradas

No menu principal, escolha **Capas dos jogos**, **USB / OTG** ou **Jogos em rede**. Consultas somente leitura começam com A; ações que alteram arquivos mostram uma confirmação. Ativar ou restaurar o modo USB mostra uma segunda confirmação antes do reinício.

Para jogos em rede, execute no Windows o assistente localizado em `portdoctor/extras/network-windows/`. Copie o arquivo `Jogos-em-Rede-R36S.conf` criado por ele para `/roms/ports/portdoctor/conf/` ou `/roms/tools/`, depois escolha **Importar configuração de rede**.

## Instalação

O método recomendado é o [instalador pelo menu Tools](INSTALACAO.md), disponível nas releases oficiais. A presença no GitHub não significa aprovação no catálogo do PortMaster. Para teste manual, o pacote direto precisa ser extraído em `/roms/ports`, resultando em:

```text
/roms/ports/Port Doctor R36S.sh
/roms/ports/portdoctor/
```

O pacote já marca o launcher como executável. O próprio launcher também tenta restaurar sua permissão quando o firmware o inicia por meio do shell. O runtime `love_11.5` é preparado pelo PortMaster quando necessário.

O usuário final não precisa acessar SSH nem executar `chmod` na imagem dArkOSRE testada. Use o arquivo **Port-Doctor-R36S-Instalador** da [última release](https://github.com/Fabriciopab/Port-Doctor-R36S/releases/latest): extraia sua pasta em `/roms/tools` ou `/roms2/tools` e execute **Instalar Port Doctor R36S** pelo menu Tools. Esse instalador valida o payload, detecta o cartão correto, guarda a versão anterior, preserva relatórios e backups de reparo e aplica todas as permissões sem utilizar o fluxo `autoinstall` que apresentou travamento no dArkOSRE testado. Imagens que não permitem executar scripts do menu Tools precisam de um instalador compatível com o firmware; não é possível prometer isso para todo sistema.

A lixeira e os planos ficam na raiz de cada cartão, fora da instalação do app. Atualizar o Port Doctor não apaga a lixeira. O gerenciador e a rede usam o Python 3 já exigido pelas ferramentas existentes, sem dependências adicionais.

Na primeira abertura, o Port Doctor registra a capa e os metadados com backup do `gamelist.xml`. Reinicie o EmulationStation uma vez para recarregar a arte.

## Privacidade

Todos os diagnósticos são locais. Relatórios podem conter caminhos, versões do sistema e trechos de logs; revise-os antes de publicar.

## Agradecimentos

Obrigado às comunidades PortMaster, dArkOSRE e ArkOS pela documentação, runtimes e integração com handhelds Linux.
