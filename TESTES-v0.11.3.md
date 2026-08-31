# Verificações da versão 0.11.3

## Plataforma

Testes no **dArkOSRE**, baseado em Debian 13, aarch64, glibc 2.41, kernel 4.4.189, RK3326/Mali-G31. A revisão **R36S-V30-2025-11-18-2603** foi informada pelo mantenedor; não constitui certificação de outros aparelhos ou firmwares.

## Hollow Knight — investigação de 31/08/2026

- As dependências diretas do `unityloader` instalado foram resolvidas pelo carregador ELF.
- Os 293 arquivos verificáveis do pacote instalado conferiram com o manifesto local. Isso **não autentica o APK** e não comprova compatibilidade de versões.
- O depurador reproduziu `SIGBUS / BUS_ADRALN`, com tentativa de execução no endereço inválido `0x0002000304020003`.
- Preferências/cache isolados, retirada dos ajustes de coleta de memória e teste sem limite de textura reproduziram a mesma falha. Os saves originais foram preservados.
- Um ponto de observação de memória identificou escrita além da área temporária da rotina de renderização em `libunity.so`. A rotina recebeu uma máscara `0xffffffff`, excedendo os 14 campos da área reservada.
- Uma limitação **temporária em memória**, sob depurador, evitou essa falha durante a janela de teste. Isso ainda **não valida uma correção distribuível**, imagem correta ou jogabilidade.

O Doctor oferece **Verificar pacote Unity** e o diagnóstico nativo, mas não anuncia esse jogo como corrigido. Não são distribuídos o APK, bibliotecas proprietárias, saves nem dumps de memória.

## Validação da atualização

- Validação local: 96 testes Python, com quatro casos específicos de Linux pulados no Windows; três suítes de navegação Lua aprovadas.
- O ZIP real passou pela validação do atualizador protocolo 1, incluindo permissões executáveis, manuais internos e ausência de configurações/credenciais privadas.
- O novo verificador foi executado no R36S/dArkOSRE: 293 entradas conferiram; nenhuma ausente, diferente ou recusada.
- No aparelho, os 29 testes de arquivos/rede passaram sem casos pulados, incluindo as quatro verificações específicas de Linux. Os oito testes novos do verificador Unity também passaram.

- O tour da interface executou no R36S/dArkOSRE e terminou com `UI tour OK`, código zero. Houve avisos `Could not restore CRTC` na saída; esse teste não certifica retorno visual perfeito ao menu.
- A [automação de publicação](https://github.com/Fabriciopab/Port-Doctor-R36S/actions/runs/33398342339) concluiu todos os passos. Os cinco arquivos da [release 0.11.3](https://github.com/Fabriciopab/Port-Doctor-R36S/releases/tag/v0.11.3) foram baixados por HTTPS e tiveram tamanho/SHA-256 conferidos.
- Uma instalação de teste em pasta temporária representando a 0.11.0 recebeu a oferta 0.11.3 e preparou o download real pelo atualizador. Esse teste não executou o instalador.

- O pacote público validado foi transferido ao R36S por USB e instalado com código de saída zero, atualizando a 0.11.0 para 0.11.3. A conexão USB usada no teste estava sem resolução DNS para o GitHub; por isso, o download foi realizado no computador, sem modificar a rede do console.
- A abertura pelo launcher instalado concluiu `smoke test concluído`, com código zero. As mensagens `Killed` do encerramento do gptokeyb/PortMaster permaneceram no log, mas não houve traceback Lua nesse teste.
- Conferência pós-instalação: os 63 arquivos instaláveis comparados coincidiram com o pacote público; os 2.952 arquivos preexistentes de configuração, relatórios e histórico de reparos conferiram com o backup, sem diferenças. A instalação anterior ficou em `portdoctor-install-backups/`.
- O estado do atualizador confirmou versão 0.11.3, origem `Fabriciopab/Port-Doctor-R36S` e nenhuma instalação pendente.

As verificações históricas da [0.11.2](TESTES-v0.11.2.md) permanecem separadas. Nenhum desses testes declara o Hollow Knight corrigido.
