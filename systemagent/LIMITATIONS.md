# AION System Agent (systemagent.py) - Limitations

Version: 1.7.0

While the AION System Agent provides advanced monitoring and automation capabilities, it's crucial to understand its limitations and the context in which it operates.

## 1. Sudo Dependency and Security

*   **External Configuration:** The agent **relies entirely on external sudo configuration** for the `aion` user to perform privileged self-healing and maintenance tasks. The script *cannot* grant itself permissions.
*   **Passwordless Requirement:** These external sudo rules **must be passwordless** (`NOPASSWD`) for the agent to execute actions non-interactively.
*   **Security Risk:** Configuring passwordless sudo requires extreme care. Granting broad permissions (e.g., `ALL=(ALL) NOPASSWD: ALL`) is **highly insecure** and strongly discouraged, especially in production. If self-healing is used, **only grant sudo privileges for the *specific commands* absolutely required** by the enabled healing actions (e.g., specific `kill` permissions, `systemctl restart specific.service`, `mandb`, `find ... -delete` on specific paths, writing to `/proc/sys/vm/drop_caches`). A compromised `aion` user account with broad sudo privileges could compromise the entire system. **Review and restrict sudo rules regularly.** Verify that script files run via sudo are not writable by the agent user.

## 2. Self-Healing Risks

*   **Disruption:** Actions like restarting network services (`_heal_network`) can cause temporary or prolonged connectivity loss. Killing processes (`_heal_cpu`) can terminate essential user work or dependent services if not configured carefully (review the exclusion list). Clearing caches (`_heal_memory`) can temporarily increase I/O load. Disk cleanup (`_heal_disk`) can permanently delete files if paths/ages are misconfigured.
*   **Root Cause:** Self-healing treats symptoms. It might restart a crashing service but won't fix the underlying bug causing the crash. Persistent issues require manual investigation.
*   **Safety Guards:** While safety checks are implemented (e.g., not killing root/excluded processes, configurable thresholds), they may not cover all edge cases. **Use self-healing features with caution, understand their actions, and test thoroughly in a non-critical environment first.** Disable features (like CPU process killing or network restart) if their risk outweighs their benefit in your context.

## 3. Ollama Integration

*   **Availability:** AI analysis depends on a running, accessible Ollama service at the configured host/port and the availability of the specified model. Network issues or Ollama service failures will disable AI analysis. The agent attempts to verify connectivity during initialization.
*   **Blocking Pull:** If the configured Ollama model isn't present locally, the agent will attempt to pull it during initialization. This is a **blocking operation** and can significantly delay agent startup, especially for large models or slow networks. Consider pulling models manually beforehand.
*   **Analysis is Informational:** The agent currently **logs** the analysis provided by the LLM but **does not automatically act** upon its recommendations. Implementing actions based on potentially variable LLM output is complex and requires further development.
*   **Resource Cost:** Running LLM analysis consumes CPU, RAM, and potentially GPU resources on the Ollama host.

## 4. Firewall (UFW) Management

*   The agent runs *within* the chroot environment. It **cannot directly manage or configure the host system's firewall** (like UFW).
*   Firewall rules must be configured separately and directly on the **host system**.
*   The agent can *indirectly* monitor the *effect* of firewall rules by checking port listening status and IPs (logic exists in `systemagent.sh`, could be ported to Python if needed), but it cannot enforce or change the rules.

## 5. Error Handling & Diagnostics

*   While extensive error handling is included, complex system interactions or unexpected states might lead to unhandled exceptions or incorrect diagnoses.
*   Root cause analysis often requires manual intervention and examination of system logs beyond what the agent provides. The agent's logs (`system_agent.log`, `*.stderr.log`) are the first place to check.

## 6. Resource Consumption

*   The agent itself consumes some CPU and memory resources, although it is designed to be relatively lightweight. The `psutil` calls, especially `cpu_percent` with short intervals, contribute to this.
*   Frequent polling or computationally intensive checks increase overhead.

## 7. External Dependencies

*   **Python Libs:** Requires `psutil` and optionally `ollama` installed in its virtual environment.
*   **Email:** Alerting requires a functioning SMTP server/relay accessible from the chroot and correct configuration in `config.json`.
*   **Log Rotation:** Uses Python's `RotatingFileHandler`, which is generally sufficient. System-wide log management might still involve external `logrotate`.
*   **System Tools:** Relies on standard Linux commands (`kill`, `systemctl`, `find`, `mandb`, `sync`, `sh`, `sudo`, `echo`, etc.) being present in the chroot's PATH and behaving as expected.

## 8. State Management

*   The agent is mostly stateless between cycles, except for alert cooldown timers, network rate calculation state, and the `mandb` run timer. It doesn't track complex historical trends or state transitions (e.g., service flapping).
