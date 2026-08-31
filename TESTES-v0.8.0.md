# Verificação da versão 0.8.0

Ambiente: R36S com dArkOSRE/Debian 13, AArch64, tela 640×480, LÖVE 11.5.

## Conferido

- Compilação dos arquivos Lua com LuaJIT e teste de navegação: abrir port, detalhes, cancelar, confirmar sem mensagem opcional, ação imediata, resultado, voltar, rolar e sair.
- 12 testes Python: economia/restore, idempotência, limites de brilho, preservação de alterações externas, reversão de falha parcial, hardware ausente, unidades dos sensores, rejeição de estado inválido, log antigo, nova falha, tombstone recente e ausência de erro sem falsa aprovação.
- Testes preexistentes de biblioteca local, backup/restore e capas, além da estrutura e permissões dos ZIPs.
- Capturas reais de seis páginas renderizadas no aparelho. `screenshot.png` é uma captura real do menu novo, não um desenho ilustrativo.
- Bateria no aparelho: brilho 51 → 48 e CPU `ondemand` → `conservative`; restauração confirmou 48 → 51 e `conservative` → `ondemand`.
- Instalador executado no dArkOSRE, preservando configuração, relatórios e backups. Recarregamento do menu ajustado para não pedir senha interativa.
- Inicialização do Doctor instalado e encerramento do teste automático.
- Análise real do Hollow Knight: `native_crash / SIGBUS`, reparo automático indisponível e diagnóstico nativo disponível.

## Limitações e pendências

- Hollow Knight **não foi corrigido**. A reprodução sob depurador confirmou SIGBUS com endereço inválido `0x0002000304020003`. Isso demonstra a falha, mas não identifica com segurança qual componente ou dado a provoca. O ajuste gráfico leve anterior não é oferecido como reparo comprovado.
- O teste do Doctor iniciado via SSH registrou avisos de restauração CRTC. As capturas renderizaram corretamente; a navegação física e o retorno visual ao menu devem ser confirmados pelo usuário no lançamento normal.
- Temperatura de bateria não exposta nesta imagem; mostrada como não informada. Não são calculadas saúde real da célula, calibração ou promessa de autonomia adicional.
- O modo econômico pode reduzir desempenho. Não há serviço persistente; firmware e jogos podem substituir os ajustes, e o registro de restauração é válido somente no mesmo boot.
- Instalação sem SSH/chmod depende da imagem permitir executar o instalador pelo menu Tools e oferecer as permissões necessárias. Validada na imagem acima; não se promete compatibilidade universal.

Créditos: fabriciopab · https://github.com/Fabriciopab · fabricio@byteforce-ai.com
