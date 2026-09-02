from pathlib import Path
import hashlib
import os
from shutil import copy2
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parent
OUTPUTS = Path(os.environ.get('PORTDOCTOR_OUTPUTS', ROOT.parents[1] / "outputs")).resolve()
VERSION = "0.12.0"


def publishable(source):
    if OUTPUTS in source.parents or any(p in ('.git', '__pycache__', '.codex') for p in source.parts):
        return False
    relative = source.relative_to(ROOT).as_posix()
    return not (relative.startswith('portdoctor/conf/') or source.name == 'log.txt'
                or source.name.endswith('-PROPOSTA.md')
                or source.suffix.lower() in ('.conf', '.log', '.pyc') or source.name in ('credentials', 'update-channel.json'))


def add_file(archive: ZipFile, source: Path, arcname: str, content=None):
    info = ZipInfo.from_file(source, arcname)
    info.compress_type = ZIP_DEFLATED
    executable_names = {"r36s-usb-control", "r36s-usb-gadget"}
    mode = 0o755 if source.suffix == ".sh" or source.name in executable_names else 0o644
    info.external_attr = (0o100000 | mode) << 16
    archive.writestr(info, source.read_bytes() if content is None else content)


def build_installable():
    destination = OUTPUTS / f"Port-Doctor-R36S-v{VERSION}.zip"
    roots = [
        ROOT / "Port Doctor R36S.sh",
        ROOT / "port.json",
        ROOT / "gameinfo.xml",
        ROOT / "README.md",
        ROOT / "screenshot.png",
        ROOT / "cover.png",
    ]

    documents = sorted(ROOT.glob('*.md')) + [ROOT / 'LICENSE']
    with ZipFile(destination, "w") as archive:
        for source in roots:
            content = None
            if source.name == 'README.md':
                content = source.read_text(encoding='utf-8')
                for doc in documents:
                    content = content.replace('](' + doc.name + ')', '](portdoctor/docs/' + doc.name + ')')
                content = content.encode('utf-8')
            add_file(archive, source, source.name, content)

        # Protocol 1 updaters allow only the original six root files.
        # Extra manuals live inside the application, not beside launchers.
        for doc in documents:
            content = None
            if doc.name == 'README.md':
                content = doc.read_text(encoding='utf-8').replace('src="cover.png"', 'src="../../cover.png"')
                content = content.replace('src="screenshot.png"', 'src="../../screenshot.png"').encode('utf-8')
            add_file(archive, doc, 'portdoctor/docs/' + doc.name, content)

        # Keep the catalogue artwork at the archive root and also place it
        # where a direct /roms/ports extraction lets EmulationStation find it.
        add_file(archive, ROOT / "cover.png", "portdoctor/cover.png")

        port_dir = ROOT / "portdoctor"
        for source in sorted(port_dir.rglob("*")):
            if source.is_file() and publishable(source):
                relative = source.relative_to(ROOT).as_posix()
                add_file(archive, source, relative)

        directory = ZipInfo("portdoctor/conf/reports/")
        directory.external_attr = (0o040755 << 16) | 0x10
        archive.writestr(directory, b"")

    return destination


def build_easy_installer(installable: Path):
    destination = OUTPUTS / f"Port-Doctor-R36S-Instalador-v{VERSION}.zip"
    folder = "Port Doctor R36S Installer"
    with ZipFile(destination, "w") as archive:
        add_file(archive, ROOT / "installer/Instalar Port Doctor R36S.sh",
                 f"{folder}/Instalar Port Doctor R36S.sh")
        add_file(archive, ROOT / "installer/LEIA-ME.txt", f"{folder}/LEIA-ME.txt")
        add_file(archive, installable, f"{folder}/portdoctor.zip")
    return destination


def build_source():
    destination = OUTPUTS / f"portdoctor-r36s-source-v{VERSION}.zip"
    excluded = {"__pycache__"}
    with ZipFile(destination, "w") as archive:
        for source in sorted(ROOT.rglob("*")):
            if not source.is_file() or not publishable(source) or any(part in excluded for part in source.parts):
                continue
            relative_path = source.relative_to(ROOT).as_posix()
            if relative_path == "portdoctor/log.txt" or relative_path.startswith("portdoctor/conf/reports/"):
                continue
            add_file(archive, source, f"portdoctor-r36s/{relative_path}")
    return destination


def build_windows():
    destination = OUTPUTS / f"Port-Doctor-R36S-Windows-Rede-v{VERSION}.zip"
    with ZipFile(destination, 'w') as archive:
        for name in ('1 - Preparar no Windows.cmd', 'Preparar Jogos em Rede no Windows.ps1', 'LEIA-ME.txt'):
            add_file(archive, ROOT / 'portdoctor/extras/network-windows' / name, 'Preparar Rede no Windows/' + name)
    return destination


OUTPUTS.mkdir(parents=True, exist_ok=True)
# Ship the already-tested local installer; the updater never executes one from a release.
copy2(ROOT / "installer/Instalar Port Doctor R36S.sh", ROOT / "portdoctor/tools/update-install.sh")
installable = build_installable()
easy_installer = build_easy_installer(installable)
source = build_source()
windows = build_windows()
preview = OUTPUTS / "Port-Doctor-R36S-preview.png"
copy2(ROOT / "screenshot.png", preview)
cover = OUTPUTS / "Port-Doctor-R36S-cover.png"
copy2(ROOT / "cover.png", cover)
catalogue = OUTPUTS / "portdoctor.zip"
copy2(installable, catalogue)
cover_fix = OUTPUTS / "portmaster-cover-fix-v4.sh"
copy2(ROOT / "portdoctor/integrations/covers/portmaster-cover-fix.sh", cover_fix)
print(installable)
print(easy_installer)
print(source)
print(windows)
print(preview)
print(cover)
print(catalogue)
print(cover_fix)
checksum = OUTPUTS / (installable.name + '.sha256')
checksum.write_text(hashlib.sha256(installable.read_bytes()).hexdigest() + '  ' + installable.name + '\n', encoding='ascii')
print(checksum)
