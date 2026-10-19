Markdown

# 🐳 Raspberry Pi Docker Backup to NAS

[🇮🇹 Italiano](#-italiano) | [🇬🇧 English](#-english)

---

## 🇮🇹 Italiano

Un sistema di backup resiliente, automatizzato e indipendente sviluppato in Python per gestire il salvataggio dei container Docker da un **Raspberry Pi** a una condivisione di rete NAS (tramite mount CIFS/SMB).

Il progetto è pensato per garantire una protezione totale dei dati e delle configurazioni, preservando rigorosamente permessi e proprietari POSIX (`root:root` e UID specifici dei container) grazie a una strategia mista basata su archivi compressi e sincronizzazione intelligente.

### 🌟 Caratteristiche Principali
* **Portainer-First Strategy**: All'avvio del backup, lo script ispeziona il volume interno di Portainer ed **estrae automaticamente i file `docker-compose.yml` originali** di tutti gli stack registrati.
* **Preservazione dei Permessi POSIX**: I bind mount locali vengono compressi in archivi `.tar.gz` salvati sul NAS, incapsulando e proteggendo i permessi originari e i proprietari (UID/GID).
* **Archiviazione Selettiva (`archive: true/false`)**: Possibilità di scegliere se comprimere una cartella (`true`) oppure eseguire un trasferimento diretto (`false` per servizi come Home Assistant che generano già backup compressi).
* **Metadati di Runtime**: Per ogni container viene estratto un file JSON con le informazioni di configurazione (`docker inspect`, variabili d'ambiente, reti e volumi).
* **Notifiche Telegram**: Invio di report in tempo reale sull'esito dell'esecuzione.

### ⚙️ Configurazione e Installazione
1. **Mount CIFS sul Raspberry Pi** (es. in `/etc/fstab`):
   ```text
   //192.168.x.x/Backup /media/nas/backup cifs credentials=/etc/samba/credentials,vers=3.0,uid=1001,gid=100,file_mode=0777,dir_mode=0777,nofail,_netdev 0 0

    File di configurazione (backup_config.json e telegram_config.json) posizionati nella cartella dello script (es. /opt/docker-backup/).

    Esecuzione Manuale:
    Bash

    sudo python3 /opt/docker-backup/portainer_docker_backup.py

    Automazione Notturna (Cron):
    Plaintext

    0 3 * * * /usr/bin/python3 /opt/docker-backup/portainer_docker_backup.py >> /opt/docker-backup/cron_execution.log 2>&1

## 🇬🇧 English

A resilient, automated, and independent Python-based backup system designed to back up Docker containers from a Raspberry Pi to a NAS network share (via CIFS/SMB mount).

The project ensures total protection of data and configurations, strictly preserving POSIX permissions and owners (root:root and container-specific UIDs) through a mixed strategy of compressed archives and intelligent synchronization.
### 🌟 Key Features

    Portainer-First Strategy: At startup, the script inspects Portainer's internal volume and automatically extracts the original docker-compose.yml files for all registered stacks.

    POSIX Permissions Preservation: Local bind mounts are compressed into .tar.gz archives saved on the NAS, encapsulating and protecting original permissions and ownership (UID/GID).

    Selective Archiving (archive: true/false): Choose whether to compress a folder (true) or perform a direct transfer (false for services like Home Assistant that already generate compressed backups).

    Runtime Metadata: A JSON file containing configuration details (docker inspect, environment variables, networks, and volumes) is extracted for each container.

    Telegram Notifications: Real-time reports sent directly to Telegram regarding backup execution status.

⚙️ Setup and Installation

    CIFS Mount on Raspberry Pi (e.g., in /etc/fstab):
    Plaintext

    //192.168.x.x/Backup /media/nas/backup cifs credentials=/etc/samba/credentials,vers=3.0,uid=1001,gid=100,file_mode=0777,dir_mode=0777,nofail,_netdev 0 0

    Configuration files (backup_config.json & telegram_config.json) placed in the script directory (e.g., /opt/docker-backup/).

    Manual Execution:
    Bash

    sudo python3 /opt/docker-backup/portainer_docker_backup.py

    Nightly Automation (Cron):
    Plaintext

    0 3 * * * /usr/bin/python3 /opt/docker-backup/portainer_docker_backup.py >> /opt/docker-backup/cron_execution.log 2>&1

🔄 Disaster Recovery

    Install Docker and Portainer on the new host.

    Locate the container's backup folder on the NAS (/media/nas/backup/portainer_docker/<container_name>/).

    Recreate the container using the saved docker-compose.yml file.

    If the service used an archived bind mount, restore the files by extracting the .tar.gz archive as root:
    Bash

    sudo tar xzf <folder_name>.tar.gz -C /target/path/

📝 License

Distributed under the MIT License. Feel free to use, modify, and adapt it to your needs.


<FollowUp term="Vuoi apportare altre modifiche o integrazioni al README.md bilingue?"/>
