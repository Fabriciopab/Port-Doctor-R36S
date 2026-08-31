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

Publicação, instalação e capturas da interface são verificadas separadamente. As verificações históricas da [0.11.2](TESTES-v0.11.2.md) não são evidência de instalação desta versão.
