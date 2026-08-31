import json
import importlib.util
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from PIL import Image


ROOT = Path(__file__).resolve().parent
OUTPUTS = Path(os.environ.get('PORTDOCTOR_OUTPUTS', ROOT.parents[1] / "outputs")).resolve()
INSTALLABLE = OUTPUTS / "Port-Doctor-R36S-v0.11.5.zip"
EASY_INSTALLER = OUTPUTS / "Port-Doctor-R36S-Instalador-v0.11.5.zip"


def require(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def validate_repair_cycle():
    helper = ROOT / "portdoctor/tools/repair_port.py"
    with tempfile.TemporaryDirectory(prefix="portdoctor-test-") as temporary:
        base = Path(temporary)
        port_home = base / "blazingbeaks"
        doctor_home = base / "portdoctor"
        pm_home = base / "PortMaster"
        launcher = base / "Blazing Beaks.sh"
        (port_home / "libs").mkdir(parents=True)
        (doctor_home / "conf").mkdir(parents=True)
        (pm_home / "libs").mkdir(parents=True)
        launcher.write_text(
            '#!/bin/bash\nGAMEDIR="/roms/ports/blazingbeaks"\n'
            'export LD_LIBRARY_PATH="$GAMEDIR/lib:$GAMEDIR/libs:${LD_LIBRARY_PATH:-}"\n'
            './gmloadernext.aarch64\n',
            encoding="utf-8",
        )
        elf = bytearray(8192)
        elf[:6] = b"\x7fELF\x02\x01"
        elf[18:20] = (183).to_bytes(2, "little")
        (pm_home / "libs/libavcodec.so.58").write_bytes(elf)

        common = [
            sys.executable,
            str(helper),
            "--launcher", str(launcher),
            "--port-home", str(port_home),
            "--doctor-home", str(doctor_home),
        ]
        repair_result = subprocess.run(
            common[:2] + ["repair-library"] + common[2:] + [
                "--pm-home", str(pm_home),
                "--library", "libavcodec.so.58",
                "--architecture", "aarch64",
                "--runtime", "gmtoolkit.squashfs",
                "--bad-path", "/lib/aarch64-linux-gnu/libavcodec.so.58",
                "--failed-executable", "./gmloadernext.aarch64",
            ],
            capture_output=True,
            text=True,
        )
        require(repair_result.returncode == 0,
                "reparo da biblioteca falhou: " + repair_result.stderr + repair_result.stdout)
        repaired = port_home / "libs.portdoctor/libavcodec.so.58"
        require(repaired.read_bytes() == elf, "biblioteca local não foi criada corretamente")
        require("Port Doctor: local libraries" in launcher.read_text(encoding="utf-8"), "launcher não foi ativado")
        require("Port Doctor: immediate local libraries" in launcher.read_text(encoding="utf-8"),
                "caminho local não foi reforçado antes do executável")
        subprocess.run(common[:2] + ["restore"] + common[2:], check=True, capture_output=True, text=True)
        require(not repaired.exists(), "restauração não removeu o arquivo criado")
        require("Port Doctor: local libraries" not in launcher.read_text(encoding="utf-8"), "launcher não foi restaurado")

        (pm_home / "libs/libavcodec.so.58").write_bytes(b"truncada")
        pack = doctor_home / "compat-packs/ffmpeg-test"
        (pack / "aarch64").mkdir(parents=True)
        pack_library = pack / "aarch64/libavcodec.so.58"
        pack_library.write_bytes(elf)
        (pack / "pack.json").write_text(json.dumps({
            "format": 1,
            "id": "ffmpeg-test",
            "license": "LGPL-2.1-or-later",
            "source": "https://example.invalid/source",
            "files": [{
                "name": "libavcodec.so.58",
                "path": "aarch64/libavcodec.so.58",
                "architecture": "aarch64",
                "sha256": hashlib.sha256(elf).hexdigest(),
            }],
        }), encoding="utf-8")
        packed = subprocess.run(
            common[:2] + ["repair-library"] + common[2:] + [
                "--pm-home", str(pm_home),
                "--library", "libavcodec.so.58",
                "--architecture", "aarch64",
            ], capture_output=True, text=True,
        )
        require(packed.returncode == 0 and str(pack_library) in packed.stdout,
                "pacote de compatibilidade validado não foi usado")
        subprocess.run(common[:2] + ["restore"] + common[2:], check=True, capture_output=True, text=True)
        shutil.rmtree(pack)

        (pm_home / "libs/libavcodec.so.58").write_bytes(elf)
        (port_home / "log.txt").write_text(
            "./gmloadernext.aarch64: error while loading shared libraries: "
            "libavcodec.so.58: cannot open shared object file: No such file or directory\n",
            encoding="utf-8",
        )
        automatic = subprocess.run(
            common[:2] + ["auto-repair"] + common[2:] + [
                "--pm-home", str(pm_home),
                "--architecture", "aarch64",
            ], capture_output=True, text=True,
        )
        require(automatic.returncode == 0 and "plano automático" in automatic.stdout,
                "reparo automático não tratou a falha registrada no log")
        require(repaired.is_file(), "reparo automático não criou a biblioteca local")
        subprocess.run(common[:2] + ["restore"] + common[2:], check=True, capture_output=True, text=True)

        (port_home / "log.txt").write_text(
            "./game.aarch64: error while loading shared libraries: "
            "libc.so.6: cannot open shared object file: No such file or directory\n",
            encoding="utf-8",
        )
        protected = subprocess.run(
            common[:2] + ["auto-repair"] + common[2:] + [
                "--pm-home", str(pm_home),
                "--architecture", "aarch64",
            ], capture_output=True, text=True,
        )
        require(protected.returncode != 0 and "núcleo ou ao driver" in protected.stderr,
                "reparo automático deveria recusar bibliotecas centrais")

        (pm_home / "libs/libavcodec.so.58").write_bytes(b"truncada")
        refused = subprocess.run(
            common[:2] + ["repair-library"] + common[2:] + [
                "--pm-home", str(pm_home),
                "--library", "libavcodec.so.58",
                "--architecture", "aarch64",
                "--runtime", "gmtoolkit.squashfs",
            ],
            capture_output=True,
            text=True,
        )
        require(refused.returncode != 0, "biblioteca truncada deveria ser recusada")
        require(not repaired.exists(), "uma biblioteca inválida não pode ser copiada")
        require("Port Doctor: local libraries" not in launcher.read_text(encoding="utf-8"), "falha segura alterou o launcher")

        subprocess.run(common[:2] + ["audio-alsa"] + common[2:], check=True, capture_output=True, text=True)
        require('ALSOFT_DRIVERS="alsa"' in launcher.read_text(encoding="utf-8"), "reparo ALSA não foi aplicado")
        subprocess.run(common[:2] + ["restore"] + common[2:], check=True, capture_output=True, text=True)
        require("ALSOFT_DRIVERS" not in launcher.read_text(encoding="utf-8"), "reparo ALSA não foi desfeito")

        subprocess.run(common[:2] + ["audio-busy"] + common[2:], check=True, capture_output=True, text=True)
        busy_launcher = launcher.read_text(encoding="utf-8")
        require("Port Doctor: audio busy start" in busy_launcher, "reparo de áudio ocupado não foi aplicado")
        require('AUDIODEV="dmix"' in busy_launcher, "fallback dmix não foi configurado")
        require('SDL_AUDIODRIVER="pulseaudio"' in busy_launcher, "fallback Pulse não foi configurado")
        require('ALSOFT_ALSA_DEVICE="dmix"' in busy_launcher, "OpenAL não foi direcionado ao dmix")
        log = port_home / "log.txt"
        log.write_text("OpenAudioDevice failed: Device or resource busy\n", encoding="utf-8")
        verification = subprocess.run(common[:2] + ["verify"] + common[2:], capture_output=True, text=True)
        require(verification.returncode != 0, "verificação deveria reprovar quando o erro reaparece")
        log.write_text("Inicialização concluída sem a falha de áudio tratada.\n", encoding="utf-8")
        subprocess.run(common[:2] + ["verify"] + common[2:], check=True, capture_output=True, text=True)
        subprocess.run(common[:2] + ["restore"] + common[2:], check=True, capture_output=True, text=True)
        require("Port Doctor: audio busy start" not in launcher.read_text(encoding="utf-8"), "reparo de áudio ocupado não foi desfeito")

        game_source = port_home / "minha-copia/game.droid"
        game_source.parent.mkdir(parents=True)
        game_source.write_bytes(b"GAME" * (1024 * 1024 // 4))
        game_destination = port_home / "saves/game.droid"
        game_install = subprocess.run(
            common[:2] + ["install-game-data"] + common[2:] + ["--source", str(game_source)],
            capture_output=True, text=True,
        )
        require(game_install.returncode == 0, "instalação local de game.droid falhou: " + game_install.stderr)
        require(game_destination.read_bytes() == game_source.read_bytes(), "game.droid instalado difere da origem")
        subprocess.run(common[:2] + ["restore"] + common[2:], check=True, capture_output=True, text=True)
        require(not game_destination.exists(), "restauração não removeu game.droid criado pelo Port Doctor")

        game_archive = port_home / "test.port"
        with ZipFile(game_archive, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("assets/game.droid", b"GAME" * 4096)
            archive.writestr("assets/sound.ogg", b"OGG" * 4096)
        original_archive = game_archive.read_bytes()
        repacked = subprocess.run(
            common[:2] + ["repack-game-archive"] + common[2:], capture_output=True, text=True,
        )
        require(repacked.returncode == 0, "reconstrução do .port falhou: " + repacked.stderr)
        with ZipFile(game_archive) as archive:
            require(all(info.is_dir() or info.compress_type == ZIP_STORED for info in archive.infolist()),
                    "pacote reconstruído ainda contém arquivos comprimidos")
        subprocess.run(common[:2] + ["restore"] + common[2:], check=True, capture_output=True, text=True)
        require(game_archive.read_bytes() == original_archive, "restauração não repôs o .port original")

        launcher.write_text(
            "Riot.sh\n\n#!/bin/bash\necho funcionando\n", encoding="utf-8"
        )
        launcher_header = subprocess.run(
            common[:2] + ["repair-launcher-header"] + common[2:], capture_output=True, text=True,
        )
        require(launcher_header.returncode == 0, "correção do cabeçalho do launcher falhou")
        require(launcher.read_text(encoding="utf-8").startswith("#!/bin/bash\n"),
                "o shebang não foi colocado na primeira linha")
        subprocess.run(common[:2] + ["restore"] + common[2:], check=True, capture_output=True, text=True)
        require(launcher.read_text(encoding="utf-8").startswith("Riot.sh\n"),
                "restauração não repôs o prefixo original do launcher")

        local_runtime = port_home / "lib/arm64-v8a/gmloadernext.squashfs"
        local_runtime.parent.mkdir(parents=True, exist_ok=True)
        local_runtime.write_bytes(b"hsqs" + b"\0" * (1024 * 1024))
        launcher.write_text(
            '#!/bin/bash\nGAMEDIR="/roms/ports/riot"\nRUNTIME="gmloadernext.squashfs"\n'
            'if [ ! -f "$controlfolder/libs/$RUNTIME" ]; then\n  echo missing\nfi\n'
            'if [ ! -f "$controlfolder/libs/$RUNTIME" ]; then\n  exit 1\nfi\n',
            encoding="utf-8",
        )
        runtime_repair = subprocess.run(
            common[:2] + ["repair-local-runtime"] + common[2:]
            + ["--runtime", "gmloadernext.squashfs"], capture_output=True, text=True,
        )
        require(runtime_repair.returncode == 0, "fallback de runtime local falhou: " + runtime_repair.stderr)
        runtime_launcher = launcher.read_text(encoding="utf-8")
        require(runtime_launcher.count("Port Doctor: local runtime fallback") == 2,
                "todas as verificações do runtime deveriam aceitar a cópia local")
        require('$GAMEDIR/lib/arm64-v8a/gmloadernext.squashfs' in runtime_launcher,
                "launcher não aponta para o runtime local validado")
        subprocess.run(common[:2] + ["restore"] + common[2:], check=True, capture_output=True, text=True)

        base_jar = port_home / "tmp/cleaned.zip"
        base_jar.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(base_jar, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\nMain-Class: game.Main\n")
            archive.writestr("game/Main.class", b"classe")
        broken_jar = port_home / "desktoppatched.jar"
        with ZipFile(broken_jar, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("images/title.png", b"imagem preservada")
        (port_home / "log.txt").write_text(
            f"Error: Invalid or corrupt jarfile {broken_jar}\n", encoding="utf-8"
        )
        java_repair = subprocess.run(
            common[:2] + ["repair-java-archive"] + common[2:], capture_output=True, text=True,
        )
        require(java_repair.returncode == 0, "reconstrução do JAR falhou: " + java_repair.stderr)
        with ZipFile(broken_jar) as archive:
            names = set(archive.namelist())
            require("META-INF/MANIFEST.MF" in names and "game/Main.class" in names,
                    "JAR reconstruído não contém manifesto e classe principal")
            require(archive.read("images/title.png") == b"imagem preservada",
                    "JAR reconstruído perdeu os recursos locais")
        subprocess.run(common[:2] + ["restore"] + common[2:], check=True, capture_output=True, text=True)


def validate_cover_cycle():
    helper = ROOT / "portdoctor/integrations/covers/portmaster-cover-fix.sh"
    bash = shutil.which("bash")
    require("create_launcher_cover_aliases" in helper.read_text(encoding="utf-8"),
            "normalização de cover/cove ausente")
    require("-iname 'cove.png'" in helper.read_text(encoding="utf-8"),
            "variante cove.* não está coberta")
    if not bash:
        return
    with tempfile.TemporaryDirectory(prefix="portdoctor-cover-test-") as temporary:
        base = Path(temporary)
        ports = base / "ports"
        doctor = ports / "portdoctor"
        game = ports / "mygame"
        doctor.mkdir(parents=True)
        game.mkdir()
        launcher = ports / "My Game.sh"
        launcher.write_text('#!/bin/bash\nGAMEDIR="/roms/ports/mygame"\n', encoding="utf-8")
        cover = game / "cover.JPEG"
        cover.write_bytes(b"preservar esta imagem")
        gamelist = ports / "gamelist.xml"
        original = b'<?xml version="1.0"?><gameList><game><path>./My Game.sh</path><name>Meu jogo</name></game></gameList>'
        gamelist.write_bytes(original)

        def shell_path(path: Path) -> str:
            converted = subprocess.run(
                [bash, "-lc", 'cygpath -u "$1" 2>/dev/null || printf "%s" "$1"', "_", str(path)],
                check=True, capture_output=True, text=True,
            )
            return converted.stdout.strip()

        environment = dict(os.environ)
        environment.update({
            "PORTS_PATH": shell_path(ports),
            "PORTDOCTOR_HOME": shell_path(doctor),
            "SKIP_RESTART": "1",
        })
        subprocess.run([bash, shell_path(helper), "sync"], check=True, env=environment,
                       capture_output=True, text=True)
        tree = ElementTree.parse(gamelist)
        image = tree.findtext("./game/image")
        alias = ports / "My Game.JPEG"
        require(image == "./My Game.JPEG", "capa normalizada não foi associada ao launcher")
        require(alias.read_bytes() == cover.read_bytes(), "cópia com nome do launcher não foi criada")
        require(cover.read_bytes() == b"preservar esta imagem", "imagem original não pode ser alterada")

        subprocess.run([bash, shell_path(helper), "restore"], check=True, env=environment,
                       capture_output=True, text=True)
        require(gamelist.read_bytes() == original, "restauração de capas não repôs o gamelist original")


def main():
    metadata = json.loads((ROOT / "port.json").read_text(encoding="utf-8"))
    require(metadata["version"] == 2, "port.json precisa usar o formato 2")
    require(metadata["attr"].get("exp") is True, "versão comunitária deve permanecer experimental")
    require("fabriciopab" in metadata["attr"]["porter"], "crédito do autor ausente")
    require("não requer SSH" in metadata["attr"]["inst"], "instalação autônoma não está documentada")
    require("Port Doctor R36S.sh" in metadata["items"], "launcher ausente de items")
    require("portdoctor/" in {item.rstrip("/") + "/" for item in metadata["items"]}, "pasta do port ausente de items")

    ElementTree.parse(ROOT / "gameinfo.xml")

    for filename in ("screenshot.png", "cover.png"):
        with Image.open(ROOT / filename) as image:
            require(image.size == (640, 480), f"{filename} precisa ser 640x480")

    shell_files = [
        ROOT / "Port Doctor R36S.sh",
        ROOT / "portdoctor/integrations/network/network-manager.sh",
        ROOT / "portdoctor/integrations/covers/portmaster-cover-fix.sh",
        ROOT / "portdoctor/integrations/system/storage-doctor.sh",
        ROOT / "portdoctor/integrations/usb/usb-bridge.sh",
        ROOT / "portdoctor/integrations/usb/install.sh",
        ROOT / "portdoctor/integrations/usb/payload/r36s-usb-control",
        ROOT / "portdoctor/integrations/usb/payload/r36s-usb-gadget",
        ROOT / "portdoctor/tools/zram-helper.sh",
        ROOT / "installer/Instalar Port Doctor R36S.sh",
    ]
    for path in [*shell_files, ROOT / "portdoctor/portdoctor.gptk"]:
        require(b"\r\n" not in path.read_bytes(), f"{path.name} precisa usar finais de linha LF")

    launcher_text = (ROOT / "Port Doctor R36S.sh").read_text(encoding="utf-8")
    require("bootstrap_installation" in launcher_text, "bootstrap de primeira abertura ausente")
    require("sudo -n" in launcher_text, "alternativa automática de elevação ausente")
    require("chmod -R +x" not in launcher_text, "launcher não deve tornar todos os arquivos executáveis")
    require('find "$GAMEDIR/tools" -type f -name \'*.sh\' -exec chmod a+rx' in launcher_text,
            "bootstrap precisa tornar auxiliares shell executáveis sem SSH")
    main_lua = (ROOT / "portdoctor/lovegame/main.lua").read_text(encoding="utf-8")
    require("if action.immediate then" in main_lua and "local function openAction" in main_lua,
            "todas as ações devem usar a página comum com suporte a ações imediatas")
    require('confirmation = confirmation or "Executar esta ação de manutenção?"' in main_lua,
            "caixa de confirmação precisa aceitar texto ausente sem encerrar a interface")
    for marker in ("recommendedRepairAction", "Corrigir problema identificado", "Ler diagnóstico completo",
                   "lg.newFont(22)", "p.maxScroll", "id='battery'", "Isso ainda NÃO confirma"):
        require(marker in main_lua, f"reparo recomendado na tela do port ausente: {marker}")
    usb_installer = (ROOT / "portdoctor/integrations/usb/install.sh").read_text(encoding="utf-8")
    for package in ("device-tree-compiler", "dnsmasq", "samba"):
        require(package in usb_installer, f"dependência USB automática ausente: {package}")
    tools_lua = (ROOT / "portdoctor/lovegame/src/tools.lua").read_text(encoding="utf-8")
    require('return "sudo -n "' in tools_lua, "fallback de elevação das ferramentas ausente")
    repairs_lua = (ROOT / "portdoctor/lovegame/src/repairs.lua").read_text(encoding="utf-8")
    require("squashfs-tools" in repairs_lua and "command -v unsquashfs" in repairs_lua,
            "dependência de leitura dos runtimes não é preparada automaticamente")
    require("launcher não associado" in repairs_lua and "disabledReason" in repairs_lua,
            "ação desativada precisa informar o motivo real")
    require("Esta ação não faz o reparo" in repairs_lua,
            "verificação precisa ser distinguida da aplicação do reparo")
    for marker in ("memoryCommand", "memory_pressure", "Ativar memória comprimida", "768 MB zram"):
        require(marker in repairs_lua, f"reparo de falta de memória ausente da interface: {marker}")
    logdoctor_lua = (ROOT / "portdoctor/lovegame/src/logdoctor.lua").read_text(encoding="utf-8")
    for marker in ("Total memory used", "memory_pressure", "Memória insuficiente"):
        require(marker in logdoctor_lua, f"diagnóstico de memória ausente: {marker}")
    for marker in ("missing_game_data", "game.droid não foi encontrado", "Unable to find game!!".lower()):
        require(marker in logdoctor_lua.lower(), f"diagnóstico de dados GameMaker ausentes: {marker}")
    diagnostics_lua = (ROOT / "portdoctor/lovegame/src/diagnostics.lua").read_text(encoding="utf-8")
    for marker in ("findPortLaunchers", "normalizedName", "recipes.forPort(name)"):
        require(marker in diagnostics_lua, f"associação flexível de launcher ausente: {marker}")
    for marker in ("platform_incompatible", "H700/ROCKNIX", "RK3326"):
        require(marker in diagnostics_lua, f"diagnóstico de plataforma incompatível ausente: {marker}")
    repair_helper = (ROOT / "portdoctor/tools/repair_port.py").read_text(encoding="utf-8")
    for marker in ("FFMPEG_SONAME", "validate_local_bundle", "sibling / \"lib\"", "loader_validation",
                   "source_libraries", "failed_target", "compat_pack_candidates", "command_auto_repair",
                   "PROTECTED_LIBRARY", "command_memory_zram", "oom_snapshot", "memory-zram",
                   "command_install_game_data", "install-game-data", "MIN_GAME_DATA_SIZE",
                   "command_repack_game_archive", "repack-game-archive", "ZIP_STORED",
                   "command_repair_local_runtime", "repair-local-runtime", "valid_squashfs",
                   "command_graphics_provider", "graphics-provider", "find_graphics_provider",
                   "command_repair_java_archive", "repair-java-archive", "validate_executable_jar",
                   "command_repair_shell_defaults", "repair-shell-defaults"):
        require(marker in repair_helper, f"reparo de conjunto FFmpeg incompleto: {marker}")
    easy_installer_text = (ROOT / "installer/Instalar Port Doctor R36S.sh").read_text(encoding="utf-8")
    require('cp -a "$BACKUP_DIR/portdoctor/conf/." "$TARGET_HOME/conf/"' in easy_installer_text,
            "atualização precisa preservar manifestos e relatórios")
    require('find "$TARGET_HOME/tools" -type f -name \'*.sh\' -exec chmod a+rx' in easy_installer_text,
            "instalador precisa aplicar permissão aos auxiliares sem SSH")
    usb_bridge = (ROOT / "portdoctor/integrations/usb/usb-bridge.sh").read_text(encoding="utf-8")
    # Public distributions preserve existing accounts, never set shared passwords.
    for usb_source in (usb_bridge, (ROOT / 'portdoctor/integrations/usb/install.sh').read_text(encoding='utf-8')):
        require('smbpasswd -s -a' not in usb_source, 'distribuição pública não pode cadastrar senha Samba embutida')
    require('exec sudo -n /bin/bash "$0" "$@"' in usb_bridge,
            "ponte USB não se eleva como o script independente")
    for marker in ("CONTROL_SHA", "GADGET_SHA", "SERVICE_SHA", "verify_original_payload",
                   "prepare_v102_state", "install -d -m 0700 /var/lib/samba/private"):
        require(marker in usb_bridge, f"validação do pacote USB v1.0.2 ausente: {marker}")
    usb_expected = {
        "r36s-usb-control": "58763e2acadb6ba69fe7d9f93b19e14b950c0d32ad299ec4cac26c3b737498e3",
        "r36s-usb-gadget": "2e5ebc8c2cc7aeecb67d2ccbab3563ea4f696d712b4e4f676f3c4cb2ba63da57",
        "r36s-usb-gadget.service": "98b76e92e2a8803feadbae65a645b5363b56619fceaf9e4e8551cab1be97f929",
    }
    for name, expected in usb_expected.items():
        payload = ROOT / "portdoctor/integrations/usb/payload" / name
        require(hashlib.sha256(payload.read_bytes()).hexdigest() == expected,
                f"componente USB não corresponde ao original v1.0.2: {name}")
    usb_installer_full = (ROOT / "portdoctor/integrations/usb/install.sh").read_text(encoding="utf-8")
    require("install -d -m 0700 /var/lib/samba/private" in usb_installer_full,
            "instalador USB precisa preservar o banco Samba da v1.0.2")
    usb_gadget = (ROOT / "portdoctor/integrations/usb/payload/r36s-usb-gadget").read_text(encoding="utf-8")
    for marker in ("private dir = /var/lib/samba/private", "passdb backend = tdbsam"):
        require(marker in usb_gadget, f"configuração Samba v1.0.2 ausente: {marker}")
    storage_doctor = (ROOT / "portdoctor/integrations/system/storage-doctor.sh").read_text(encoding="utf-8")
    for marker in ("test_user_write", "test_root_write", "RESULTADO: APROVADO"):
        require(marker in storage_doctor, f"teste de gravação ausente: {marker}")

    bash = shutil.which("bash")
    if bash:
        for shell_file in shell_files:
            subprocess.run([bash, "-n", str(shell_file)], check=True)

    for helper in ("repair_port.py", "battery.py", "memory.py", "file_manager.py", "network_status.py", "updater.py"):
        subprocess.run([sys.executable, "-m", "py_compile", str(ROOT / "portdoctor/tools" / helper)], check=True)
    validate_repair_cycle()
    validate_cover_cycle()
    subprocess.run([sys.executable, str(ROOT / 'test_v080.py')], check=True)
    subprocess.run([sys.executable, str(ROOT / 'test_v090.py')], check=True)
    subprocess.run([sys.executable, str(ROOT / 'test_v0100.py')], check=True)
    subprocess.run([sys.executable, str(ROOT / 'test_v0110.py')], check=True)
    subprocess.run([sys.executable, str(ROOT / 'test_unity_audit.py')], check=True)
    subprocess.run([sys.executable, str(ROOT / 'test_unity_egl.py')], check=True)
    subprocess.run([sys.executable, str(ROOT / 'test_unity_graphics.py')], check=True)
    release = json.loads((ROOT / 'portdoctor/release.json').read_text())
    require(release['version'] == '0.11.5', 'versão interna não confere')
    require(release['pix'] == 'fabriciopab@hotmail.com', 'chave Pix divergente')
    require(release['github_owner'] == 'Fabriciopab' and release['github_repository'] == 'Port-Doctor-R36S',
            'canal oficial de atualização divergente')
    require(release['tested_model'] == 'R36S-V30-2025-11-18-2603', 'modelo atestado divergente')
    require(release['tested_firmware'] == 'dArkOSRE', 'sistema testado divergente')
    require((ROOT / 'installer/Instalar Port Doctor R36S.sh').read_bytes() ==
            (ROOT / 'portdoctor/tools/update-install.sh').read_bytes(), 'instalador local do atualizador divergente')

    require(INSTALLABLE.is_file(), "execute build_package.py antes da validação")
    updater_spec = importlib.util.spec_from_file_location('release_validator', ROOT / 'portdoctor/tools/updater.py')
    updater_module = importlib.util.module_from_spec(updater_spec)
    updater_spec.loader.exec_module(updater_module)
    require(updater_module.validate_zip(INSTALLABLE, release['version']) > 0,
            'pacote real precisa ser aceito pelo atualizador protocol 1')
    with ZipFile(INSTALLABLE) as archive:
        names = set(archive.namelist())
        require('portdoctor/docs/INSTALACAO.md' in names and 'INSTALACAO.md' not in names,
                'manual deve ficar dentro do app para compatibilidade com atualizadores antigos')
        required = {
            "Port Doctor R36S.sh",
            "port.json",
            "gameinfo.xml",
            "README.md",
            "screenshot.png",
            "cover.png",
            "portdoctor/cover.png",
            "portdoctor/portdoctor.gptk",
            "portdoctor/lovegame/conf.lua",
            "portdoctor/lovegame/main.lua",
            "portdoctor/lovegame/src/diagnostics.lua",
            "portdoctor/lovegame/src/logdoctor.lua",
            "portdoctor/lovegame/src/recipes.lua",
            "portdoctor/lovegame/src/repairs.lua",
            "portdoctor/lovegame/src/tools.lua",
            "portdoctor/lovegame/src/util.lua",
            "portdoctor/lovegame/src/battery.lua",
            "portdoctor/lovegame/src/storage.lua",
            "portdoctor/lovegame/src/json.lua",
            "portdoctor/lovegame/src/icons.lua",
            "portdoctor/lovegame/src/updates.lua",
            "portdoctor/release.json",
            "portdoctor/integrations/network/network-manager.sh",
            "portdoctor/integrations/covers/portmaster-cover-fix.sh",
            "portdoctor/integrations/system/storage-doctor.sh",
            "portdoctor/integrations/usb/usb-bridge.sh",
            "portdoctor/integrations/usb/payload/r36s-usb-control",
            "portdoctor/integrations/usb/payload/r36s-usb-gadget",
            "portdoctor/integrations/usb/payload/r36s-usb-gadget.service",
            "portdoctor/integrations/usb/LICENSE",
            "portdoctor/integrations/usb/README.md",
            "portdoctor/extras/network-windows/1 - Preparar no Windows.cmd",
            "portdoctor/extras/network-windows/Preparar Jogos em Rede no Windows.ps1",
            "portdoctor/tools/install_metadata.py",
            "portdoctor/tools/repair_port.py",
            "portdoctor/tools/unity_audit.py",
            "portdoctor/tools/unity_egl.py",
            "portdoctor/tools/unity_graphics.py",
            "portdoctor/libexec/aarch64/unity-egl-rebind.so",
            "portdoctor/tools/zram-helper.sh",
            "portdoctor/tools/battery.py",
            "portdoctor/tools/memory.py",
            "portdoctor/lovegame/src/memory.lua",
            "portdoctor/tools/file_manager.py",
            "portdoctor/tools/network_status.py",
            "portdoctor/tools/updater.py",
            "portdoctor/tools/update-install.sh",
            "portdoctor/compat-packs/README.md",
            "portdoctor/compat-packs/pack.schema.json",
            "portdoctor/conf/reports/",
        }
        require(not required.difference(names), "arquivos obrigatórios ausentes do ZIP")
        require(not any(name.endswith('-PROPOSTA.md') for name in names), 'propostas não implementadas não entram na release')
        mode = (archive.getinfo("Port Doctor R36S.sh").external_attr >> 16) & 0o777
        require(mode == 0o755, "launcher não está executável no ZIP")
        for executable in (
            "portdoctor/integrations/network/network-manager.sh",
            "portdoctor/integrations/covers/portmaster-cover-fix.sh",
            "portdoctor/integrations/system/storage-doctor.sh",
            "portdoctor/integrations/usb/usb-bridge.sh",
            "portdoctor/integrations/usb/install.sh",
            "portdoctor/integrations/usb/payload/r36s-usb-control",
            "portdoctor/integrations/usb/payload/r36s-usb-gadget",
            "portdoctor/tools/zram-helper.sh",
            "portdoctor/tools/update-install.sh",
        ):
            mode = (archive.getinfo(executable).external_attr >> 16) & 0o777
            require(mode == 0o755, f"{executable} não está executável no ZIP")
        require(not any("\\" in name or name.startswith("/") for name in names), "caminho inválido no ZIP")
        require(not any(name.endswith(('.conf', '.log', '.pyc')) or name.endswith('/credentials')
                        or (name.startswith('portdoctor/conf/') and not name.endswith('/')) for name in names),
                'pacote público contém configuração, log ou credencial local')

    require(EASY_INSTALLER.is_file(), "instalador de um clique não foi gerado")
    with ZipFile(EASY_INSTALLER) as installer:
        folder = "Port Doctor R36S Installer/"
        required = {
            folder + "Instalar Port Doctor R36S.sh",
            folder + "LEIA-ME.txt",
            folder + "portdoctor.zip",
        }
        require(not required.difference(installer.namelist()), "instalador de um clique está incompleto")
        mode = (installer.getinfo(folder + "Instalar Port Doctor R36S.sh").external_attr >> 16) & 0o777
        require(mode == 0o755, "script do instalador não está executável")
        require(installer.read(folder + "portdoctor.zip") == INSTALLABLE.read_bytes(),
                "payload do instalador difere do pacote validado")

    print("Validação estrutural: OK")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Falha: {error}", file=sys.stderr)
        raise SystemExit(1)
