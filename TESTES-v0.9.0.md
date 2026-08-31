# Validação 0.9.0 — 30/08/2026

## Arquivos e rede

- 29 testes Python: lista, propriedades, copiar/conferir, recortar, renomear, criar pasta, lixeira, restaurar, apagar e esvaziar lixeira; associação de launcher/pasta e saves internos; conflito de destino, plano alterado/expirado/reutilizado, falha parcial com reversão, preservação do registro após falha de exclusão, caminhos protegidos, montagens, links, processo em uso, limpeza com assinatura/idade e controle de rede simulado.
- R36S: todos os 29 aprovados no armazenamento temporário Linux. No cartão exFAT, 27 aprovados e 2 casos de links ignorados porque esse sistema de arquivos não cria links; os mesmos casos foram aprovados no temporário Linux.
- Encontrada e corrigida incompatibilidade `EINVAL` do `renameat2(RENAME_NOREPLACE)` no exFAT antigo. O caminho alternativo reserva exclusivamente um destino vazio e o reconfere antes de substituir somente a reserva. Não executar transferências externas simultâneas. Não é uma defesa contra um processo malicioso do mesmo usuário que altere os caminhos durante a operação.
- Nenhum jogo real foi excluído, movido ou desinstalado: testes usam diretórios descartáveis com nomes exclusivos. Os arquivos de teste foram removidos ao concluir.
- Rádio Wi-Fi testado no R36S por USB, sem dongle detectado: desativar → verificar → ativar → verificar → restaurar estado inicial habilitado. Endereço e conexão USB preservados. Conexão real a um ponto de acesso Wi-Fi não testada nesta rodada.
- Informações reais: interface USB, IP, MAC e estado do rádio lidos corretamente. Sem backend suportado, a alteração é recusada. Nenhuma senha de rede é consultada.

## Interface e regressões

- Compilação de todos os arquivos Lua por LuaJIT e dois testes de navegação sem gravações reais: interface anterior, JSON, navegação nos arquivos, copiar/colar, cancelamento de prévia, teclado e dupla confirmação de exclusão definitiva.
- Passeio automático de dez telas pelo LÖVE 11.5 do R36S; capturas do menu, navegador, limpeza, rede e teclado. Controle físico completo de todas as novas ações ainda depende de teste de uso pelo usuário.
- Os 12 testes anteriores de bateria e verificação de reparos foram mantidos/aprovados, assim como os ciclos de reparo de bibliotecas, capas e validação estrutural do pacote.

## Limites declarados

- Limpeza usa regras restritas, não “adivinha” tudo que seria inútil. Não remove saves, ROMs, BIOS, bibliotecas, runtimes, backups nem arquivos desconhecidos.
- O app não promete corrigir todos os jogos. Esta atualização não declara resolvida a falha SIGBUS anterior do Hollow Knight.
- Lixeira não libera espaço até esvaziar; exclusão definitiva não pode ser desfeita. Saves internos acompanham a pasta e são explicitamente mencionados na confirmação.
- Gerenciamento de arquivos é restrito aos cartões locais, sem root. Compartilhamentos de rede e partes críticas do firmware não são alvos de exclusão.

## Instalação no aparelho

- Instalador 0.9.0 aplicado no R36S; versão anterior guardada em `/roms/ports/portdoctor-install-backups/20260830-211226`.
- SHA-256 do instalador transferido: `5c5f4d711f7c784ffcb59db6d0deafadbc7925d3619085822b417b3f32040854`.
- Arquivos instalados `main.lua`, `file_manager.py` e `storage.lua` conferidos por SHA-256 contra a versão local.
- Launcher executável e abertura com `smoke test concluído`; consulta real do gerenciador retornou sucesso e 150 itens na primeira página de ports. Rádio Wi-Fi permaneceu habilitado.
