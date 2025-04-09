# AION System Agent Project

Version: 1.7.0 (Python Agent) / 1.4.0 (Bash Agent)

## Overview

This project contains the AION System Agent, designed for autonomous monitoring, diagnostics, AI-driven analysis (via Ollama), and optional self-healing capabilities within the AION chroot environment.

The primary agent is implemented in Python (`systemagent.py`, v1.7.0) and is recommended for use due to its robustness and features. An earlier Bash version (`systemagent.sh`, v1.4.0) is also included as a reference or alternative.

The agent is intended to be run persistently using a process manager like Supervisor, operating as the `aion` user within the chroot.

## Core Component: `systemagent.py` (v1.7.0)

### Features

*   **Comprehensive Monitoring:** Tracks CPU (usage, load, times), Memory (virtual, swap), Disk (usage, IO), Network (IO, rate, connections), Processes (total, zombies), Temperature, and Uptime.
*   **Structured Diagnostics:** Analyzes metrics against configurable thresholds, assigning subsystem and overall health status (NOMINAL, WARNING, CRITICAL, ERROR).
*   **AI-Powered Analysis (Optional):** Integrates with a local Ollama instance to provide deeper insights into system state and diagnostics using a configured LLM (logs analysis, does not act on it automatically).
*   **Configurable Self-Healing (Optional):** Attempts automated remediation for detected issues based on `config.json` settings. Actions include clearing memory caches, cleaning zombie processes, deleting old log/temp files, and optionally killing high-CPU processes or restarting network services. **Requires careful configuration and sudo privileges.**
*   **Periodic Maintenance:** Runs `mandb` (man page index update) when system load is low.
*   **Alerting (Optional):** Sends email alerts via SMTP for non-nominal states.
*   **Robust Logging:** Configurable level, logs to file (with rotation) and stdout.
*   **Graceful Shutdown:** Handles SIGTERM/SIGINT.
*   **Configuration:** Driven by `config.json`.

### Setup & Configuration

1.  **Environment:** Assumes the AION chroot environment (e.g., `/opt/aion_chroot`).
2.  **User:** Designed to run as the `aion` user.
3.  **Virtual Environment:** Create and activate a Python venv (e.g., `/opt/aion/venv/`):
    ```bash
    # Inside chroot
    python3 -m venv /opt/aion/venv
    source /opt/aion/venv/bin/activate
    ```
4.  **Dependencies:** Install required libraries into the venv:
    ```bash
    # Inside chroot (with venv activated)
    pip install --upgrade pip
    pip install psutil ollama # Install ollama only if AI features are desired
    ```
5.  **Script Location:** Place `systemagent.py` in `/opt/aion/system_agent/system_agent.py`. Make it executable (`chmod +x ...`).
6.  **Configuration File:** Create/edit `/opt/aion/system_agent/config.json` using the example below. Adjust thresholds, features, paths, email, Ollama settings.
7.  **Permissions & Sudo:**
    *   Ensure `aion` user can read `config.json` and write to the log directory/file (e.g., `/var/log/aion/`).
    *   **CRITICAL:** If self-healing/maintenance is enabled, configure specific, **passwordless sudo** rules externally (`/etc/sudoers` or `/etc/sudoers.d/`) for the `aion` user **only for the required commands**. See `LIMITATIONS.md`.
8.  **Ollama (Optional):** Ensure Ollama service is running and accessible (e.g., `http://127.0.0.1:11434` from within chroot). Ensure the model specified in `config.json` is available or pullable.
9.  **Email (Optional):** Configure a local SMTP relay if using email alerts.

### Running (Supervisor Recommended)

1.  **Install Supervisor:** `sudo apt-get update && sudo apt-get install -y supervisor` (inside chroot).
2.  **Create Supervisor Config:** Place the example `supervisor/aion_system_agent.conf` into `/etc/supervisor/conf.d/aion_system_agent.conf`.
3.  **Load & Start:**
    ```bash
    sudo supervisorctl reread
    sudo supervisorctl update
    sudo supervisorctl start aion_system_agent
    ```
4.  **Check Status:** `sudo supervisorctl status aion_system_agent`

### Logging

*   **Main Agent Log:** `/var/log/aion/system_agent.log` (configurable, rotates)
*   **Supervisor Stdout:** `/var/log/aion/system_agent.stdout.log`
*   **Supervisor Stderr:** `/var/log/aion/system_agent.stderr.log`

---

## Alternative Component: `systemagent.sh` (v1.4.0)

This is an earlier Bash implementation. It includes monitoring for CPU, Memory, Disk, Network Ping, Process/Service status, and Port status (listening IP). It supports basic alerting and self-healing (restarting a service).

*   **Configuration:** Uses `/opt/aion/config/system_agent.conf` (INI-style).
*   **Dependencies:** Requires `bc`, `sysstat`, `mailutils`, `iproute2` (for `ss`), `procps`, `coreutils`.
*   **Limitations:** Less robust error handling, less detailed monitoring, no AI integration compared to the Python version. Also relies on `sudo`.

Refer to the script's comments for details if using this version. The Python agent is generally preferred.

---

## Important Considerations

*   **Security:** Carefully review and restrict `sudo` permissions granted to the `aion` user.
*   **Self-Healing:** Use self-healing features cautiously, especially actions like killing processes or restarting networking. Test thoroughly.
*   **Limitations:** Understand the agent's limitations, especially regarding direct firewall management. See `LIMITATIONS.md`.
