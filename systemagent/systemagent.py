#!/opt/aion/venv/bin/python
# /opt/aion/system_agent/system_agent.py
# AION System Agent - Cognitive Monitoring, AI Analysis, Self-Healing
# Version: 1.7.0 (Final Audit & Refinements)

import os
import sys
import json
import time
import psutil
import subprocess
import traceback
import logging
import logging.handlers
import socket
import shutil
import smtplib
import signal
import pwd
import grp
from email.mime.text import MIMEText
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple, Union, Set

# Try importing ollama, handle if not found
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    ollama = None # Set to None if library is missing
    OLLAMA_AVAILABLE = False

# --- Constants ---
DEFAULT_CONFIG_PATH = '/opt/aion/system_agent/config.json'
AGENT_VERSION = "1.7.0"
# Schema for basic config validation
CONFIG_SCHEMA = {
    "monitor_interval": {"type": int, "min": 10},
    "log_level": {"type": str, "enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]},
    "log_file": {"type": str},
    "cpu_threshold": {"type": float, "min": 0, "max": 100},
    "memory_threshold": {"type": float, "min": 0, "max": 100},
    "disk_threshold": {"type": float, "min": 0, "max": 100},
    "swap_threshold": {"type": float, "min": 0, "max": 100},
    "zombie_threshold": {"type": int, "min": 0},
    "temp_alert_threshold": {"type": float},
    "network_connectivity_host": {"type": str},
    "network_connectivity_port": {"type": int, "min": 1, "max": 65535},
    "network_connectivity_timeout": {"type": int, "min": 1},
    "cpu_permit_man_update": {"type": float, "min": 0, "max": 100},
    "mandb_min_interval_hours": {"type": int, "min": 1},
    "email_alerts_enabled": {"type": bool},
    "email_recipient": {"type": str}, # Could add regex validation
    "email_sender": {"type": str},
    "smtp_host": {"type": str},
    "smtp_port": {"type": int, "min": 1, "max": 65535},
    "ollama_enabled": {"type": bool},
    "ollama_host": {"type": str}, # Could add URL validation
    "ollama_model": {"type": str},
    "ollama_init_timeout_seconds": {"type": int, "min": 10},
    "self_healing_enabled": {"type": bool},
    "self_heal_cpu_enabled": {"type": bool},
    "self_heal_cpu_threshold": {"type": float, "min": 0, "max": 100},
    "self_heal_cpu_kill_limit": {"type": int, "min": 0},
    "self_heal_cpu_exclude_procs": {"type": list}, # Check list elements are strings
    "self_heal_memory_enabled": {"type": bool},
    "self_heal_memory_clear_caches": {"type": bool},
    "self_heal_processes_enabled": {"type": bool},
    "self_heal_processes_cleanup_zombies": {"type": bool},
    "self_heal_disk_enabled": {"type": bool},
    "self_heal_disk_log_path": {"type": str},
    "self_heal_disk_log_max_age_days": {"type": int, "min": 1},
    "self_heal_disk_tmp_path": {"type": str},
    "self_heal_disk_tmp_max_age_days": {"type": int, "min": 1},
    "self_heal_network_enabled": {"type": bool},
    "self_heal_network_service_names": {"type": list}, # Check list elements are strings
}


class AionSystemAgent:
    """
    Integrated AION agent for monitoring, diagnostics, AI analysis, and self-healing.

    **Security Note:** This agent is designed to run as the 'aion' user.
    Certain self-healing and maintenance actions require elevated privileges.
    It is **imperative** that the 'aion' user is granted necessary, specific
    **passwordless sudo** capabilities *externally* via the /etc/sudoers file
    or /etc/sudoers.d/. Using overly broad rules (like ALL=(ALL) NOPASSWD: ALL)
    is highly discouraged in production. Grant only the specific commands needed
    (e.g., specific 'kill', 'systemctl restart <service>', 'mandb', find commands).
    Misconfigured sudo rules are a significant security risk.

    Requires psutil, ollama (optional) libraries installed in the venv.
    """
    VERSION = AGENT_VERSION

    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self.config_path = config_path
        self.config: Dict[str, Any] = {} # Set default empty dict
        self.logger = self._configure_initial_logging() # Basic logger first
        self.config = self._load_and_validate_config() # Load the actual config
        self._configure_logging(reconfigure=True) # Reconfigure with loaded settings

        self.logger.info(f"===== AION System Agent v{self.VERSION} Starting =====")
        self.logger.info(f"Using configuration: {self.config_path}")
        self.logger.info(f"Effective monitoring interval: {self.config['monitor_interval']}s")
        self.logger.info(f"Self-Healing Enabled: {self.config.get('self_healing_enabled', False)}")
        self.current_user = self._get_current_user()
        self.logger.warning(f"Agent running as user '{self.current_user}'. Ensure required passwordless sudo rules are configured if self-healing requires root.")

        self.last_mandb_run_time: float = 0.0
        self.last_net_io_counters: Optional[psutil._common.snetio] = None
        self.last_net_collection_time: Optional[float] = None
        self.running: bool = True # Flag for graceful shutdown
        self._setup_signal_handling()

        self.ollama_client: Optional[ollama.Client] = self._initialize_ollama_client()
        if self.config.get("ollama_enabled") and not self.ollama_client:
             self.logger.warning("Ollama is enabled in config, but client initialization failed or library missing.")


    def _get_current_user(self) -> str:
        """Gets the current effective username."""
        try:
            return pwd.getpwuid(os.geteuid()).pw_name
        except Exception:
            return "unknown"

    def _configure_initial_logging(self) -> logging.Logger:
        """Sets up a basic logger before config is fully loaded."""
        logger = logging.getLogger('AionSystemAgentInit')
        # Avoid adding handlers if logger already exists from a previous init attempt
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    def _load_and_validate_config(self) -> Dict[str, Any]:
        """Loads configuration, merges with defaults, and validates schema."""
        defaults = { # Define comprehensive defaults here
            "monitor_interval": 60, "log_level": "INFO", "log_file": "/var/log/aion/system_agent.log",
            "cpu_threshold": 85.0, "memory_threshold": 90.0, "disk_threshold": 85.0, "swap_threshold": 75.0, "zombie_threshold": 10,
            "temp_alert_threshold": 80.0, "network_connectivity_host": "8.8.8.8", "network_connectivity_port": 53, "network_connectivity_timeout": 3,
            "cpu_permit_man_update": 50.0, "mandb_min_interval_hours": 6,
            "email_alerts_enabled": False, "email_recipient": "", "email_sender": "system-agent@aion.chroot.localhost", "smtp_host": "localhost", "smtp_port": 25,
            "ollama_enabled": OLLAMA_AVAILABLE, "ollama_host": "http://127.0.0.1:11434", "ollama_model": "gemma:2b", "ollama_init_timeout_seconds": 180, # Increased timeout
            "self_healing_enabled": True,
            "self_heal_cpu_enabled": False, "self_heal_cpu_threshold": 95.0, "self_heal_cpu_kill_limit": 2, "self_heal_cpu_exclude_procs": ["systemd", "kthreadd", "sshd", "rsyslogd", "journald", "dbus-daemon", "login", "agetty", "containerd", "dockerd", "kubelet", "supervisord", "python", "aion_system_agent", "ollama"], # Exclude common system procs + self + ollama
            "self_heal_memory_enabled": True, "self_heal_memory_clear_caches": True,
            "self_heal_processes_enabled": True, "self_heal_processes_cleanup_zombies": True,
            "self_heal_disk_enabled": True, "self_heal_disk_log_path": "/var/log", "self_heal_disk_log_max_age_days": 30, "self_heal_disk_tmp_path": "/tmp", "self_heal_disk_tmp_max_age_days": 7,
            "self_heal_network_enabled": False, "self_heal_network_service_names": ["networking", "NetworkManager", "systemd-networkd"],
        }
        config = defaults.copy()
        try:
            self.logger.info(f"Loading configuration from {self.config_path}")
            if not os.path.exists(self.config_path):
                 self.logger.warning(f"Config file not found: {self.config_path}. Using defaults.")
            else:
                with open(self.config_path, 'r') as f:
                    loaded_config = json.load(f)
                config.update(loaded_config) # Loaded values override defaults
                self.logger.info("Config file loaded.")
        except (json.JSONDecodeError, OSError) as e:
            self.logger.error(f"Error loading config: {e}. Using defaults.", exc_info=True)
            config = defaults.copy() # Revert to defaults on error

        # --- Validation against Schema ---
        validated_config = {}
        for key, schema in CONFIG_SCHEMA.items():
            value = config.get(key) # Get value from merged config
            valid = True
            expected_type = schema["type"]
            reason = "" # For logging validation failure reason

            if value is None: # Use default if key was missing entirely
                value = defaults.get(key)

            # Type Check
            if not isinstance(value, expected_type):
                 # Special case for float allowing int
                 if not (expected_type is float and isinstance(value, int)):
                      valid = False; reason = f"wrong type (got {type(value).__name__}, expected {expected_type.__name__})"
            # Additional Checks based on schema
            elif "min" in schema and value < schema["min"]: valid = False; reason = f"less than min {schema['min']}";
            elif "max" in schema and value > schema["max"]: valid = False; reason = f"greater than max {schema['max']}";
            elif "enum" in schema and str(value).upper() not in schema["enum"]: valid = False; reason = f"not in allowed values {schema['enum']}";
            elif expected_type is list and not isinstance(value, list): valid = False; reason = "expected a list"; # Ensure it IS a list first
            elif expected_type is list and not all(isinstance(item, str) for item in value): valid = False; reason = "list elements not all strings";

            if not valid:
                 self.logger.warning(f"Config Validation: Key '{key}' value '{value}' failed check ({reason}). Using default: {defaults.get(key)}")
                 value = defaults.get(key) # Use default on validation failure

            validated_config[key] = value # Store validated or default value

        # Specific post-validation checks
        if validated_config["email_alerts_enabled"] and not validated_config["email_recipient"]:
             self.logger.warning("Config Validation: email_alerts_enabled is true, but email_recipient is empty. Disabling email alerts.")
             validated_config["email_alerts_enabled"] = False
        if not OLLAMA_AVAILABLE and validated_config["ollama_enabled"]:
            self.logger.warning("Config Validation: ollama_enabled is true, but 'ollama' library not found. Disabling Ollama features.")
            validated_config["ollama_enabled"] = False

        # Ensure exclude list items are lowercase for case-insensitive comparison later
        if isinstance(validated_config.get("self_heal_cpu_exclude_procs"), list):
            validated_config["self_heal_cpu_exclude_procs"] = [p.lower() for p in validated_config["self_heal_cpu_exclude_procs"]]

        return validated_config

    def _configure_logging(self, reconfigure: bool = False):
        """Configures logging handlers based on validated config."""
        logger = logging.getLogger('AionSystemAgent')
        if reconfigure or not logger.handlers: # Configure if first time or reconfiguring
            for handler in logger.handlers[:]: handler.close(); logger.removeHandler(handler) # Remove existing

            log_level_str = self.config.get('log_level', 'INFO').upper()
            log_level = getattr(logging, log_level_str, logging.INFO)
            log_file = self.config.get('log_file')
            log_file_enabled = False

            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] %(message)s') # Added funcName+lineno
            handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)] # Always log to stdout

            if log_file:
                try:
                    log_dir = os.path.dirname(log_file); os.makedirs(log_dir, exist_ok=True)
                    # Use RotatingFileHandler for automatic rotation (10MB, 5 backups)
                    file_handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
                    file_handler.setFormatter(formatter)
                    handlers.append(file_handler)
                    log_file_enabled = True
                except Exception as e: print(f"ERROR: Failed setup file logging {log_file}: {e}", file=sys.stderr)

            logger.setLevel(log_level); logger.handlers.clear(); # Clear any handlers from init logger
            for handler in handlers: handler.setLevel(log_level); logger.addHandler(handler)
            logger.propagate = False
            self.logger = logger
            self.logger.info(f"Logging configured. Level: {log_level_str}, File: {log_file if log_file_enabled else 'Disabled'}")

    def _setup_signal_handling(self):
        """Sets up handlers for termination signals."""
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        self.logger.info("Signal handlers registered for SIGTERM, SIGINT.")

    def _handle_signal(self, signum, frame):
        """Gracefully handles termination signals."""
        signal_name = signal.Signals(signum).name
        self.logger.warning(f"Received signal {signal_name} ({signum}). Initiating shutdown...")
        self.running = False

    def _initialize_ollama_client(self) -> Optional['ollama.Client']:
        """Initializes Ollama client."""
        if not self.config.get("ollama_enabled") or not OLLAMA_AVAILABLE:
            self.logger.info("Ollama feature disabled or library not available.")
            return None

        host = self.config["ollama_host"]; model = self.config["ollama_model"]; timeout = self.config["ollama_init_timeout_seconds"]
        self.logger.info(f"Initializing Ollama: Host={host}, Model={model}, Timeout={timeout}s")
        try:
            client = ollama.Client(host=host, timeout=timeout); client.list() # Check connection
            self.logger.info(f"Ollama server connection OK: {host}")
            models = [m['name'] for m in client.list()['models']]
            if model not in models:
                self.logger.warning(f"Ollama model '{model}' missing. Pulling (BLOCKING)...")
                try:
                    status = client.pull(model, stream=False) # Blocking pull
                    self.logger.info(f"Ollama pull status for '{model}': {status}")
                    models_after = [m['name'] for m in client.list()['models']] # Re-verify
                    if model not in models_after: raise RuntimeError(f"Model '{model}' still not found after pull.")
                except Exception as pull_e: self.logger.error(f"Failed pull model '{model}': {pull_e}", exc_info=True); return None
            else: self.logger.info(f"Ollama model '{model}' found.")
            self.logger.info("Ollama client ready.")
            return client
        except Exception as e: self.logger.error(f"Failed init Ollama client: {e}", exc_info=True); return None

    # --- Data Collection ---
    def get_system_state(self) -> Dict[str, Any]:
        """Collects comprehensive system state using psutil and other tools."""
        # ... (No significant changes from v1.6.1 needed here, already quite detailed) ...
        self.logger.debug("Collecting system state..."); state = {"timestamp": datetime.now().isoformat()}
        try:
            state["cpu"] = {"percent": psutil.cpu_percent(interval=0.1)} # Non-blocking sample
            cpu_times = psutil.cpu_times_percent(interval=0.1); state["cpu"].update({"percent_user": cpu_times.user, "percent_system": cpu_times.system, "percent_idle": cpu_times.idle, "percent_wait": getattr(cpu_times, 'iowait', 0.0), "cores_logical": psutil.cpu_count(), "cores_physical": psutil.cpu_count(logical=False), "load_avg_1m_5m_15m": os.getloadavg()})
            mem = psutil.virtual_memory(); swap = psutil.swap_memory(); state["memory"] = {"virtual_total_gb": round(mem.total / (1024**3), 2), "virtual_available_gb": round(mem.available / (1024**3), 2), "virtual_percent": mem.percent, "swap_total_gb": round(swap.total / (1024**3), 2), "swap_used_gb": round(swap.used / (1024**3), 2), "swap_percent": swap.percent}
            disk = psutil.disk_usage('/'); disk_io = psutil.disk_io_counters(); state["disk"] = {"path": "/", "total_gb": round(disk.total / (1024**3), 2), "used_gb": round(disk.used / (1024**3), 2), "free_gb": round(disk.free / (1024**3), 2), "percent": disk.percent, "io_read_count": getattr(disk_io, 'read_count', 'N/A'), "io_write_count": getattr(disk_io, 'write_count', 'N/A'), "io_read_mb": round(getattr(disk_io, 'read_bytes', 0) / (1024**2), 2), "io_write_mb": round(getattr(disk_io, 'write_bytes', 0) / (1024**2), 2)}
            current_time = time.monotonic(); net_io = psutil.net_io_counters(); state["network_rate_kBs"] = {"sent": 0.0, "recv": 0.0}; if self.last_net_io_counters and self.last_net_collection_time: interval = current_time - self.last_net_collection_time; if interval > 0: bytes_sent_rate = (net_io.bytes_sent - self.last_net_io_counters.bytes_sent) / interval; bytes_recv_rate = (net_io.bytes_recv - self.last_net_io_counters.bytes_recv) / interval; state["network_rate_kBs"] = {"sent": round(bytes_sent_rate / 1024, 2), "recv": round(bytes_recv_rate / 1024, 2)}; self.last_net_io_counters = net_io; self.last_net_collection_time = current_time; state["network_counters"] = net_io._asdict()
            try: net_conns = psutil.net_connections(kind='inet'); state["network_connections"] = {"listening": len([c for c in net_conns if c.status == psutil.CONN_LISTEN]), "established": len([c for c in net_conns if c.status == psutil.CONN_ESTABLISHED])}
            except psutil.AccessDenied: state["network_connections"] = {"error": "Access Denied"}
            except Exception as net_e: self.logger.warning(f"Net connections error: {net_e}"); state["network_connections"] = {"error": str(net_e)}
            pids = psutil.pids(); state["processes"] = {"total": len(pids), "zombie": 0};
            try: state["processes"]["zombie"] = len([p for p in psutil.process_iter(['status'], zombie_processes_skip=False) if p.info['status'] == psutil.STATUS_ZOMBIE])
            except psutil.Error as proc_e: self.logger.warning(f"Zombie count error: {proc_e}")
            state["temperature_celsius"] = self._get_temperatures(); state["uptime_seconds"] = time.time() - psutil.boot_time()
        except psutil.Error as e: self.logger.error(f"psutil state error: {e}", exc_info=True); state["error"] = f"psutil error: {e}"
        except Exception as e: self.logger.error(f"State collection error: {e}", exc_info=True); state["error"] = f"General error: {e}"
        return state

    def _get_temperatures(self) -> Dict[str, float]:
        # ... (Same as v1.6.1) ...
        temps = {}; if not hasattr(psutil, "sensors_temperatures"): return temps
        try:
            psutil_temps = psutil.sensors_temperatures()
            for name, entries in psutil_temps.items():
                for i, entry in enumerate(entries): key = f"{name}_{i}_{entry.label or 'sensor'}"; if isinstance(entry.current, (int, float)): temps[key] = round(entry.current, 1)
        except Exception as e: self.logger.warning(f"Temp read error: {e}")
        return temps

    # --- Diagnostics ---
    def diagnose_system(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Performs structured diagnostics, triggers alert if needed."""
        # ... (Logic is sound, no major changes from v1.6.1) ...
        self.logger.debug("Running diagnostics..."); diagnostics = {"overall_status": "NOMINAL", "checks": {}}; issues = False
        diag_funcs = {"cpu": self._diagnose_cpu, "memory": self._diagnose_memory, "disk": self._diagnose_disk, "processes": self._diagnose_processes, "network": self._diagnose_network, "temperature": self._diagnose_temperature}
        for key, func in diag_funcs.items():
            try: diagnostics["checks"][key] = func(state.get(key)); status = diagnostics["checks"][key]["status"]; # Pass empty dict if key missing
                 if status == "ERROR": diagnostics["overall_status"] = "ERROR"; issues = True; break
                 elif status == "CRITICAL": diagnostics["overall_status"] = "CRITICAL"; issues = True
                 elif status == "WARNING" and diagnostics["overall_status"] == "NOMINAL": diagnostics["overall_status"] = "WARNING"; issues = True
            except Exception as e: self.logger.error(f"Diag check '{key}' error: {e}", exc_info=True); diagnostics["checks"][key] = self._create_health_result("ERROR", [{"type": "DIAG_ERROR", "description": str(e)}]); diagnostics["overall_status"] = "ERROR"; issues = True
        self.logger.info(f"Diagnostics complete. Overall: {diagnostics['overall_status']}");
        if issues: self.logger.warning(f"Diagnostic Details: {json.dumps(diagnostics['checks'], indent=2)}"); self._alert_if_needed(diagnostics)
        return diagnostics

    def _create_health_result(self, status: str = "NOMINAL", issues: Optional[List[Dict]] = None) -> Dict[str, Any]:
        return {"status": status, "issues": issues or []}

    def _add_issue(self, health: Dict, type: str, val: Any, desc: str, sev: str = "WARNING") -> Dict[str, Any]:
        health["issues"].append({"type": type, "value": val, "description": desc}); cs = health["status"]
        sev_map = {"NOMINAL":0, "WARNING": 1, "CRITICAL": 2, "ERROR": 3}
        if sev_map.get(sev, 0) > sev_map.get(cs, 0): health["status"] = sev # Update if higher severity
        return health

    # ... (Individual _diagnose_* methods remain the same core logic) ...
    def _diagnose_cpu(self, s: Optional[dict]) -> dict: h=self._create_health_result(); t=self.config['cpu_threshold']; if not s: return self._add_issue(h,"MISSING",0,"CPU data","ERROR"); if s.get("percent",0)>t: h=self._add_issue(h,"HIGH_CPU",s["percent"],f"> {t}%","CRITICAL"); c=s.get("cores_logical"); l=s.get("load_avg_1m_5m_15m",[0])[0]; if c and l>c*1.5: h=self._add_issue(h,"HIGH_LOAD",round(l,2),f"Load > 1.5x cores","WARNING"); return h
    def _diagnose_memory(self, s: Optional[dict]) -> dict: h=self._create_health_result(); vt=self.config['memory_threshold']; st=self.config['swap_threshold']; if not s: return self._add_issue(h,"MISSING",0,"Mem data","ERROR"); if s.get("virtual_percent",0)>vt: h=self._add_issue(h,"HIGH_MEM",s["virtual_percent"],f"> {vt}%","CRITICAL"); if s.get("swap_percent",0)>st: h=self._add_issue(h,"HIGH_SWAP",s["swap_percent"],f"> {st}%","WARNING"); return h
    def _diagnose_disk(self, s: Optional[dict]) -> dict: h=self._create_health_result(); t=self.config['disk_threshold']; if not s: return self._add_issue(h,"MISSING",0,"Disk data","ERROR"); if s.get("percent",0)>t: h=self._add_issue(h,"LOW_DISK",s["percent"],f"Disk '{s.get('path','?')}' > {t}%","CRITICAL"); return h
    def _diagnose_processes(self, s: Optional[dict]) -> dict: h=self._create_health_result(); t=self.config['zombie_threshold']; if not s: return self._add_issue(h,"MISSING",0,"Proc data","ERROR"); if s.get("zombie",0)>t: h=self._add_issue(h,"ZOMBIES",s["zombie"],f"> {t} zombies","WARNING"); return h
    def _diagnose_network(self, s: Optional[dict]) -> dict:
        h=self._create_health_result(); if s is None: return self._add_issue(h,"MISSING",0,"Net data(Collection Error)","ERROR"); ch=self.config['network_connectivity_host']; cp=self.config['network_connectivity_port']; ct=self.config['network_connectivity_timeout'];
        try: sock=socket.create_connection((ch,cp),timeout=ct); sock.close()
        except Exception as e: h=self._add_issue(h,"NET_CONNECT",0,f"No reach {ch}:{cp} ({type(e).__name__})","CRITICAL")
        counters = s.get("network_counters", {}); err_thresh = 100; drop_thresh = 1000 # Example thresholds
        if counters.get("errin",0)>err_thresh or counters.get("errout",0)>err_thresh: h=self._add_issue(h,"NET_ERRORS",{"in":counters.get("errin"),"out":counters.get("errout")},"High NIC errors","WARNING")
        if counters.get("dropin",0)>drop_thresh or counters.get("dropout",0)>drop_thresh: h=self._add_issue(h,"NET_DROPS",{"in":counters.get("dropin"),"out":counters.get("dropout")},"High NIC drops","WARNING")
        return h
    def _diagnose_temperature(self, s: Optional[dict]) -> dict: h=self._create_health_result(); t=self.config['temp_alert_threshold']; if s is None: return self._add_issue(h,"MISSING",0,"Temp data(Collection Error)","ERROR"); if not s and hasattr(psutil,"sensors_temperatures"): return self._add_issue(h,"MISSING",0,"Temp read failed","WARNING"); elif not s: return h; ht=[{"s":n,"t":tv} for n,tv in s.items() if tv>t]; if ht: h=self._add_issue(h,"HIGH_TEMP",ht,f"Sensor(s) > {t}°C","CRITICAL"); return h

    # --- AI Analysis ---
    def _generate_ai_prompt(self, system_state: Dict, diagnostics: Dict) -> str:
        # ... (Same prompt as v1.6.1) ...
        state_summary = {k: v for k, v in system_state.items() if k != "network_counters"}
        prompt = f"""Objective: Analyze AION server state/diagnostics. ID root causes, severity, recommend actions. State: {json.dumps(state_summary, indent=1, default=str, sort_keys=True)} Diagnostics: {json.dumps(diagnostics, indent=1, default=str, sort_keys=True)} Analysis Request: 1. Overall Health: 2. Key Issues & Severity: 3. Probable Causes: 4. Prioritized Recommendations: 5. Severity Score (1-10): Format: Use clear headings."""
        return prompt
    def request_ai_analysis(self, system_state: Dict, diagnostics: Dict) -> Optional[str]:
        # ... (Same logic as v1.6.1) ...
        if not self.ollama_client: self.logger.debug("Ollama client skip."); return None
        self.logger.info("Requesting AI analysis..."); prompt = self._generate_ai_prompt(system_state, diagnostics); model = self.config["ollama_model"]
        try:
            response = self.ollama_client.chat(model=model, messages=[{'role': 'user', 'content': prompt}], stream=False)
            analysis = response['message']['content']; self.logger.info(f"AI Analysis OK ({model}).")
            self.logger.debug(f"AI Full:\n{analysis}"); summary = "\n".join(line for i, line in enumerate(analysis.splitlines()) if i < 8 and line.strip()); self.logger.info(f"AI Summary:\n{summary}\n...")
            return analysis
        except ollama.ResponseError as e: self.logger.error(f"Ollama API Error: Status {e.status_code}, Error: {e.error}"); return f"AI Fail: Ollama API Error {e.status_code}"
        except Exception as e: self.logger.error(f"AI analysis fail: {e}", exc_info=True); return f"AI Fail: {type(e).__name__}"

    # --- Self-Healing ---
    def perform_self_healing(self, diagnostics: Dict):
        # ... (Same logic as v1.6.1) ...
        if not self.config.get("self_healing_enabled"): return
        self.logger.warning(f"Overall status {diagnostics['overall_status']}, checking heal actions...")
        actions = []; checks = diagnostics["checks"]
        if checks["cpu"]["status"] != "NOMINAL": actions.append(self._heal_cpu(checks["cpu"]))
        if checks["memory"]["status"] != "NOMINAL": actions.append(self._heal_memory())
        if checks["processes"]["status"] != "NOMINAL": actions.append(self._heal_processes())
        if checks["disk"]["status"] != "NOMINAL": actions.append(self._heal_disk())
        if checks["network"]["status"] != "NOMINAL": actions.append(self._heal_network())
        actions = [a for a in actions if a]
        if actions: self.logger.warning(f"Self-Healing Actions: {json.dumps(actions, indent=2)}")
        else: self.logger.info("No self-healing actions triggered.")

    def _run_subprocess(self, command_list: List[str], check: bool = False, use_sudo: bool = False, shell: bool = False, input_str: Optional[str] = None, timeout_sec: int = 60) -> Tuple[bool, str]:
        # ... (Improved logic from v1.6.1 remains suitable) ...
        sudo_used = False; cmd_str_log = ' '.join(command_list) # For logging
        if use_sudo and os.geteuid() != 0:
            sudo_path = shutil.which('sudo');
            if not sudo_path: self.logger.error("'sudo' needed but not found."); return False, "sudo not found"
            command_list.insert(0, sudo_path); sudo_used = True; cmd_str_log = ' '.join(command_list)
        cmd_path = shutil.which(command_list[0]);
        if not cmd_path and not shell: self.logger.error(f"Command not found: {command_list[0]}"); return False, f"Command not found: {command_list[0]}"
        if not shell and cmd_path: command_list[0] = cmd_path # Use full path
        self.logger.info(f"Running command: {cmd_str_log}")
        try:
            process = subprocess.Popen(command_list, stdin=subprocess.PIPE if input_str else None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=shell, bufsize=1, universal_newlines=True)
            stdout_output, stderr_output = process.communicate(input=input_str, timeout=timeout_sec)
            rc = process.returncode; combined_output = (stdout_output.strip() + "\n" + stderr_output.strip()).strip()
            if rc == 0: self.logger.info(f"Command OK (RC:{rc})."); return True, combined_output
            else: error_msg = f"Command failed (RC:{rc}): {cmd_str_log}. Output: {combined_output}";
                  if check: raise subprocess.CalledProcessError(rc, cmd=cmd_str_log, output=stdout_output, stderr=stderr_output)
                  else: self.logger.warning(error_msg); if sudo_used: self.logger.warning("Failure may be due to sudo permissions."); return False, combined_output
        except FileNotFoundError: self.logger.error(f"Cmd not found error: {command_list[0]}"); return False, f"Cmd not found: {command_list[0]}"
        except subprocess.TimeoutExpired: self.logger.error(f"Cmd timed out ({timeout_sec}s): {cmd_str_log}"); process.kill(); _, stderr = process.communicate(); return False, f"Cmd timed out. Stderr: {stderr.strip()}"
        except subprocess.CalledProcessError as e: self.logger.error(f"Cmd failed (RC:{e.returncode}, Check=True): {cmd_str_log}. Output: {(e.stderr or '').strip()}"); return False, (e.stderr or "").strip()
        except Exception as e: self.logger.error(f"Unexpected error running {cmd_str_log}: {e}", exc_info=True); return False, str(e)

    # --- Refined Healing Methods with Internal Enable Checks ---
    def _heal_cpu(self, cpu_diag: Dict) -> Optional[Dict]:
        # ... (Same as v1.6.1, including sudo comment) ...
        if not self.config.get("self_heal_cpu_enabled"): return None
        cpu_percent = next((i['value'] for i in cpu_diag['issues'] if i['type'] == 'HIGH_CPU_USAGE'), 0)
        if cpu_percent < self.config.get("self_heal_cpu_threshold", 95.0): return None
        self.logger.warning(f"Attempting CPU heal (Usage:{cpu_percent}%)...")
        action = {"action": "MITIGATE_CPU_PRESSURE", "killed_pids": [], "status": "ATTEMPTED"}
        exclude = {p.lower() for p in self.config.get("self_heal_cpu_exclude_procs", [])}
        limit = self.config['self_heal_cpu_kill_limit']; killed_count = 0
        try:
            procs = sorted([p for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'username', 'create_time']) if p.info['cpu_percent'] is not None], key=lambda x: x.info['cpu_percent'], reverse=True)
            for proc in procs:
                if killed_count >= limit: break
                pinfo = proc.info; pname = (pinfo['name'] or 'unknown').lower()
                if pinfo['cpu_percent'] > self.config['cpu_threshold'] and pname not in exclude and pinfo['username'] != 'root' and (time.time() - pinfo['create_time']) > 10:
                    self.logger.warning(f"CPU Heal: Terminate PID {pinfo['pid']} (Name:{pname}, User:{pinfo['username']}, CPU:{pinfo['cpu_percent']:.1f}%)")
                    # Requires sudo=True to allow killing other users' processes (needs external sudoers config)
                    success, _ = self._run_subprocess(['kill', str(pinfo['pid'])], use_sudo=True)
                    if success: action["killed_pids"].append(pinfo['pid']); killed_count += 1; time.sleep(0.5)
            action["killed_count"] = killed_count
        except Exception as e: self.logger.error(f"CPU heal error: {e}"); action = {"action": "MITIGATE_CPU_PRESSURE", "status": "FAILED", "error": str(e)}
        return action

    def _heal_memory(self) -> Optional[Dict]:
        # ... (Same as v1.6.1, including sudo comment) ...
        if not self.config.get("self_heal_memory_enabled") or not self.config.get("self_heal_memory_clear_caches"): return None
        self.logger.warning("Attempting memory heal: Clearing caches...")
        # Requires root/sudo
        success, output = self._run_subprocess(['sh', '-c', 'sync && echo 3 > /proc/sys/vm/drop_caches'], use_sudo=True, shell=True)
        return {"action": "CLEAR_MEMORY_CACHES", "status": "SUCCESS" if success else "FAILED", "details": output if not success else "Caches dropped."}

    def _heal_processes(self) -> Optional[Dict]:
        # ... (Same as v1.6.1, including sudo comment) ...
        if not self.config.get("self_heal_processes_enabled") or not self.config.get("self_heal_processes_cleanup_zombies"): return None
        self.logger.warning("Attempting process heal: Cleaning zombies...")
        action = {"action": "CLEANUP_ZOMBIE_PROCESSES", "status": "SUCCESS"}
        try:
            zombies = [p for p in psutil.process_iter(['pid', 'status'], zombie_processes_skip=False) if p.info['status'] == psutil.STATUS_ZOMBIE]
            if not zombies: action["status"] = "NO_ACTION_NEEDED"; return action
            pids = [p.pid for p in zombies]; action["zombies_found"] = pids
            self.logger.warning(f"Found {len(pids)} zombies: {pids}. Signaling init...")
            # Requires root/sudo to signal PID 1
            success, _ = self._run_subprocess(['kill', '-s', 'SIGCHLD', '1'], use_sudo=True)
            action["sigchld_sent"] = success
        except Exception as e: action = {"action": "CLEANUP_ZOMBIE_PROCESSES", "status": "FAILED", "error": str(e)}
        return action

    def _heal_disk(self) -> Optional[Dict]:
        # ... (Same as v1.6.1, including sudo comment) ...
        if not self.config.get("self_heal_disk_enabled"): return None
        self.logger.warning("Attempting disk heal: Cleaning logs/temp...")
        action = {"action": "MANAGE_DISK_SPACE", "status": "SUCCESS", "details": []}; success_overall = True
        items = [ {"path": self.config['self_heal_disk_log_path'], "age": str(self.config['self_heal_disk_log_max_age_days']), "type": "log", "tf": "-mtime"}, {"path": self.config['self_heal_disk_tmp_path'], "age": str(self.config['self_heal_disk_tmp_max_age_days']), "type": "tmp", "tf": "-atime"} ]
        try:
            for item in items:
                path, age, type, tf = item["path"], item["age"], item["type"], item["tf"]
                detail = {"path": path, "age_days": age, "success": False, "output": "Path does not exist/skipped."}
                if os.path.isdir(path):
                    # Requires sudo for system dirs
                    cmd = ['find', path, '-type', 'f', tf, f'+{age}', '-print', '-delete']
                    success, out = self._run_subprocess(cmd, use_sudo=True)
                    detail = {"path": path, "age_days": age, "success": success, "output": out if not success else f"Deleted old {type} files found."}
                    if not success: success_overall = False
                else:
                     self.logger.warning(f"Disk heal skipped for non-existent path: {path}")
                     success_overall = False # Consider this a partial failure if path doesn't exist? Or just log? Currently marking as partial.
                action["details"].append(detail)
            if not success_overall: action["status"] = "PARTIAL_FAILURE"
        except Exception as e: action = {"action": "MANAGE_DISK_SPACE", "status": "FAILED", "error": str(e)}
        return action

    def _heal_network(self) -> Optional[Dict]:
        # ... (Same as v1.6.1, including sudo comment) ...
        if not self.config.get("self_heal_network_enabled"): return None
        self.logger.warning("Attempting network heal: Restarting services...")
        action = {"action": "RESTART_NETWORKING", "status": "FAILED", "services_attempted": [], "success_service": None, "last_error": ""}
        services = self.config.get("self_heal_network_service_names", [])
        if not services: self.logger.warning("No network services configured."); return None
        # Requires root/sudo
        for service in services:
            action["services_attempted"].append(service); self.logger.info(f"Attempting restart: {service}")
            success, output = self._run_subprocess(['systemctl', 'restart', service], use_sudo=True)
            if success: action["status"] = "SUCCESS"; action["success_service"] = service; self.logger.info(f"Restarted {service}."); break
            else: self.logger.warning(f"Restart '{service}' failed: {output}"); action["last_error"] = output
        return action

    # --- Periodic Tasks ---
    def _update_man_db_if_needed(self):
        # ... (Same as v1.6.1, including sudo comment) ...
        interval = 3600 * self.config.get("mandb_min_interval_hours", 6)
        if time.time() - self.last_mandb_run_time < interval: return
        try:
            cpu_usage = psutil.cpu_percent(interval=0.1)
            permit_threshold = self.config.get("cpu_permit_man_update", 50.0)
            if cpu_usage < permit_threshold:
                self.logger.info(f"CPU low ({cpu_usage}%), running `mandb`.")
                # Needs root/sudo
                success, output = self._run_subprocess(['mandb', '-q'], use_sudo=True)
                if success: self.logger.info("Man-db updated."); self.last_mandb_run_time = time.time()
                else: self.logger.error(f"`mandb` failed: {output}")
            else: self.logger.debug(f"CPU {cpu_usage}% too high for `mandb`.")
        except Exception as e: self.logger.error(f"Error checking/running mandb: {e}", exc_info=True)


    # --- Alerting ---
    def _send_email_alert(self, subject: str, body: str):
        # ... (Same logic as v1.6.1) ...
        if not self.config.get("email_alerts_enabled"): return
        recipient=self.config.get("email_recipient"); sender=self.config.get("email_sender"); host=self.config.get("smtp_host"); port=self.config.get("smtp_port")
        if not recipient: self.logger.error("Email alerts enabled but no recipient."); return
        self.logger.info(f"Sending email: To={recipient}, Subject={subject}")
        full_body = f"{body}\n\n--\nAION Agent v{self.VERSION} on {socket.gethostname()}"
        msg = MIMEText(full_body); msg["Subject"] = f"[AION Agent] {subject}"; msg["From"] = sender; msg["To"] = recipient
        try:
            with smtplib.SMTP(host, port, timeout=10) as server: server.sendmail(sender, [recipient], msg.as_string())
            self.logger.info("Email alert sent.")
        except smtplib.SMTPConnectError: self.logger.error(f"SMTP Connect Error {host}:{port}.")
        except Exception as e: self.logger.error(f"Email send fail {host}:{port}: {e}", exc_info=True)

    def _alert_if_needed(self, diagnostics: Dict):
        """Helper to trigger email alert based on overall status."""
        # ... (Same logic as v1.6.1) ...
        if diagnostics['overall_status'] != "NOMINAL":
             self._send_email_alert(f"System Status {diagnostics['overall_status']}", f"Diagnostics detected issues.\nOverall: {diagnostics['overall_status']}\n\nDetails:\n{json.dumps(diagnostics['checks'], indent=2)}")

    # --- Main Execution ---
    def run(self):
        """Main monitoring loop with graceful shutdown."""
        # ... (Main loop logic refined slightly in v1.6.1 for interruptible sleep remains good) ...
        while self.running:
            start_time = time.time()
            self.logger.info("--- Cycle START ---")
            try:
                system_state = self.get_system_state()
                if "error" in system_state: self.logger.error(f"State collection error: {system_state['error']}"); time.sleep(self.config['monitor_interval']); continue # Short sleep on error

                diagnostics = self.diagnose_system(system_state) # Alerting done inside

                if self.ollama_client: self.request_ai_analysis(system_state, diagnostics)

                if diagnostics["overall_status"] != "NOMINAL": self.perform_self_healing(diagnostics)

                self._update_man_db_if_needed()
                # Add other periodic tasks here...

            except Exception as e: self.logger.critical(f"Unhandled main loop error: {e}", exc_info=True)

            cycle_duration = time.time() - start_time
            self.logger.info(f"--- Cycle END ({cycle_duration:.2f}s) ---")
            sleep_duration = max(1.0, self.config['monitor_interval'] - cycle_duration)
            # Interruptible sleep
            sleep_end = time.monotonic() + sleep_duration
            while self.running and time.monotonic() < sleep_end:
                 time.sleep(min(0.5, sleep_end - time.monotonic())) # Check running flag every 0.5s
            if not self.running: break # Exit loop if flag changed during sleep

        self.logger.info("===== AION System Agent Shutting Down =====")


# --- Entry Point ---
if __name__ == "__main__":
    agent = None
    try:
        intended_user = "aion"; current_user = "unknown"
        try: current_user = pwd.getpwuid(os.geteuid()).pw_name
        except Exception: pass # Ignore errors getting username
        if current_user != intended_user: print(f"WARNING: Agent intended for '{intended_user}', running as '{current_user}'. Check sudo rules.", file=sys.stderr)

        agent = AionSystemAgent()
        agent.run()
    except KeyboardInterrupt: print("\nCtrl+C detected. Shutting down...", file=sys.stderr);
    except Exception as e: # Catch broader exceptions during init or run
        timestamp = datetime.now().isoformat()
        error_msg = f"{timestamp} - CRITICAL STARTUP/RUNTIME ERROR: {e}\n{traceback.format_exc()}"
        print(error_msg, file=sys.stderr)
        try: open("/tmp/aion_agent_critical_error.log", "a").write(error_msg) # Fallback log
        except Exception: pass
        sys.exit(1)
    finally:
        if agent: agent.running = False # Ensure flag is set even on non-KeyboardInterrupt exit
        logging.shutdown(); # Ensure log handlers flushed/closed
        print("Agent exited.", file=sys.stderr)
        sys.exit(0) # Explicitly exit 0 on clean shutdown
