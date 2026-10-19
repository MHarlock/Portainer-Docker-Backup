#!/usr/bin/env python3
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Configurazione del Logging (Console + File di log locale)
LOG_FILE = Path(__file__).resolve().parent / "backup_docker.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8")
    ]
)

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / "backup_config.json"
TELEGRAM_CONFIG_FILE = SCRIPT_DIR / "telegram_config.json"


def load_json_file(file_path: Path) -> dict:
    if not file_path.exists():
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Errore nella lettura del file {file_path.name}: {e}")
        return {}


def send_telegram_notification(telegram_cfg: dict, message: str):
    if not telegram_cfg.get("enabled", False):
        return

    bot_token = telegram_cfg.get("bot_token")
    chat_id = telegram_cfg.get("chat_id")

    if not bot_token or not chat_id or bot_token == "IL_TUO_BOT_TOKEN_REALE":
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as response:
            pass
    except Exception as e:
        logging.error(f"Impossibile inviare la notifica Telegram: {e}")


def check_mount_point(mount_point: str) -> bool:
    path = Path(mount_point)
    if not path.exists() or not os.path.ismount(mount_point):
        logging.error(f"ERRORE CRITICO: Il punto di mount NAS non è raggiungibile o montato: {mount_point}")
        return False
    return True


def run_command(cmd: list) -> bool:
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Comando fallito: {' '.join(cmd)}")
        logging.error(f"Errore: {e.stderr.strip()}")
        return False


def get_container_metadata(container_name: str) -> dict:
    try:
        cmd = ["docker", "inspect", container_name]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        data = json.loads(result.stdout)[0]

        env_vars = data.get("Config", {}).get("Env", [])
        networks_data = data.get("NetworkSettings", {}).get("Networks", {})
        networks_info = {
            net_name: {
                "ip_address": net_config.get("IPAddress", ""),
                "gateway": net_config.get("Gateway", ""),
                "mac_address": net_config.get("MacAddress", "")
            }
            for net_name, net_config in networks_data.items()
        }

        ports = data.get("HostConfig", {}).get("PortBindings", {})
        mounts = data.get("Mounts", [])
        mounts_info = [
            {
                "type": m.get("Type"),
                "source": m.get("Source"),
                "destination": m.get("Destination"),
                "mode": m.get("Mode")
            }
            for m in mounts
        ]

        return {
            "container": container_name,
            "image_tag": data.get("Config", {}).get("Image", "unknown"),
            "image_id": data.get("Image", "unknown"),
            "created_at": data.get("Created", ""),
            "restart_policy": data.get("HostConfig", {}).get("RestartPolicy", {}).get("Name", ""),
            "environment_variables": env_vars,
            "networks": networks_info,
            "port_bindings": ports,
            "mounts": mounts_info
        }
    except Exception as e:
        logging.error(f"Errore durante l'estrazione metadati per '{container_name}': {e}")
        return {"container": container_name, "image_tag": "unknown", "image_id": "unknown", "error": str(e)}


def save_container_metadata(container_name: str, container_dest: Path):
    container_dest.mkdir(parents=True, exist_ok=True)
    metadata_file = container_dest / f"{container_name}_metadata.json"
    
    meta = get_container_metadata(container_name)
    payload = {
        "backup_timestamp": datetime.now().isoformat(),
        **meta
    }
    
    try:
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        logging.info(f"Metadati salvati per '{container_name}' in: {metadata_file}")
    except Exception as e:
        logging.error(f"Impossibile salvare i metadati per {container_name}: {e}")


def extract_portainer_compose_files(volume_name: str = "portainer_data") -> dict:
    extracted_composes = {}
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        logging.info(f"Estrazione temporanea degli stack dal volume Portainer '{volume_name}'...")
        
        copy_cmd = [
            "docker", "run", "--rm",
            "-v", f"{volume_name}:/portainer:ro",
            "-v", f"{tmp_path.resolve()}:/out",
            "alpine",
            "sh", "-c", "if [ -d /portainer/compose ]; then cp -r /portainer/compose /out/; fi"
        ]
        if not run_command(copy_cmd):
            logging.warning("Impossibile accedere alla directory 'compose' del volume Portainer.")
            return extracted_composes

        compose_dir = tmp_path / "compose"
        if not compose_dir.exists():
            return extracted_composes

        for folder in compose_dir.iterdir():
            if folder.is_dir():
                yml_file = folder / "docker-compose.yml"
                if yml_file.exists():
                    try:
                        content = yml_file.read_text(encoding="utf-8")
                        service_names = re.findall(r"^\s{2,4}([a-zA-Z0-9_-]+):", content, re.MULTILINE)
                        for service in service_names:
                            extracted_composes[service.lower()] = content
                    except Exception as e:
                        logging.error(f"Errore nella lettura di {yml_file}: {e}")

    logging.info(f"Estratti con successo {len(extracted_composes)} riferimenti compose da Portainer.")
    return extracted_composes


def stop_containers(containers: list):
    if not containers:
        return
    logging.info(f"Fermo i container: {', '.join(containers)}")
    run_command(["docker", "stop"] + containers)


def start_containers(containers: list):
    if not containers:
        return
    logging.info(f"Riavvio i container: {', '.join(containers)}")
    run_command(["docker", "start"] + containers)


def sync_paths_local(paths: list, container_dest: Path):
    """Gestisce il backup delle cartelle: creazione .tar.gz (per preservare permessi) oppure rsync diretto sul mount CIFS."""
    container_dest.mkdir(parents=True, exist_ok=True)

    for path_item in paths:
        if isinstance(path_item, str):
            src = path_item
            should_archive = True
        else:
            src = path_item.get("path")
            should_archive = path_item.get("archive", True)

        src_path = Path(src)
        if not src_path.exists():
            logging.info(f"Il percorso locale {src} non esiste. Lo creo automaticamente.")
            try:
                src_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logging.error(f"Impossibile creare la cartella locale {src}: {e}")
                continue

        if should_archive:
            # Creazione di un archivio .tar.gz salvato direttamente sul mount CIFS.
            # L'archivio racchiude e mantiene intatti i permessi POSIX e l'owner (root:root / UID container).
            tar_filename = f"{src_path.name}.tar.gz"
            dest_tar = container_dest / tar_filename
            logging.info(f"Creazione archivio compresso per {src} -> {dest_tar}...")

            tar_cmd = ["tar", "czf", str(dest_tar), "-C", str(src_path.parent), src_path.name]
            if run_command(tar_cmd):
                logging.info(f"Archivio {tar_filename} creato con successo sul NAS.")
            else:
                logging.error(f"Creazione archivio fallita per {src}")
                return False
        else:
            # Trasferimento diretto sul mount CIFS per file/cartelle già compresse (es. Home Assistant backups)
            target_dir = container_dest / src_path.name
            target_dir.mkdir(parents=True, exist_ok=True)
            logging.info(f"Sincronizzazione diretta (senza ri-compressione) per: {src} -> {target_dir}")

            rsync_cmd = [
                "rsync",
                "-rtlv",
                "--delete",
                "--no-perms",
                "--no-owner",
                "--no-group",
                "--exclude=*cifs*",
                "--exclude=*.tmp",
                f"{src}/",
                str(target_dir)
            ]
            if run_command(rsync_cmd):
                logging.info(f"Sincronizzazione diretta completata per: {src}")
            else:
                logging.error(f"Sincronizzazione diretta fallita per: {src}")
                return False

    return True


def backup_docker_volume_local(volume_name: str, container_dest: Path):
    container_dest.mkdir(parents=True, exist_ok=True)
    backup_file = container_dest / f"{volume_name}.tar.gz"

    logging.info(f"Backup del volume Docker interno '{volume_name}' sul mount locale...")

    backup_cmd = [
        "docker", "run", "--rm",
        "-v", f"{volume_name}:/volume:ro",
        "-v", f"{container_dest.resolve()}:/backup",
        "alpine",
        "tar", "czf", f"/backup/{volume_name}.tar.gz", "-C", "/volume", "."
    ]

    if run_command(backup_cmd):
        logging.info(f"Volume '{volume_name}' salvato con successo in {backup_file}")
        return True
    else:
        logging.error(f"Backup fallito per il volume Docker: {volume_name}")
        return False


def main():
    if os.geteuid() != 0:
        print("Errore: Questo script deve essere eseguito come root (sudo).")
        sys.exit(1)

    config = load_json_file(CONFIG_FILE)
    telegram_config = load_json_file(TELEGRAM_CONFIG_FILE)

    if not config:
        logging.error(f"File di configurazione principale non trovato o non valido: {CONFIG_FILE}")
        sys.exit(1)

    nas_mount = config.get("nas_mount_point")
    subfolder = config.get("backup_destination_subfolder", "portainer_docker")

    send_telegram_notification(telegram_config, "🚀 *Backup Docker avviato* (Destinazione CIFS locale).")

    if not check_mount_point(nas_mount):
        err_msg = f"❌ *ERRORE CRITICO:* Il punto di mount NAS ({nas_mount}) non è raggiungibile o montato! Backup interrotto."
        logging.error(err_msg)
        send_telegram_notification(telegram_config, err_msg)
        sys.exit(1)

    base_backup_dest = Path(nas_mount) / subfolder
    containers_config = config.get("containers", [])

    grouped_tasks = defaultdict(lambda: {"items": [], "stop": False})

    for idx, item in enumerate(containers_config):
        group = item.get("group", f"__single_{idx}")
        if item.get("stop", False):
            grouped_tasks[group]["stop"] = True
        grouped_tasks[group]["items"].append(item)

    global_success = True
    portainer_extracted_composes = {}

    for group_key, data in grouped_tasks.items():
        items = data["items"]
        should_stop = data["stop"]
        group_containers = [item["name"] for item in items if item.get("name")]

        logging.info(f"--- Elaborazione blocco: {group_key} (Containers: {group_containers if group_containers else 'Nessuno'}) ---")

        stopped_successfully = False
        try:
            if should_stop and group_containers:
                stop_containers(group_containers)
                stopped_successfully = True

            for item in items:
                name = item.get("name")
                paths = item.get("paths", [])
                volumes = item.get("volumes", [])

                if not name:
                    continue

                container_dest = base_backup_dest / name
                container_dest.mkdir(parents=True, exist_ok=True)

                # 1. Metadati a runtime
                save_container_metadata(name, container_dest)

                # 2. Backup cartelle locali (archiviate in .tar.gz o rsync diretto in base al flag)
                if paths:
                    success_sync = sync_paths_local(paths, container_dest)
                    if not success_sync:
                        global_success = False

                # 3. Backup volumi interni Docker (.tar.gz)
                for vol in volumes:
                    success_vol = backup_docker_volume_local(vol, container_dest)
                    if not success_vol:
                        global_success = False

                # 4. Estrazione compose da Portainer se elaboriamo Portainer
                if name == "portainer":
                    portainer_extracted_composes = extract_portainer_compose_files("portainer_data")

                # 5. Salvataggio compose estratto sul NAS
                clean_name = name.lower()
                if clean_name in portainer_extracted_composes:
                    compose_dest = container_dest / "docker-compose.yml"
                    try:
                        compose_dest.write_text(portainer_extracted_composes[clean_name], encoding="utf-8")
                        logging.info(f"File docker-compose.yml salvato per '{name}' in: {compose_dest}")
                    except Exception as e:
                        logging.error(f"Impossibile salvare il docker-compose.yml estratto per {name}: {e}")

        finally:
            if stopped_successfully and group_containers:
                start_containers(group_containers)

        logging.info(f"--- Blocco {group_key} completato ---\n")

    if global_success:
        success_msg = "✅ *Backup Docker completato con successo!* Archivi e configurazioni salvati sul NAS."
        logging.info(success_msg)
        send_telegram_notification(telegram_config, success_msg)
    else:
        warn_msg = "⚠️ *Backup Docker completato con errori.* Controlla i log sul Raspberry Pi."
        logging.warning(warn_msg)
        send_telegram_notification(telegram_config, warn_msg)


if __name__ == "__main__":
    main()