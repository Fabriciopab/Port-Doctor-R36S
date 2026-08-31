# Hollow Knight: reparos de abertura e imagem — 0.11.5

## Aplicar pelo próprio R36S

1. Instale/atualize o Port Doctor pelo menu Tools ou por **Atualizar Port Doctor**; não precisa de SSH ou `chmod` na imagem dArkOSRE testada.
2. Feche Hollow Knight. Em **Meus ports**, selecione o jogo e escolha **Corrigir**.
3. Confirme. O plano verifica o build e aplica o reparo EGL e o complemento gráfico necessário, guardando backup para cada etapa.
4. Se faltar o arquivo de preferências, o Doctor aplica apenas o EGL e informa a pendência: abra/feche o jogo uma vez e volte a analisar. Não inventa uma configuração para outro pacote.
5. Se o EGL já estava instalado, escolha **Corrigir tela roxa/preta** quando oferecido.
6. Abra o jogo e confirme personagem/cenário, áudio e controles. Para desfazer, use **Desfazer último reparo** uma vez por etapa; gráficos primeiro, depois EGL.

O pacote inclui o módulo necessário, mas **não inclui o jogo nem seus dados**. Pacotes com binários diferentes ou ambiente não reconhecido são recusados. A configuração de quadros e os efeitos de dano são preservados.

Testado em 31/08/2026 no **dArkOSRE (Debian 13, glibc 2.41)**, RK3326/Mali-G31. Revisão informada pelo mantenedor: **R36S-V30-2025-11-18-2603**. Não certifica outros aparelhos, todos os pacotes do jogo ou sessões prolongadas.

## O que foi encontrado

O pacote local e a instalação tinham os mesmos binários. Os 293 arquivos cobertos pelo manifesto local conferiram, sem que isso autentique o publicador. As dependências do carregador estavam disponíveis.

A instrumentação mostrou que SDL/KMSDRM destrói a superfície EGL inicial e cria outra para a mesma janela nativa. Este carregador guarda o identificador anterior e o entrega novamente a `eglMakeCurrent`. A chamada falha; a thread do jogo fica sem contexto atual, `glCreateShader` retorna zero e o motor acaba falhando. Um perfil gráfico mais leve e limpeza de cache isolada não resolveram esse problema.

## Como a receita funciona

1. Confere arquitetura, ambiente RK3326/Mali-G31 e SHA-256 do carregador, Unity e IL2CPP. Não depende somente do nome da pasta.
2. Valida o módulo incluído, exige o jogo fechado e reconhece uma única linha de execução do launcher.
3. Guarda o launcher original e um manifesto de restauração **antes** de alterar arquivos.
4. Copia um pequeno módulo original do Port Doctor para `portdoctor-egl/` dentro do jogo. Ativa `LD_AUDIT` somente no processo desse carregador.
5. O módulo observa criação/destruição de superfícies. Só redireciona um identificador cuja destruição e substituição foram observadas para o mesmo display e a mesma janela nativa. Não inventa sucesso em chamadas EGL.
6. O launcher verifica novamente os hashes a cada abertura. Se o usuário trocar o carregador, motor ou módulo, pede nova análise em vez de aplicar cegamente a receita.

Não modifica `libunity.so`, `libil2cpp.so`, APK, bibliotecas do Linux, clocks, saves ou caches. Não usa o antigo experimento de limitar uma máscara interna do Unity. Para desfazer, use **Desfazer último reparo** no mesmo port.

## Resultados e limites

- Sem redirecionamento, a superfície antiga foi recusada e os shaders receberam identificador zero.
- Com redirecionamento, o contexto passou a ficar ativo e os shaders/programas compilaram com sucesso.
- A leitura do framebuffer no próprio R36S passou a mostrar a **seleção de idioma**, em vez de uma imagem inteiramente preta.
- Testes limitados a 45 segundos também foram feitos com a configuração normal e um cache isolado.
- A receita foi aplicada ao port instalado com backup; um teste adicional com os arquivos, configuração e cache reais permaneceu aberto por 90 segundos, até o encerramento controlado do teste.
- Testes nativos sem GPU cobrem recriação, janelas diferentes, displays diferentes, falha do driver, identificador reutilizado e ponteiros de função.
- O usuário confirmou áudio e controles funcionando, mas relatou tela roxa. Isso confirma que o reparo EGL, sozinho, não corrige toda a apresentação gráfica deste pacote. Jogabilidade prolongada continua pendente.

### Complemento gráfico incluído na 0.11.5

Na mesma unidade dArkOSRE, em testes separados e limitados, com cópias das preferências e caches novos:

| Configuração | Imagem capturada do menu |
| --- | --- |
| `textureMaxDim=1024`, `ShaderQuality=1` | Fundo roxo; logotipo ausente |
| `textureMaxDim=0`, `ShaderQuality=1` | Logotipo visível; fundo preto |
| `textureMaxDim=0`, `ShaderQuality=2` | Logotipo e cenário do menu visíveis |

O complemento `unity-graphics` desativa a redução de texturas e seleciona desfoque Alto para **este build verificado**. A própria tela desse pacote orienta usar desfoque Alto quando o fundo fica preto. A comparação observada não identifica, por si só, qual operação interna do carregador causa a falha. Não é uma receita genérica para telas roxas em outros jogos.

Exige o reparo EGL já instalado, caminhos de configuração conhecidos e jogo fechado. Cria backup dos arquivos antes da escrita, preserva os demais valores das preferências e não modifica saves, áudio, controles, shaders, arquivos do jogo ou drivers. Pode aumentar o uso de memória; não altera clocks, zram ou serviços para compensar isso.

**Confirmação posterior do mantenedor:** personagem/cenário, áudio e controles estão funcionando na instalação real. Isso não certifica estabilidade prolongada nem outros pacotes ou aparelhos. O verificador não considera um log sem erros como prova de imagem correta. O complemento pode ser desfeito pelo backup do Port Doctor e acompanha o ZIP 0.11.5.

Não reduzir novamente `textureMaxDim` nem baixar `ShaderQuality` como tentativa genérica de desempenho: esses ajustes reintroduziram problemas de imagem nos testes.

### Pausa ao receber dano e desempenho

O mantenedor reconheceu a pausa de impacto como parte do comportamento do jogo, embora a percebesse um pouco mais longa neste port. O teste separado de limitar `VidTFR` a 60 piorou a experiência relatada e foi desfeito, voltando ao valor anterior da instalação de teste. **Esse experimento não faz parte da receita comunitária.** O Doctor não força 60 nem 400 quadros; mantém a preferência existente e não altera os efeitos de dano.

Houve limitação térmica ativa nas medições, mas isso não estabeleceu a causa da pausa específica. As proteções térmicas foram preservadas. Não há promessa de remover pausas de impacto nem de aumentar o desempenho com estes reparos de abertura/imagem.

O arquivo `dmesg_exit.log` não substitui o log de execução: a verificação dessa receita lê especificamente `log.txt`, exige que seja posterior ao reparo e procura a mensagem de contexto ativo. Novos crashes continuam impedindo um resultado positivo.

## Build reconhecido

`unityloader` SHA-256: `9c52d486b975e62ccab12ee480ffda37b92adcaa9e8d6ec9ced67f2916c3db5e`.

As demais impressões digitais e verificações estão em `tools/unity_egl.py`. Um build diferente é recusado, não corrigido por aproximação. O projeto não distribui o jogo nem seus dados.

## Fonte e compilação do módulo

Fonte própria MIT: `native/unity_egl_rebind.c`; testes: `native/test_unity_egl.c`. Módulo distribuído: `libexec/aarch64/unity-egl-rebind.so`. Pode ser compilado em Linux AArch64 com:

```sh
gcc -shared -fPIC -O2 -Wall -Wextra -Werror -pthread -Wl,-z,relro,-z,now unity_egl_rebind.c -o unity-egl-rebind.so
```

Uma recompilação com outra ferramenta pode produzir um hash diferente. Desenvolvedores devem executar os testes e atualizar o hash aprovado na receita; usuários finais não precisam compilar nada. A interface utilizada está documentada em [rtld-audit](https://man7.org/linux/man-pages/man7/rtld-audit.7.html).

Criado por **fabriciopab** · [GitHub](https://github.com/Fabriciopab) · fabricio@byteforce-ai.com. Apoio voluntário via Pix: **fabriciopab@hotmail.com**.
