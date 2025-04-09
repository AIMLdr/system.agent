#!/bin/bash
# activate_aion_agent.sh - Deploys and runs systemagent.sh inside the AION chroot as user 'aion'.
# Place this script on the HOST machine, in the SAME directory as the systemagent.sh you want to deploy.

# --- Configuration ---
readonly CHROOT_DIR="/opt/aion_chroot"         # Path to the AION chroot environment on the host
readonly TARGET_USER="aion"                     # User inside the chroot to run the script as
readonly SCRIPT_TO_DEPLOY="systemagent.sh"      # Name of the agent script to deploy
readonly TARGET_PERMISSIONS="750"               # Permissions (rwx r-x ---)

# --- Internal Variables ---
# Get the directory where THIS activation script resides
readonly SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
# Path to the source script on the host
readonly SOURCE_SCRIPT_PATH="${SCRIPT_DIR}/${SCRIPT_TO_DEPLOY}"
# Path where the script will be placed INSIDE the chroot
readonly DEST_SCRIPT_PATH_CHROOT="/home/${TARGET_USER}/${SCRIPT_TO_DEPLOY}"
# Corresponding path on the HOST filesystem to copy to
readonly DEST_SCRIPT_PATH_HOST="${CHROOT_DIR}${DEST_SCRIPT_PATH_CHROOT}"

# --- Colors ---
readonly GREEN='\033[0;32m'; readonly YELLOW='\033[1;33m'; readonly RED='\033[0;31m'; readonly NC='\033[0m';

# --- Functions ---
log() { echo -e "$(date '+%Y-%m-%d %H:%M:%S') - INFO - $*"; }
error() { echo -e "$(date '+%Y-%m-%d %H:%M:%S') - ${RED}ERROR${NC} - $*" >&2; }
fail() { error "$@"; exit 1; }

# Check if running as root, rerun with sudo if not
check_root() {
  if [[ $EUID -ne 0 ]]; then
     log "Root privileges required via sudo. Re-running..."
     # Ensure script path is correctly passed to sudo
     exec sudo bash "$0" "$@"
     fail "Failed to rerun with sudo. Please ensure sudo is configured and password is correct (if required)."
  fi
  log "Running with sufficient privileges."
}

# --- Main Script ---
# Ensure script exits immediately if a command fails
set -e

log "Starting AION Agent Activation Script..."
log "Chroot Dir: $CHROOT_DIR"
log "Target User: $TARGET_USER"
log "Script to Deploy: $SCRIPT_TO_DEPLOY (from $SCRIPT_DIR)"

# 1. Check for Root/Sudo privileges
check_root

# 2. Check if chroot directory exists
if [[ ! -d "$CHROOT_DIR" ]]; then
    fail "AION Chroot directory '$CHROOT_DIR' not found on the host."
fi
log "Chroot directory found."

# 3. Check if the source script exists
if [[ ! -f "$SOURCE_SCRIPT_PATH" ]]; then
    fail "Source script '$SCRIPT_TO_DEPLOY' not found in the same directory as this script ($SCRIPT_DIR)."
fi
log "Source script '$SCRIPT_TO_DEPLOY' found."

# 4. Copy the script into the chroot's target home directory
log "Copying '$SCRIPT_TO_DEPLOY' to '$DEST_SCRIPT_PATH_HOST'..."
sudo cp "$SOURCE_SCRIPT_PATH" "$DEST_SCRIPT_PATH_HOST"
log "${GREEN}Copy successful.${NC}"

# 5. Set ownership within the chroot
log "Setting ownership to ${TARGET_USER}:${TARGET_USER} for '$DEST_SCRIPT_PATH_CHROOT' within chroot..."
# Use chroot command to execute chown relative to the chroot environment
sudo chroot "$CHROOT_DIR" chown "${TARGET_USER}:${TARGET_USER}" "$DEST_SCRIPT_PATH_CHROOT"
log "${GREEN}Ownership set successfully.${NC}"

# 6. Set permissions within the chroot
log "Setting permissions to '$TARGET_PERMISSIONS' for '$DEST_SCRIPT_PATH_CHROOT' within chroot..."
# Use chroot command to execute chmod relative to the chroot environment
sudo chroot "$CHROOT_DIR" chmod "$TARGET_PERMISSIONS" "$DEST_SCRIPT_PATH_CHROOT"
log "${GREEN}Permissions set successfully.${NC}"

# 7. Execute the script as the target user inside the chroot
log "${YELLOW}Executing '$DEST_SCRIPT_PATH_CHROOT' as user '$TARGET_USER' inside the chroot...${NC}"
echo "--- Agent Output Starts Below ---"
# Use 'su - user -c command' to run the command in the user's environment
# Pass the full path to the script within the chroot
sudo chroot "$CHROOT_DIR" su - "$TARGET_USER" -c "$DEST_SCRIPT_PATH_CHROOT"

# Check exit status of the agent script if needed (optional)
agent_exit_status=$?
echo "--- Agent Output Ended ---"
if [[ $agent_exit_status -eq 0 ]]; then
    log "${GREEN}Agent script execution completed successfully (Exit Code: 0).${NC}"
else
    # Use warning level for non-zero exit, as script might exit non-zero intentionally sometimes
    log "${YELLOW}Agent script execution finished with non-zero Exit Code: $agent_exit_status.${NC}"
    log "${YELLOW}Check agent output and logs ($AION_AGENT_LOG_FILE inside chroot) for details.${NC}"
fi

log "Activation script finished."
exit $agent_exit_status # Exit with the agent's exit code
