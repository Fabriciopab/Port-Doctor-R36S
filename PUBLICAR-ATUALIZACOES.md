# Canal oficial de atualizações

Mantenedor: **fabriciopab** — https://github.com/Fabriciopab
Contato: fabricio@byteforce-ai.com — Pix opcional: fabriciopab@hotmail.com

## Preparação pelo mantenedor

1. O repositório oficial é **[Fabriciopab/Port-Doctor-R36S](https://github.com/Fabriciopab/Port-Doctor-R36S)**, público.
2. A partir da 0.11.1, `portdoctor/release.json` já define `github_repository` como `Port-Doctor-R36S`. Preserve `github_owner`, `app` e `update_protocol`. Versões antigas sem esse campo podem definir a origem em **Atualizar Port Doctor → Configurar repositório**, usando o gamepad, sem SSH.
3. Para uma nova versão estável, atualize a versão no manifesto, no app, no instalador, em `build_package.py` e nas verificações de `validate_project.py`. Compile com `python3 build_package.py` e execute `python3 validate_project.py`. O build inclui automaticamente a cópia do instalador local e gera um arquivo `.sha256`.
4. Prepare as notas em `releases/vMAJOR.MINOR.PATCH.md`. O fluxo `Publicar release` valida, empacota e publica quando `portdoctor/release.json` muda na `main`; também pode ser iniciado manualmente em Actions. Uma versão já publicada não é substituída. Para publicação manual, crie uma Release estável com tag `vMAJOR.MINOR.PATCH` e anexe o pacote direto **Port-Doctor-R36S-vMAJOR.MINOR.PATCH.zip**. O ZIP do instalador e o ZIP de código-fonte não servem como asset de autoatualização; anexe-os separadamente.
5. Confira o campo `digest` SHA-256 do asset na API de releases. Se estiver ausente, reenvie o asset. O Doctor recusa instalar sem esse valor. As versões de teste/prerelease não são oferecidas pelo botão de atualização.

## No console

Com internet funcionando, abra **Atualizar Port Doctor → Verificar atualizações**. O app mostra versão, origem e tamanho. Após confirmar, baixa e valida o pacote, fecha a interface e instala automaticamente. Depois abra novamente no menu Ports.

O atualizador preserva conf, backups, bibliotecas de compatibilidade locais e jogos. Ele atualiza apenas o Port Doctor, nunca o sistema operacional. Alimentação estável é necessária. A versão anterior fica em `ports/portdoctor-install-backups/`; registro e estado do atualizador ficam em `ports/.portdoctor-updates/`.

**Estado da atualização** mostra pendências e última tentativa. **Descartar pacote pendente** apaga somente o download e o agendamento: não restaura uma instalação já alterada. Se houver queda de energia durante a troca, use o instalador pelo menu Tools e consulte o backup. Repetições automáticas de uma tentativa interrompida são bloqueadas.

## Segurança e limites

- Conta de origem fixa Fabriciopab; apenas HTTPS e domínios de entrega do GitHub.
- Download limitado a 256 MiB e conteúdo extraído a 1,5 GiB; até 15.000 entradas.
- Recusa links, arquivos especiais, caminhos absolutos/relativos inseguros, nomes ambíguos/duplicados e conteúdo que substitua conf.
- Verifica hash e estrutura tanto ao preparar quanto ao instalar.
- O instalador executado é o já incluído na versão local, não um script recebido na release.
- Hash recebido da mesma origem detecta corrupção/troca de arquivo, mas não protege contra comprometimento da conta do mantenedor. Não equivale a assinatura criptográfica independente.

Referência: [API oficial de releases do GitHub](https://docs.github.com/en/rest/releases/releases#get-the-latest-release).

Modelo de referência do projeto: **R36S-V30-2025-11-18-2603**, com dArkOSRE. Não há garantia automática para clones, outras revisões ou todos os jogos.
