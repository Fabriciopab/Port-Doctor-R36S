# Desenvolvimento do Port Doctor R36S

## Arquitetura

O aplicativo usa LÖVE 11.5 e foi desenhado para a apresentação horizontal de 640×480 do R36S. O launcher segue as convenções do PortMaster e solicita o runtime oficial quando ele ainda não estiver instalado.

- `portdoctor/lovegame/main.lua`: interface, navegação e fila de verificações.
- `portdoctor/lovegame/src/diagnostics.lua`: diagnósticos somente leitura e análise de ports.
- `portdoctor/lovegame/src/logdoctor.lua`: assinaturas de falhas extraídas dos logs.
- `portdoctor/lovegame/src/recipes.lua`: runtimes e regras verificadas de ports conhecidos.
- `portdoctor/lovegame/src/repairs.lua`: ações confirmadas de permissões, runtimes, bibliotecas, áudio e atualização.
- `portdoctor/lovegame/src/util.lua`: execução de comandos, arquivos e formatação.
- `portdoctor/tools/repair_port.py`: alterações atômicas, validação ELF, backup e restauração.
- `portdoctor/portdoctor.gptk`: tradução dos controles físicos pelo gptokeyb.
- `portdoctor/conf/reports/`: relatórios criados no dispositivo.

## Princípios de segurança

- Correções de ports e atualizações sempre pedem confirmação.
- O launcher repara apenas a própria permissão de execução e registra metadados com backup.
- O aplicativo não faz atualização geral de pacotes nem substitui drivers. USB/rede podem solicitar a instalação isolada de dependências conhecidas, com confirmação.
- Bibliotecas do sistema em `/lib` nunca são sobrescritas; uma cópia validada é isolada no port.
- Runtimes e catálogos são gerenciados exclusivamente pelo HarbourMaster.
- Cada alteração de launcher tem manifesto de backup e pode ser desfeita.
- Reparos de áudio só encerram processos de uma lista restrita e pertencentes ao usuário atual.

## Testes

Validação estática do pacote:

Use Python 3 e Pillow (`python -m pip install Pillow`). Em Linux, instale também Lua 5.1 para os testes de interface e Bash para a validação de scripts. Defina `PORTDOCTOR_OUTPUTS` se quiser escolher a pasta de saída; o pipeline usa `dist/`.

```text
python build_package.py
python validate_project.py
lua5.1 test_ui.lua
lua5.1 test_ui_storage.lua
lua5.1 test_ui_updates.lua
```

Teste rápido com um runtime LÖVE 11.5 de desktop:

```text
PORTDOCTOR_SMOKE_TEST=1 love portdoctor/lovegame
```

O teste físico mínimo deve confirmar abertura, escala 640×480, D-pad, A/B/X/Y, L1/R1, criação de relatório e retorno limpo ao EmulationStation.

## Módulos atuais

- `battery.py` / `memory.py`: perfis temporários, sensores, brilho e zram própria.
- `file_manager.py`: planos, operações protegidas e lixeira por cartão.
- `network_status.py`: estado de interfaces e rádio via NetworkManager.
- `updater.py`: origem oficial, validação de release/ZIP e instalação após saída da UI.
- `integrations/`: capas, USB, rede e verificação de gravação.
- `extras/network-windows/`: preparador opcional executado pelo usuário no Windows.

O código próprio é MIT. Não inclua logs reais, credenciais, dados proprietários ou bibliotecas sem licença. Veja [CONTRIBUTING.md](CONTRIBUTING.md) e [publicação das releases](PUBLICAR-ATUALIZACOES.md).
