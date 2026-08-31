# Hollow Knight: reparo da superfície EGL — 0.11.4

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
- A confirmação de **jogabilidade prolongada, todos os controles e áudio** ainda precisa ser feita pelo usuário. Uma janela aberta ou um log sem crash não prova esses itens.

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
