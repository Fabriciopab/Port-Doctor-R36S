# Como instalar o Port Doctor R36S

Guia por **fabriciopab**. Método testado no **R36S-V30-2025-11-18-2603 com dArkOSRE**. Outros firmwares/revisões precisam de validação.

## Antes de começar

- Faça backup dos saves e dos arquivos importantes do cartão.
- Use um cartão de jogos reconhecido pelo console, com espaço para extração e backup da instalação anterior.
- O firmware precisa oferecer PortMaster/HarbourMaster, Python 3 e execução de scripts pelo menu Tools. O runtime LÖVE 11.5 é solicitado ao PortMaster quando ausente; nesse caso é necessária internet.
- Mantenha alimentação estável. Não desligue nem retire o cartão durante a instalação.
- Não precisa abrir SSH, terminal ou digitar `chmod` no sistema testado.

## 1. Baixe o instalador certo

Abra **[a última release oficial](https://github.com/Fabriciopab/Port-Doctor-R36S/releases/latest)** e expanda **Assets** se necessário.

| Arquivo | Para que serve |
| --- | --- |
| `Port-Doctor-R36S-Instalador-vVERSAO.zip` | **Recomendado para instalar ou reinstalar pelo menu Tools.** |
| `Port-Doctor-R36S-vVERSAO.zip` | Pacote direto usado pelo atualizador; extração manual em `ports` para quem conhece a estrutura. |
| `Port-Doctor-R36S-Windows-Rede-vVERSAO.zip` | Assistente opcional para compartilhar jogos no Windows. Não é o app do console. |
| `portdoctor-r36s-source-vVERSAO.zip` / `Source code` | Código-fonte para desenvolvimento; não use como instalador. |
| `.sha256` | Conferência de integridade do pacote direto. |

## 2. Copie para o cartão

Desligue corretamente antes de retirar o cartão. No computador, extraia o instalador e copie **a pasta inteira** `Port Doctor R36S Installer` para `tools` na partição de jogos. O Windows usa uma letra de unidade: não crie uma pasta chamada `roms` dentro dela.

Exemplo se o cartão aparecer como `E:`:

```text
E:\tools\Port Doctor R36S Installer\Instalar Port Doctor R36S.sh
E:\tools\Port Doctor R36S Installer\portdoctor.zip
E:\tools\Port Doctor R36S Installer\LEIA-ME.txt
```

No console, corresponde a `/roms/tools/...` ou `/roms2/tools/...`. Mantenha os três arquivos juntos. **Não extraia o `portdoctor.zip` interno.** Ejete o cartão com segurança e coloque-o no R36S.

Se já tem transferência por rede/USB funcionando, pode copiar a mesma pasta por esse meio. Aguarde a transferência terminar antes de instalar. SSH não é requisito.

## 3. Instale no R36S

1. Abra **Tools / Ferramentas**.
2. Se necessário, entre em **Port Doctor R36S Installer** e selecione **Instalar Port Doctor R36S**.
3. Aguarde a conclusão. Atualizar pode demorar mais porque preserva configurações e backups; não interrompa por ficar alguns instantes sem mensagem nova.
4. Abra **Ports → Port Doctor R36S**. Se não aparecer, atualize a lista ou reinicie o EmulationStation pelo menu do firmware.

O instalador valida o pacote, detecta o cartão, organiza a pasta, aplica permissões e guarda a instalação anterior. Resultado esperado:

```text
/roms/ports/Port Doctor R36S.sh
/roms/ports/portdoctor/
```

Ou a mesma estrutura em `/roms2/ports`. Não deve ficar `ports/Port-Doctor-R36S-vVERSAO/portdoctor`.

## 4. Primeira abertura

O launcher prepara o runtime quando necessário, cria relatórios/configurações e registra capa e metadados. Se a capa não aparecer, reinicie o EmulationStation pelo menu do firmware para recarregar a lista.

Use o direcional, **A** para abrir/confirmar e **B** para voltar. Alterações pedem confirmação. Leia o rodapé para atalhos específicos; **X** exporta relatórios nas páginas de diagnóstico.

## Atualizar pelo próprio Doctor

Na 0.11.1 ou posterior, abra **Atualizar Port Doctor → Verificar atualizações**. A origem oficial é `Fabriciopab/Port-Doctor-R36S`. Leia a versão e confirme para baixar/instalar. O app fecha antes da troca de arquivos; depois abra novamente em Ports.

Se uma versão antiga pedir o repositório, escolha **Configurar repositório** e digite apenas `Port-Doctor-R36S` pelo teclado na tela. A conta é fixada em `Fabriciopab`. Alternativamente, repita a instalação pelo menu Tools com o instalador mais novo.

Configurações e backups de reparos são preservados. As instalações anteriores ficam em `ports/portdoctor-install-backups`. A lixeira fica fora do app e não é esvaziada pela atualização.

## Se não abrir ou não aparecer

| Sintoma | O que conferir |
| --- | --- |
| Instalador não aparece em Tools | Pasta no cartão correto, ZIP externo extraído, script junto do `portdoctor.zip`; recarregue a lista. Confira suporte a scripts em Tools. |
| Abre e fecha imediatamente | Estrutura sem pasta de versão extra; PortMaster/HarbourMaster disponíveis e runtime LÖVE instalado. |
| Download inicial falha | Internet no console. Endereço IP não garante acesso à internet. |
| Capas continuam antigas | Reinicie o EmulationStation após registrar as capas. |
| Não consegue gravar | Espaço livre e função **Armazenamento**. Não force reparos num cartão somente leitura ou com erros. |
| Atualização interrompida | Reinstale pelo menu Tools, mantendo backups, configurações e saves. |

Log principal: `ports/portdoctor/log.txt`. Relatórios: `ports/portdoctor/conf/reports/`. Copie pelo gerenciador/transferência disponível; não precisa de SSH para pedir ajuda. Remova dados pessoais antes de abrir uma [issue](https://github.com/Fabriciopab/Port-Doctor-R36S/issues).

Não use `autoinstall` do PortMaster como método recomendado nesta versão: ele apresentou travamento na imagem testada. Publicação no GitHub não significa aprovação no catálogo oficial PortMaster.

## Créditos e apoio

**fabriciopab** · [GitHub](https://github.com/Fabriciopab) · **fabricio@byteforce-ai.com**

**Pix: fabriciopab@hotmail.com** — contribuição voluntária, sem bloqueio de funcionalidades.
