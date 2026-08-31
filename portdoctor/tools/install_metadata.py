#!/usr/bin/env python3
"""Install Port Doctor metadata idempotently for direct ZIP extractions."""

import argparse
import os
import shutil
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree


FIELDS = {
    "path": "./Port Doctor R36S.sh",
    "name": "Port Doctor R36S",
    "desc": "Diagnóstico e manutenção protegida de ports, runtimes, bibliotecas e permissões.",
    "releasedate": "20260828T000000",
    "developer": "fabriciopab",
    "publisher": "fabriciopab",
    "genre": "Utility",
    "image": "./portdoctor/cover.png",
}


def child_text(node, tag):
    child = node.find(tag)
    return child.text if child is not None else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ports-root", required=True)
    parser.add_argument("--port-home", required=True)
    args = parser.parse_args()

    ports_root = Path(args.ports_root).resolve()
    port_home = Path(args.port_home).resolve()
    if port_home.parent != ports_root or port_home.name != "portdoctor":
        raise SystemExit("metadata: caminhos fora do port recusados")
    if not (port_home / "cover.png").is_file():
        raise SystemExit("metadata: cover.png ausente")

    gamelist = ports_root / "gamelist.xml"
    if gamelist.exists():
        tree = ElementTree.parse(gamelist)
        root = tree.getroot()
        if root.tag != "gameList":
            raise SystemExit("metadata: formato de gamelist.xml desconhecido")
    else:
        root = ElementTree.Element("gameList")
        tree = ElementTree.ElementTree(root)

    game = None
    for candidate in root.findall("game"):
        if child_text(candidate, "path") == FIELDS["path"] or child_text(candidate, "name") == FIELDS["name"]:
            game = candidate
            break
    if game is None:
        game = ElementTree.SubElement(root, "game")

    changed = False
    for tag, value in FIELDS.items():
        child = game.find(tag)
        if child is None:
            child = ElementTree.SubElement(game, tag)
        if child.text != value:
            child.text = value
            changed = True

    if not changed:
        print("Port Doctor: metadados já instalados")
        return

    if gamelist.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(gamelist, gamelist.with_name(f"gamelist.xml.portdoctor-backup-{stamp}"))

    try:
        ElementTree.indent(tree, space="  ")
    except AttributeError:
        pass
    temporary = gamelist.with_name("gamelist.xml.portdoctor.tmp")
    tree.write(temporary, encoding="utf-8", xml_declaration=True)
    os.replace(temporary, gamelist)
    print("Port Doctor: metadados e capa registrados; reinicie o EmulationStation para recarregar")


if __name__ == "__main__":
    main()
