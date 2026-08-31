# Histórico de versões

## 0.11.2 — pacote compatível com o atualizador

- Documentação extra instalada em `portdoctor/docs/`, mantendo a lista de arquivos permitidos na raiz pelo protocolo 1 das versões anteriores.
- Teste de regressão valida o ZIP real com o mesmo validador do atualizador antes da publicação.
- Mantém funcionalidades, créditos, Pix e canal oficial da 0.11.1. Prefira esta versão à 0.11.1, cujo pacote direto era recusado pelo atualizador.

## 0.11.1 — publicação comunitária e canal oficial

- Canal de atualização configurado para Fabriciopab/Port-Doctor-R36S.
- Publicação USB sem senha padrão embutida: preserva contas existentes, informa quando Samba ainda não tem conta e não altera senhas do usuário.
- Página inicial com todos os módulos, capa, créditos, Pix e compatibilidade testada.
- Guia de instalação pelo menu Tools, sem SSH/chmod na imagem validada, e solução dos erros comuns de extração.
- Manual detalhado, orientações para suporte/contribuições e publicação de releases com instalador e preparador Windows.
- Nenhuma nova receita universal de reparo ou alteração automática de firmware/desempenho é introduzida nesta versão.

## 0.11.0 — perfis, zram e preparação da rede

- Quatro perfis temporários com restauração, sem overclock; bloqueios preventivos no modo Desempenho.
- Zram própria de 25/50/75% da RAM visível, sem tocar nas áreas do firmware e sem desativar páginas em uso.
- Guia inicial no menu Jogos em rede e ZIP separado do preparador Windows.
- Preparador recusa pastas amplas/sistema/links e rede pública; firewall limitado a Private/LocalSubnet.
- Empacotamento exclui conf, credenciais, logs e cache do Python; 24 novos testes de regressão.

## 0.10.0 — ícones, apoio ao projeto e atualizador

- Ícones vetoriais originais em menus, listas, arquivos e cabeçalhos; sem dependência de fontes de ícones.
- Tela Pix: fabriciopab@hotmail.com, contribuição opcional; créditos, GitHub e contato mantidos.
- Aviso do modelo atestado R36S-V30-2025-11-18-2603 no início e nas informações de compatibilidade.
- Atualizador com confirmação, release estável, HTTPS, tamanho/versão/SHA-256 e validação segura de ZIP. Instala somente após fechar a interface, usando cópia do instalador local, com backup.
- Configuração do repositório pelo gamepad, estado da tentativa e descarte do download pendente. Não baixa enquanto a origem oficial estiver indefinida.
- Instalações simultâneas bloqueadas; backups de instalação usam nomes únicos. O firmware e os jogos não são alvos da atualização.

## 0.9.0 — arquivos, desinstalação, limpeza e Wi-Fi

- Navegação nos cartões, cópia validada, recorte/colar, renomear e criar pastas pelo gamepad.
- Desinstalação associa pasta e launchers, recusa compartilhamentos conhecidos e mostra prévia com aviso de saves internos.
- Lixeira por cartão, recuperação nos locais originais e remoção definitiva com duas confirmações.
- Limpeza com assinatura e idade: metadados do explorador do computador e tombstones antigos repetidos; nenhum apagamento genérico do sistema.
- Prévia expira e é revalidada; destinos existentes, arquivos em uso detectados, caminhos protegidos, links selecionados e montagens internas são recusados.
- Compatibilidade com exFAT antigo: reserva exclusiva e rechecagem do destino quando o kernel não oferece rename sem substituição. Não faça transferências externas simultâneas.
- Rede/Wi-Fi separado do modo USB/OTG. Consulta IP/MAC e altera somente o rádio do NetworkManager, verificando o resultado.
- Instalação mantém permissões automáticas e preserva conf, backups e lixeira.

## 0.8.0 — telas legíveis e bateria

- Navegação por páginas independentes, fontes maiores e resultados com rolagem; sem barra lateral permanente nem painéis divididos.
- Diagnóstico, reparos e backup agrupados por port.
- Bateria: leitura dos sensores, brilho, economia conservadora e restauração protegida no mesmo boot.
- Testes de falha parcial, permissões, limites de brilho, idempotência e mudanças externas.
- Verificação diferencia alteração aplicada de funcionamento comprovado; novas falhas ou tombstones impedem falsa aprovação.
- Falha SIGBUS do Hollow Knight reconhecida. Perfil leve não comprovado foi retirado do reparo automático.

### Correções acumuladas desde 0.7.3

- O caso Fables of Talumos passa pelo mesmo reparo automático FFmpeg já validado no Blazing Beaks; o conjunto transitivo é instalado localmente e o pré-teste do carregador precisa ser aprovado.
- Logs GameMaker com `Unable to find game` agora identificam claramente a ausência de `game.droid`, em vez de tratar mensagens secundárias do runner como causa.
- Se o usuário colocar sua cópia legítima de `game.droid` dentro da pasta do port, o Port Doctor pode validá-la e instalá-la no destino esperado com backup e SHA-256. Dados proprietários não são distribuídos nem baixados.
- Segfaults de ports declarados para H700/ROCKNIX são distinguidos de falhas reparáveis quando o aparelho é um R36S RK3326/dArkOS, evitando alterações inúteis em bibliotecas e permissões.
- A tela do port mostra o motivo concreto quando não existe reparo automático seguro.
- Pacotes GMLoader criados com `game.droid`, áudio ou grupos de recursos comprimidos podem ser reconstruídos no modo armazenado, com validação ZIP, espaço livre mínimo, backup e restauração.
- Valores impossíveis do contador `mallinfo` do GMLoader em AArch64 são ignorados para não oferecer zram por engano.
- Uma reconstrução concluída antes de uma queda de conexão pode ser recuperada e registrada no histórico sem processar novamente todo o arquivo `.port`.
- Recursos externos ausentes, como `cinematics.dat` e `menu.dat`, aparecem como aviso separado: não são confundidos com falha do executável nem baixados automaticamente.
- Launchers com texto ou linhas vazias antes do `#!` são identificados e corrigidos com backup; isso cobre ports que o EmulationStation tenta abrir sem conseguir iniciar o script.
- Launchers que exigem um runtime desconhecido pelo catálogo global podem usar a imagem `.squashfs` incluída no próprio port, somente depois de validar cabeçalho, tamanho e caminho; o launcher original permanece no backup.
- Falhas `Can't load EGL/GL library` e `EGL not initialized` agora oferecem um reparo gráfico por port. O driver Mali é validado por arquitetura e pelos símbolos EGL/GLES antes de configurar o SDL, sem substituir drivers do sistema.
- O fluxo foi validado no RIOT: pacote `.port` reconstruído sem compressão, cabeçalho do launcher corrigido, runtime local liberado e OpenGL ES 3.2 inicializado até `Entering main loop`.
- JARs finais sem manifesto ou classes podem ser reconstruídos usando somente a base e os recursos preservados pelo próprio patch, com validação integral e backup. O Slay the Spire passou de `Invalid or corrupt jarfile` até a inicialização real do Java/Weston.
- Valores-padrão de resolução escritos como expansão de substring (`${VAR:640}`) são corrigidos para a sintaxe segura do shell (`${VAR:-640}`), evitando dimensões vazias.
- Falhas Vorbis `ov_open_callbacks error -132` agora identificam áudio destruído por uma compactação anterior incompleta e explicam a necessidade da fonte legítima original.
- Bibliotecas nativas x86/ELFCLASS32 dentro de JARs executados no R36S são separadas de JAR corrompido; o Port Doctor recusa transplantes inseguros e solicita a fonte original para aplicar o patch AArch64 oficial.

## 0.7.3 — Integração fiel do USB File Access v1.0.2

- Os três componentes executáveis internos agora são idênticos, byte a byte, aos arquivos originais do R36S USB File Access v1.0.2 fornecido pelo autor.
- A ponte do Port Doctor apenas valida, instala e chama o sistema original, sem alterar sua lógica de DTB, reinício ou gadget USB.
- Restauradas as diretivas Samba `private dir` e `passdb backend` removidas na adaptação anterior.
- O instalador cria `/var/lib/samba/private` com permissão restrita, preservando a credencial `ark` entre reinicializações.
- Ao atualizar uma instalação anterior, a própria ação de ativar migra o banco Samba e cria a credencial padrão somente se ela ainda não existir.
- Arquivos antigos instalados em `/usr/local/sbin` são atualizados automaticamente antes de ativar ou restaurar o modo USB.
- Resíduos da antiga verificação `pending-mode` deixam de bloquear o estado USB/Wi-Fi.

## 0.7.2 — Correção de falta de memória

- A análise reconhece o consumo informado por ports GMLoader e eventos de OOM em logs.
- Ports que ultrapassam aproximadamente 700 MB oferecem **Corrigir agora** na própria tela analisada.
- O reparo ativa 768 MB de zram comprimida sob demanda e ajusta o alocador do jogo, sem criar swap no cartão SD.
- O launcher recebe um auxiliar local executável, com backup e restauração pelo Port Doctor.
- A verificação reprova o reparo caso o kernel volte a encerrar processos por falta de memória.
- Validado fisicamente com Castlevania: Tales of Night Moon, que antes era encerrado perto de 831 MB e permaneceu em execução com zram ativa.

## 0.7.1 — Analisar e corrigir na mesma tela

- A seção **Meus ports** substitui o antigo fluxo separado de Dependências e Reparos.
- Depois da análise, a causa provável e o botão **A — Corrigir agora** aparecem juntos no painel do port.
- Pressionar A novamente abre a confirmação do reparo automático recomendado, sem navegar para outra aba.
- O resultado da execução também permanece na tela do port.
- A antiga seção Reparos foi renomeada para **Avançado** e continua disponível para restauração, verificação e ações específicas.

## 0.7.0 — Motor de reparo automático

- Nova ação **Corrigir port automaticamente**, voltada ao usuário final e sem necessidade de SSH.
- Interpretação do último log e pré-análise do executável quando o port não produz log útil.
- Instalação somente dos runtimes declarados que realmente estiverem ausentes.
- Fechamento transitivo e pré-teste final pelo carregador dinâmico em uma única operação.
- Suporte a pacotes de compatibilidade verificáveis por licença, arquitetura e SHA-256.
- Política de segurança impede substituição automática de bibliotecas centrais e drivers gráficos.
- Testes automatizados cobrem pacote compatível válido, hash, reparo automático, restauração e recusa de `libc`.

## 0.6.9 — Fechamento transitivo de bibliotecas

- O teste do carregador passa a usar o executável original que falhou, mesmo quando a biblioteca ausente é uma dependência indireta.
- Todas as bibliotecas realmente resolvidas na mesma fonte compatível são descobertas e copiadas em uma única operação.
- O caso Blazing Beaks passa a incluir de uma vez dependências indiretas como `libcodec2`, `libwavpack`, `libx264`, `libx265` e `libssh-gcrypt`.
- Cada arquivo adicional continua sendo validado como ELF da arquitetura correta e registrado no manifesto reversível.

## 0.6.8 — Correção da tela azul na verificação

- Corrigido o crash `main.lua:824: bad argument #1 to 'printf' (string expected, got nil)`.
- Ações imediatas da tela Reparos, como **Verificar resultado do reparo**, agora iniciam diretamente sem abrir uma confirmação vazia.
- A caixa de confirmação ganhou textos defensivos para impedir que metadados incompletos derrubem a interface.
- Mantida a migração segura do histórico implementada na versão 0.6.7.

## 0.6.7 — Histórico preservado e verificação clara

- Atualizações passam a preservar `conf/reports` e `conf/backups`, incluindo manifestos e arquivos necessários para verificar ou desfazer reparos anteriores.
- **Verificar resultado do reparo** informa claramente que primeiro é necessário aplicar um reparo e testar o jogo.
- Ações de verificar e desfazer agora mostram o motivo concreto quando não existe reparo ou backup pendente.
- Uma falha ao migrar o histórico cancela a atualização e restaura automaticamente a instalação anterior.

## 0.6.6 — Associação correta do launcher

- A pasta `blazingbeaks` agora é associada corretamente ao launcher `Blazing Beaks.sh`, mesmo com espaços e diferenças de capitalização.
- A associação também considera o nome conhecido pela receita e referências ao port dentro do launcher.
- Uma ação desativada passa a mostrar o motivo concreto, como `launcher não associado`, `arquitetura não identificada` ou `componente de reparo ausente`.
- O reparo FFmpeg da versão 0.6.5 permanece inalterado e passa a ficar acessível para o Blazing Beaks.

## 0.6.5 — Conjunto FFmpeg compatível entre ports

- O reparo agora procura bibliotecas compatíveis também nas pastas `lib/` e `libs/` de outros ports instalados.
- Dependências FFmpeg são tratadas como conjunto: `libavcodec`, `libavformat`, `libavutil`, `libswresample` e `libswscale` exigidas pelo executável vêm da mesma origem.
- Cada arquivo é validado como ELF e arquitetura correta; antes de gravar, o conjunto passa por `ld-linux --list` contra o executável real.
- As bibliotecas são copiadas para `libs.portdoctor/` do port quebrado. O port de origem e `/lib` permanecem intactos.
- O manifesto do backup registra todas as bibliotecas e o resultado da validação do carregador para restauração completa.

## 0.6.4 — Leitura real dos runtimes

- Instalação automática e confirmada de `squashfs-tools` quando o reparo precisa examinar runtimes `.squashfs`.
- Busca ampliada para `/opt/system`, `/opt/tools`, `/roms/tools`, `/roms2/tools` e instalações em `ports`.
- Extração compatível com bibliotecas versionadas e links simbólicos dentro do SquashFS.
- Em caso de falha, o relatório agora informa quais imagens de runtime foram efetivamente localizadas e examinadas.
- Varredura ELF otimizada para ler somente o cabeçalho em vez do executável inteiro.

## 0.6.3 — Correção do diagnóstico de biblioteca

- Corrigida a distinção entre o caminho em que o carregador encontrou uma biblioteca truncada e um `DT_NEEDED` realmente absoluto.
- O reparo não é mais cancelado quando `patchelf` confirma que o executável exige apenas o nome normal da biblioteca.
- O executável que falhou é extraído do log e associado ao reparo.
- `LD_LIBRARY_PATH` é reforçado imediatamente antes da linha que inicia o jogo, evitando que o launcher sobrescreva a configuração aplicada anteriormente.
- Teste automatizado reproduz o caso real de `gmloadernext.aarch64` com `libavcodec.so.58`.

## 0.6.2 — Diagnóstico de gravação

- Novo teste pela interface para confirmar escrita em `portdoctor/conf`, na pasta `ports` e em `/boot`.
- Detecção de cartão ou partição montada como somente leitura, espaço disponível e falha de `sudo` sem senha.
- Cada teste grava, relê e remove um arquivo temporário para comprovar persistência real.
- Resultado detalhado salvo em `portdoctor/conf/reports/storage-doctor-*.log`.
- A seção Ferramentas agora exibe a mensagem real do comando, inclusive quando uma alteração falha.

## 0.6.1 — Restauração USB para Wi-Fi

- Corrigida a elevação automática quando `ESUDO` está vazio no dArkOSRE.
- O controlador USB volta a usar `sudo -n` internamente, como o script independente validado no aparelho.
- Ações USB atualizam de forma atômica o controlador instalado antes da troca de modo.
- Restauração encerra o gadget USB, instala e valida o DTB em modo `otg` antes de reiniciar.
- Ativação e restauração registram auditoria e o modo aguardado para conferência após o boot.
- O status informa DTB gravado, modo do boot e se a mudança pendente foi confirmada.

## 0.6.0 — Capas validadas e reparos verificáveis

- Módulo de capas substituído pelo PortMaster Cover Fix enviado e validado no R36S.
- Reconhecimento de `cover.*` e `cove.*`, com cópia automática usando o nome exato do launcher `.sh`.
- Backup e restauração do `gamelist.xml` diretamente pela interface.
- Correção real de dependências ELF com caminho absoluto por `patchelf`, mantendo a biblioteca válida dentro do port e sem sobrescrever `/lib`.
- Instalação confirmada e automática de `patchelf` apenas quando esse tipo de reparo exigir a ferramenta.
- Reparos agora ficam como “alteração aplicada” até o usuário testar o jogo.
- Nova verificação compara o log posterior ao teste e reprova a correção se o mesmo erro reaparecer.
- Reparo de áudio ocupado também força OpenAL/ALSA `dmix` e passa pelo mesmo ciclo de verificação.

## 0.5.2 — Instalador de um clique

- Novo instalador pelo menu Tools, sem usar o fluxo `autoinstall` que travou na imagem testada.
- Validação integral do ZIP e bloqueio de caminhos inseguros antes da extração.
- Instalação em área temporária, backup da versão anterior e restauração em caso de falha.
- Detecção automática do cartão `/roms` ou `/roms2` usado pelo PortMaster.
- `items` atualizado para a forma atual do padrão PortMaster, sem barra final.
- Pacote principal reduzido aos arquivos de nível superior previstos pelo padrão oficial.

## 0.5.1 — Instalação sem SSH

- Bootstrap automático na primeira abertura para criar relatórios e backups.
- Correção automática e restrita das permissões dos scripts internos.
- Elevação pelo mecanismo fornecido pelo firmware, com alternativa `sudo -n`.
- Validação no pacote de todos os modos executáveis necessários.
- Guia de instalação local pelo diretório `autoinstall` do PortMaster.

## 0.5.0 — Capas, USB e jogos em rede

- Nova seção Ferramentas integrada à interface 640×480.
- Reconhecimento de capas `cover.png`, `cover.jpg`, `cover.jpeg` e equivalentes sem renomear ou apagar os originais.
- Atualização atômica do `gamelist.xml`, backup e restauração pela interface.
- Integração do R36S USB File Access com diagnóstico prévio, backup duplo de DTB, validação SHA-256 e confirmação dupla antes de reiniciar.
- Integração de jogos em rede SMB/CIFS com importação protegida, conexão, desconexão, diagnóstico e instalação isolada de `cifs-utils`.
- Assistente do Windows para compartilhamento em rede incluído no pacote.
- Capa atualizada com o LED central verde no R36S original.

## 0.4.0 — Áudio ocupado e capa R36S

- Reconhecimento da falha fatal FNA/SDL `Device or resource busy`.
- Reparo reversível que prefere Pulse e usa ALSA `dmix` como alternativa.
- Encerramento restrito a clientes de áudio conhecidos e pertencentes ao usuário atual.
- Teste automático do ciclo aplicar/restaurar para a nova receita.
- Capa refeita com o formato e os controles do R36S original.

## 0.3.1 — Compatibilidade com control.txt

- O launcher agora preserva seu próprio diretório em `PORTDOCTOR_SCRIPT_DIR`.
- Corrigido encerramento antes do log quando `device_info.txt` remove `SCRIPT_DIR`.

## 0.3.0 — Diagnóstico por log e reparos reversíveis

- Identificação da causa provável a partir de assinaturas do log.
- Distinção entre falhas fatais e mensagens secundárias de PipeWire/gptokeyb.
- Receita oficial de runtimes para Blazing Beaks.
- Reparo local de bibliotecas truncadas/ausentes com validação ELF e de arquitetura.
- Alternativa OpenAL/ALSA por launcher.
- Backup, manifesto e restauração do último reparo.
- Política explícita de nunca sobrescrever `/lib`.

## 0.2.0 — Dependências e reparos protegidos

- Nova capa e créditos de fabriciopab.
- Inventário de runtimes, bibliotecas e catálogos do PortMaster.
- Análise ELF por arquitetura e detecção de dependências diretas ausentes.
- Correção confirmada de permissões de scripts e executáveis.
- Instalação confirmada de runtimes pelo HarbourMaster.
- Atualização confirmada de catálogos e backend HarbourMaster.
- Registro automático de capa e metadados com backup do gamelist.

## 0.1.0 — MVP inicial

- Interface 640×480 para gamepad.
- Diagnóstico de arquitetura, glibc, memória e armazenamento.
- Verificação da camada ARMHF em sistemas AArch64.
- Verificação de SDL2, EGL/GLES, ALSA, DRM/Mali, framebuffer e uinput.
- Lista e análise somente leitura dos ports instalados.
- Exportação local de relatório de diagnóstico.
