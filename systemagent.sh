#!/bin/bash
# /home/aion/systemagent.sh
# AION System Agent (Bash Version) - Monitoring & Alerting Script
# Version: 1.4.0 (Includes Port Status Check)
# NOTE: This is an alternative implementation. systemagent.py (v1.7.0+) is recommended.
# Run as: aion user within the AION chroot environment

# --- Strict Mode & Error Handling ---
set -euo pipefail

# --- Configuration File Path ---
readonly CONFIG_FILE="/opt/aion/config/system_agent.conf" # INI Style for Bash version
readonly SCRIPT_NAME=$(basename "$0")
readonly SCRIPT_DIR=$(dirname "$(readlink -f "$0")")

# --- Default Configuration ---
DEFAULT_MONITOR_INTERVAL=60; DEFAULT_AION_AGENT_LOG_FILE="/opt/aion/logs/system_agent.sh.log"; DEFAULT_CPU_ALERT_THRESHOLD=90; DEFAULT_MEM_ALERT_THRESHOLD=90; DEFAULT_DISK_ALERT_THRESHOLD=85; DEFAULT_DISK_FILESYSTEM="/"; DEFAULT_NETWORK_CHECK_HOST="1.1.1.1"; DEFAULT_NETWORK_CHECK_ENABLED=true; DEFAULT_PROCESS_SERVICE_CHECK_ENABLED=true; DEFAULT_PROCESS_NAME_TO_CHECK="ollama"; DEFAULT_SERVICE_NAME_TO_CHECK="ollama-chroot.service"; DEFAULT_EXPECTED_SERVICE_STATE="active"; DEFAULT_PORT_CHECK_ENABLED=true; DEFAULT_PORT_TO_CHECK=11434; DEFAULT_PORT_EXPECTED_STATE="listening"; DEFAULT_PORT_EXPECTED_LISTEN_IP="127.0.0.1"; DEFAULT_EMAIL_ALERTS_ENABLED=true; DEFAULT_EMAIL_RECIPIENT="aion@pythai.net"; DEFAULT_EMAIL_SUBJECT_PREFIX="[AION Agent Bash Alert]"; DEFAULT_ALERT_COOLDOWN=3600; DEFAULT_SELF_HEAL_ENABLED=false; DEFAULT_SELF_HEAL_SERVICE_TO_RESTART="ollama-chroot.service"

# --- Global Variables ---
MONITOR_INTERVAL=""; AION_AGENT_LOG_FILE=""; CPU_ALERT_THRESHOLD=""; MEM_ALERT_THRESHOLD=""; DISK_ALERT_THRESHOLD=""; DISK_FILESYSTEM=""; NETWORK_CHECK_HOST=""; NETWORK_CHECK_ENABLED=""; PROCESS_SERVICE_CHECK_ENABLED=""; PROCESS_NAME_TO_CHECK=""; SERVICE_NAME_TO_CHECK=""; EXPECTED_SERVICE_STATE=""; PORT_CHECK_ENABLED=""; PORT_TO_CHECK=""; PORT_EXPECTED_STATE=""; PORT_EXPECTED_LISTEN_IP=""; EMAIL_ALERTS_ENABLED=""; EMAIL_RECIPIENT=""; EMAIL_SUBJECT_PREFIX=""; ALERT_COOLDOWN=""; SELF_HEAL_ENABLED=""; SELF_HEAL_SERVICE_TO_RESTART=""
declare -A LAST_ALERT_TIME

# --- Logging Function ---
log_msg() { local m="$1"; local l="${2:-INFO}"; local f="${AION_AGENT_LOG_FILE:-/tmp/system_agent_sh_early.log}"; local t; t=$(date --iso-8601=seconds); local d; d=$(dirname "$f"); if [[ ! -d "$d" ]]; then mkdir -p "$d" || { echo "$t - CRITICAL - Cannot create log dir: $d" >&2; f="/tmp/${SCRIPT_NAME}.fallback.log"; echo "$t - CRITICAL - Fallback log: $f" >&2; }; fi; echo "$t - $l - $m" >> "$f" || { echo "$t - ERROR - Failed write log: $f" >&2; }; if [[ "$l" == "ERROR" || "$l" == "CRITICAL" ]]; then echo "$t - $l - $m" >&2; fi; }

# --- Configuration Loading (Simplified INI style) ---
load_config() {
    log_msg "Loading config $CONFIG_FILE (INI style)..."
    # Set all defaults first (long line, unavoidable in bash for this style)
    MONITOR_INTERVAL="$DEFAULT_MONITOR_INTERVAL"; AION_AGENT_LOG_FILE="$DEFAULT_AION_AGENT_LOG_FILE"; CPU_ALERT_THRESHOLD="$DEFAULT_CPU_ALERT_THRESHOLD"; MEM_ALERT_THRESHOLD="$DEFAULT_MEM_ALERT_THRESHOLD"; DISK_ALERT_THRESHOLD="$DEFAULT_DISK_ALERT_THRESHOLD"; DISK_FILESYSTEM="$DEFAULT_DISK_FILESYSTEM"; NETWORK_CHECK_HOST="$DEFAULT_NETWORK_CHECK_HOST"; NETWORK_CHECK_ENABLED="$DEFAULT_NETWORK_CHECK_ENABLED"; PROCESS_SERVICE_CHECK_ENABLED="$DEFAULT_PROCESS_SERVICE_CHECK_ENABLED"; PROCESS_NAME_TO_CHECK="$DEFAULT_PROCESS_NAME_TO_CHECK"; SERVICE_NAME_TO_CHECK="$DEFAULT_SERVICE_NAME_TO_CHECK"; EXPECTED_SERVICE_STATE="$DEFAULT_EXPECTED_SERVICE_STATE"; PORT_CHECK_ENABLED="$DEFAULT_PORT_CHECK_ENABLED"; PORT_TO_CHECK="$DEFAULT_PORT_TO_CHECK"; PORT_EXPECTED_STATE="$DEFAULT_PORT_EXPECTED_STATE"; PORT_EXPECTED_LISTEN_IP="$DEFAULT_PORT_EXPECTED_LISTEN_IP"; EMAIL_ALERTS_ENABLED="$DEFAULT_EMAIL_ALERTS_ENABLED"; EMAIL_RECIPIENT="$DEFAULT_EMAIL_RECIPIENT"; EMAIL_SUBJECT_PREFIX="$DEFAULT_EMAIL_SUBJECT_PREFIX"; ALERT_COOLDOWN="$DEFAULT_ALERT_COOLDOWN"; SELF_HEAL_ENABLED="$DEFAULT_SELF_HEAL_ENABLED"; SELF_HEAL_SERVICE_TO_RESTART="$DEFAULT_SELF_HEAL_SERVICE_TO_RESTART"

    if [[ -f "$CONFIG_FILE" && -r "$CONFIG_FILE" ]]; then
        log_msg "Reading $CONFIG_FILE...";
        # Simple INI parsing (handles VAR=value, ignores comments/blanks)
        while IFS='=' read -r key value || [[ -n "$key" ]]; do
            key=$(echo "$key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//') # Trim whitespace
            [[ -z "$key" || "$key" =~ ^# || "$key" =~ ^; ]] && continue # Skip blanks/comments
            value=$(echo "$value" | sed 's/^[[:space:]"]*//;s/[[:space:]"]*$//') # Trim whitespace/quotes
            # Use eval carefully to assign variables dynamically (ensure keys are safe)
            if [[ "$key" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then # Basic check for valid var name
                eval "$key=\"\$value\"" # Assign value to variable named by key
            else log_msg "Skipping potentially unsafe key in config: $key" "WARN"; fi
        done < "$CONFIG_FILE"
        log_msg "Config loaded."
    else
        log_msg "Config $CONFIG_FILE not found/readable. Using defaults." "WARN"; AION_AGENT_LOG_FILE="$DEFAULT_AION_AGENT_LOG_FILE"; mkdir -p "$(dirname "$AION_AGENT_LOG_FILE")" || log_msg "Cannot create default log dir" "CRITICAL"
    fi
    log_msg "Effective config summary..." "INFO" # Log summary as in Python version
    log_msg "Log:$AION_AGENT_LOG_FILE Int:$MONITOR_INTERVAL Limits(CPU/Mem/Disk):$CPU_ALERT_THRESHOLD/$MEM_ALERT_THRESHOLD/$DISK_ALERT_THRESHOLD($DISK_FILESYSTEM)" "INFO"
    log_msg "Checks(Net/ProcSvc/Port):$NETWORK_CHECK_ENABLED/$PROCESS_SERVICE_CHECK_ENABLED/$PORT_CHECK_ENABLED" "INFO"
    log_msg "PortDetail(Port/ExpState/ExpIP):$PORT_TO_CHECK/$PORT_EXPECTED_STATE/$PORT_EXPECTED_LISTEN_IP" "INFO"
    log_msg "Alerts:$EMAIL_ALERTS_ENABLED($EMAIL_RECIPIENT Cool:$ALERT_COOLDOWN) Heal:$SELF_HEAL_ENABLED($SELF_HEAL_SERVICE_TO_RESTART)" "INFO"
}

# --- Alerting Function ---
send_alert() { local k="$1"; local s="$2"; local b="$3"; local ct; ct=$(date +%s); local lt=${LAST_ALERT_TIME[$k]:-0}; if [[ "$EMAIL_ALERTS_ENABLED"!="true" ]]; then log_msg "Email disabled. Skip: $s" "INFO"; return; fi; if (( ct < lt + ALERT_COOLDOWN )); then log_msg "Cooldown active [$k]. Skip: $s" "INFO"; return; fi; log_msg "Alert [$k]: $s" "WARN"; local fs="${EMAIL_SUBJECT_PREFIX} ${s}"; local hn; hn=$(hostname -f); local fb="Alert from AION Agent (Bash) on ${hn}: $b Time: $(date --iso-8601=seconds)"; if command -v mail &> /dev/null; then echo "$fb" | mail -s "$fs" "$EMAIL_RECIPIENT"; log_msg "Alert email sent ($EMAIL_RECIPIENT)." "INFO"; LAST_ALERT_TIME[$k]=$ct; else log_msg "Cannot send email: 'mail' cmd missing." "ERROR"; fi; }

# --- Check Functions ---
# ... (check_cpu, check_memory, check_disk, check_network, check_process_service, check_port_status from v1.4.0 Bash script) ...
check_cpu() { log_msg "CPU..." "INFO"; local cpu; if ! command -v mpstat &> /dev/null; then log_msg "mpstat missing." "ERROR"; return; fi; cpu=$(mpstat 1 1 | awk '/Average:/ {print 100 - $NF}' | cut -d. -f1); if [[ -z "$cpu" ]]; then log_msg "Failed parse mpstat." "ERROR"; return; fi; log_msg "CPU:$cpu%" "INFO"; if (( cpu > CPU_ALERT_THRESHOLD )); then send_alert "CPU_HIGH" "High CPU" "CPU ${cpu}% > ${CPU_ALERT_THRESHOLD}%."; fi; }
check_memory() { log_msg "Memory..." "INFO"; local mi mu mt ma mp; if ! mi=$(free -m); then log_msg "Failed 'free'." "ERROR"; return; fi; mt=$(echo "$mi" | awk '/^Mem:/ {print $2}'); ma=$(echo "$mi" | awk '/^Mem:/ {print $7}'); if [[ -z "$mt" || -z "$ma" ]]; then log_msg "Failed parse free." "ERROR"; return; fi; mu=$(( mt - ma )); mp=$(echo "scale=2; ($mu / $mt) * 100" | bc | cut -d. -f1); if [[ -z "$mp" ]]; then log_msg "Failed calc mem %." "ERROR"; return; fi; log_msg "Mem:$mp% ($mu MB used)" "INFO"; if (( mp > MEM_ALERT_THRESHOLD )); then send_alert "MEM_HIGH" "High Memory" "Memory ${mp}% > ${MEM_ALERT_THRESHOLD}%."; fi; }
check_disk() { log_msg "Disk $DISK_FILESYSTEM..." "INFO"; local du di; if ! di=$(df -Pkh "$DISK_FILESYSTEM" 2>/dev/null | awk 'NR==2'); then log_msg "FS $DISK_FILESYSTEM err/miss." "ERROR"; return; fi; du=$(echo "$di" | awk '{print $5}' | sed 's/%//'); if [[ -z "$du" ]]; then log_msg "Failed parse disk $DISK_FILESYSTEM." "ERROR"; return; fi; log_msg "Disk $DISK_FILESYSTEM:$du%" "INFO"; if (( du > DISK_ALERT_THRESHOLD )); then send_alert "DISK_HIGH_${DISK_FILESYSTEM//\//_}" "High Disk $DISK_FILESYSTEM" "Disk ${du}% > ${DISK_ALERT_THRESHOLD}%."; fi; }
check_network() { if [[ "$NETWORK_CHECK_ENABLED"!="true" ]]; then log_msg "NetPing disabled." "INFO"; return; fi; log_msg "NetPing $NETWORK_CHECK_HOST..." "INFO"; if ping -c 1 -W 5 "$NETWORK_CHECK_HOST" &> /dev/null; then log_msg "NetPing OK." "INFO"; else log_msg "NetPing FAILED $NETWORK_CHECK_HOST." "WARN"; send_alert "NET_DOWN" "Network Issue" "Ping failed: ${NETWORK_CHECK_HOST}."; fi; }
check_process_service() { if [[ "$PROCESS_SERVICE_CHECK_ENABLED" != "true" ]]; then log_msg "Proc/Svc check disabled." "INFO"; return; fi; if [[ -z "$PROCESS_NAME_TO_CHECK" || -z "$SERVICE_NAME_TO_CHECK" ]]; then log_msg "Proc/Svc check config incomplete." "WARN"; return; fi; log_msg "Proc/Svc: $PROCESS_NAME_TO_CHECK/$SERVICE_NAME_TO_CHECK (Exp:$EXPECTED_SERVICE_STATE)..." "INFO"; local pr=false; local sa=false; local s_state="unknown"; if pgrep -f "$PROCESS_NAME_TO_CHECK" &>/dev/null; then pr=true; fi; if sudo --non-interactive /bin/systemctl is-active "$SERVICE_NAME_TO_CHECK" &>/dev/null; then sa=true; s_state="active"; else s_state=$(sudo --non-interactive /bin/systemctl is-active "$SERVICE_NAME_TO_CHECK" 2>/dev/null || echo "inactive"); fi; log_msg "Proc: $([[ "$pr" == true ]] && echo Run || echo Stop). Svc: $s_state." "INFO"; local ok=false; if [[ "$EXPECTED_SERVICE_STATE" == "active" && "$sa" == true && "$pr" == true ]]; then ok=true; elif [[ "$EXPECTED_SERVICE_STATE" == "inactive" && "$sa" == false && "$pr" == false ]]; then ok=true; fi; if $ok; then log_msg "Proc/Svc state OK." "INFO"; else log_msg "Proc/Svc state MISMATCH (Exp:$EXPECTED_SERVICE_STATE)." "WARN"; send_alert "PROC_SVC_STATE_${SERVICE_NAME_TO_CHECK}" "Proc/Svc State Mismatch: $SERVICE_NAME_TO_CHECK" "State mismatch. Exp:$EXPECTED_SERVICE_STATE, Proc:$pr, Svc:$s_state."; if [[ "$EXPECTED_SERVICE_STATE" == "active" ]]; then attempt_self_heal; fi; fi; }
check_port_status() { if [[ "$PORT_CHECK_ENABLED" != "true" ]]; then log_msg "Port check disabled." "INFO"; return; fi; log_msg "Port $PORT_TO_CHECK (ExpState:$PORT_EXPECTED_STATE, ExpIP:$PORT_EXPECTED_LISTEN_IP)..." "INFO"; local listening=false; local listen_ip=""; local ss_out; if ss_out=$(ss -tlpn "sport == :$PORT_TO_CHECK" 2>/dev/null); then if [[ -n "$ss_out" ]]; then listening=true; listen_ip=$(echo "$ss_out" | awk 'NR==2 {print $4}' | sed -e 's/:[0-9]*$//' -e 's/^\[\(.*\)\]$/\1/' -e 's/^::1$/127.0.0.1/' -e 's/^::$/0.0.0.0/'); fi; else log_msg "'ss' cmd failed for port $PORT_TO_CHECK." "ERROR"; return; fi; if $listening; then log_msg "Port $PORT_TO_CHECK LISTENING on '$listen_ip'." "INFO"; if [[ "$PORT_EXPECTED_STATE" == "clear" ]]; then log_msg "Port $PORT_TO_CHECK unexpected LISTEN." "WARN"; send_alert "PORT_UNEXPECTED_LISTEN_${PORT_TO_CHECK}" "Port Unexpectedly Listening: $PORT_TO_CHECK" "Port $PORT_TO_CHECK listening ($listen_ip), expected clear."; elif [[ "$PORT_EXPECTED_LISTEN_IP" != "any" && "$listen_ip" != "$PORT_EXPECTED_LISTEN_IP" ]]; then log_msg "Port $PORT_TO_CHECK WRONG IP '$listen_ip' (exp '$PORT_EXPECTED_LISTEN_IP')." "WARN"; send_alert "PORT_WRONG_IP_${PORT_TO_CHECK}" "Port Wrong IP: $PORT_TO_CHECK" "Port $PORT_TO_CHECK listening $listen_ip, expected $PORT_EXPECTED_LISTEN_IP. Check host UFW/service bind."; else log_msg "Port $PORT_TO_CHECK listen state OK." "INFO"; fi; else log_msg "Port $PORT_TO_CHECK CLEAR." "INFO"; if [[ "$PORT_EXPECTED_STATE" == "listening" ]]; then log_msg "Port $PORT_TO_CHECK unexpected CLEAR." "WARN"; send_alert "PORT_UNEXPECTED_CLEAR_${PORT_TO_CHECK}" "Port Unexpectedly Clear: $PORT_TO_CHECK" "Port $PORT_TO_CHECK not listening, expected listening ($PORT_EXPECTED_LISTEN_IP)."; fi; fi; }
custom_checks() { log_msg "Custom checks (placeholder)..." "INFO"; }

# --- Self Healing Function ---
attempt_self_heal() { if [[ "$SELF_HEAL_ENABLED"!="true" ]]; then return; fi; if [[ -z "$SELF_HEAL_SERVICE_TO_RESTART" ]]; then log_msg "SELF_HEAL_SERVICE_TO_RESTART empty." "ERROR"; return; fi; log_msg "Attempt self-heal via service '$SELF_HEAL_SERVICE_TO_RESTART' due to check failure." "WARN"; # Requires sudo configured externally for aion user
    if sudo --non-interactive /bin/systemctl restart "$SELF_HEAL_SERVICE_TO_RESTART"; then log_msg "OK: sudo systemctl restart $SELF_HEAL_SERVICE_TO_RESTART." "INFO"; send_alert "SELF_HEAL_ATTEMPT" "Self-Heal Attempted" "Restarted ${SELF_HEAL_SERVICE_TO_RESTART}."; sleep 5; else log_msg "FAIL: sudo systemctl restart $SELF_HEAL_SERVICE_TO_RESTART. Check sudoers." "ERROR"; send_alert "SELF_HEAL_FAIL" "Self-Heal FAILED" "Failed restart ${SELF_HEAL_SERVICE_TO_RESTART}."; fi; }

# --- Dependency Check ---
check_dependencies() { log_msg "Checking deps..."; local missing=0; local cmds=("bc" "awk" "grep" "sed" "date" "ping" "df" "free" "mpstat" "pgrep" "hostname" "dirname" "readlink" "cut" "ss"); if [[ "$EMAIL_ALERTS_ENABLED"=="true" ]]; then cmds+=("mail"); fi; if [[ "$SELF_HEAL_ENABLED"=="true" || "$PROCESS_SERVICE_CHECK_ENABLED" == "true" ]]; then cmds+=("sudo" "systemctl"); fi; for cmd in "${cmds[@]}"; do if ! command -v "$cmd" &> /dev/null; then log_msg "Essential cmd '$cmd' missing." "CRITICAL"; missing=$((missing+1)); fi; done; if ! command -v mpstat &>/dev/null; then log_msg "'mpstat'(sysstat) needed." "WARN"; fi; if (( missing > 0 )); then log_msg "Exiting: missing deps." "CRITICAL"; exit 1; fi; log_msg "Deps OK." "INFO"; }

# --- Cleanup ---
cleanup() { log_msg "Signal received. Cleanup..." "INFO"; log_msg "AION System Agent (Bash) stopped." "INFO"; exit 0; }

# --- Main Loop ---
monitor_loop() { log_msg "Starting AION System Agent (Bash) monitoring loop (PID: $$)..."; while true; do log_msg "-- Checks cycle --"; ( check_cpu ); ( check_memory ); ( check_disk ); ( check_network ); ( check_process_service ); ( check_port_status ); ( custom_checks ); log_msg "-- Cycle done. Sleep $MONITOR_INTERVAL s..."; sleep "$MONITOR_INTERVAL"; done; }

# --- Entry Point ---
main() { trap cleanup SIGTERM SIGINT SIGHUP; log_msg "AION System Agent Script (Bash v1.4.0) Initializing..."; local req_user="aion"; if [[ "$(whoami)" != "$req_user" ]]; then log_msg "WARN: Should run as '$req_user', is '$(whoami)'." "WARN"; fi; load_config; check_dependencies; monitor_loop; }

# --- Execute ---
main "$@"
exit 0
