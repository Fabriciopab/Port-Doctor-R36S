# R36S USB File Access

Acesso aos cartões do R36S pelo cabo USB usando rede RNDIS, sem remover o cartão e sem expor uma partição montada como USB Mass Storage.

**Créditos:** Fabricio Bastos (fabriciopab) by Byte Force Tecnologias  
**Licença:** MIT

> **Aparelho testado:** R36S V30 utilizando dArkOSRE. Outras revisões do
> R36S podem possuir DTB, controlador USB ou organização do sistema diferentes.
> Por segurança, o instalador verifica os requisitos antes de fazer alterações.

## Compatibilidade inicial

- Testado no R36S V30 com dArkOSRE;
- R36S com dArkOSRE;
- kernel com ConfigFS, UDC e módulos `libcomposite` e `usb_f_rndis`;
- DTB ativo em `/boot/rk3326-r36s-linux.dtb`;
- controlador USB em `/usb@ff300000`;
- ferramentas `dtc`, `fdtget`, `fdtput`, `dnsmasq`, SSH e, opcionalmente, Samba.

O instalador verifica esses requisitos e cancela sem trocar o DTB se algo não estiver correto.
Ele também reconhece uma instalação experimental anterior quando o DTB ativo foi
validado durante a instalação, permitindo migrar para a versão final sem perder o
backup OTG.

## Instalação

1. Descompacte a pasta inteira `R36S-USB-File-Access` dentro de `/roms/tools`.
2. No menu Tools, execute `Instalar R36S USB`.
3. Depois execute `Ativar USB por Cabo`.
4. O R36S trocará somente o modo USB do DTB e reiniciará.
5. Conecte um cabo de dados entre o computador e a porta OTG do R36S.

No Windows, aguarde o adaptador `Remote NDIS`. O endereço deve ser recebido automaticamente. Se necessário:

```powershell
ipconfig /renew "Ethernet 2"
ping 192.168.7.1
```

## Qual endereço devo utilizar?

O endereço do R36S é **fixo** e igual para todos os usuários deste projeto:

```text
IP do R36S: 192.168.7.1
```

O endereço recebido pelo computador pode variar entre `192.168.7.2` e
`192.168.7.20`. Esse endereço pertence ao computador e não deve ser colocado no
gerenciador de arquivos.

No gerenciador de arquivos do Windows, digite diretamente na barra de endereço:

```text
\\192.168.7.1\ROMS
```

Para o segundo cartão:

```text
\\192.168.7.1\ROMS2
```

No Port Doctor, a função de status USB mostra IP e estado da conexão. Abra o
caminho acima no Explorador do Windows. O atalho `.bat` do pacote USB
independente antigo não acompanha a distribuição integrada do Doctor.

Também é possível usar um cliente gráfico SFTP, como WinSCP, com o endereço USB do console e as credenciais pessoais configuradas no firmware. Não é necessário abrir um terminal para transferir arquivos.

### Usuário e senha no Windows

SSH/SFTP e Samba utilizam bancos de senhas separados. Esta distribuição
**não cria senha padrão nem altera senhas existentes**. Para o Explorador do
Windows, use a conta Samba já configurada no firmware. Se não houver uma,
configure uma conta pela ferramenta de contas/compartilhamento do firmware,
quando disponível, ou use um cliente gráfico SFTP com suas credenciais existentes.

O Doctor ainda não oferece um assistente próprio para cadastrar senha Samba.
Nesse caso o modo USB/OTG pode ser ativado, mas acesso pelo Explorador depende
da conta Samba. Não habilite acesso anônimo para contornar a autenticação.

O banco de usuários Samba é mantido em `/var/lib/samba/private`, separado
dos arquivos temporários do serviço USB em `/run`. O Windows deve autenticar
com sua conta Samba; não habilite a política de acesso de convidado inseguro.

Se o Windows tiver memorizado uma tentativa incorreta, execute antes de acessar:

```powershell
net use \\192.168.7.1 /delete /y
cmdkey /delete:192.168.7.1
```

## Voltar ao Wi-Fi

Execute `Restaurar USB e WiFi`. O backup OTG será validado, restaurado e o aparelho reiniciará. Depois do reinício, conecte o dongle Wi-Fi. Caso o Wi-Fi tenha sido desativado anteriormente, use a ferramenta `Wi-Fi Toggle` do dArkOSRE para habilitá-lo.

## USB por cabo e Wi-Fi ao mesmo tempo

Não é possível usar os dois no mesmo conector OTG. Em modo `peripheral`, o R36S é um dispositivo USB conectado ao computador. Para o dongle funcionar, a porta precisa estar em modo host/OTG. Um hub não remove essa limitação. Nos modelos em que a segunda USB-C é somente para energia, ela também não pode receber o dongle.

## Segurança e recuperação

- O DTB original é salvo em `/boot/r36s-usb-file-access/original.dtb` e também em `data/backups/original.dtb`.
- Todos os DTBs são validados por SHA-256 antes de uma troca.
- A ativação é recusada se o DTB ativo tiver sido alterado por uma atualização do sistema.
- Samba fica vinculado somente à interface `usb0` e não é publicado na rede Wi-Fi.
- Os compartilhamentos exigem autenticação com o usuário Samba `ark`.
- Nunca compartilhe o mesmo cartão simultaneamente como USB Mass Storage enquanto ele estiver montado pelo Linux.

Se o aparelho não iniciar, coloque o cartão do sistema no computador e copie `original.dtb` sobre `/boot/rk3326-r36s-linux.dtb`.

## Desinstalação

Primeiro restaure o modo normal. Depois, por SSH:

```bash
sudo r36s-usb-control uninstall --confirm
sudo reboot
```

Os backups são preservados.
