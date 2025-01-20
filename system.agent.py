#!/usr/bin/env python3

import os
import psutil
import subprocess
import json
import time
from datetime import datetime
import smtplib
from email.mime.text import MIMEText

# Configuration
CONFIG_FILE = "config.json"
LOG_FILE = "/var/log/aion/system_agent.log"
DEFAULT_CONFIG = {
    "monitor_interval": 60,
    "cpu_alert_threshold": 90,
    "disk_alert_threshold": 80,
    "network_alert_threshold": 1000,  # in KB/s
    "temp_alert_threshold": 80,      # in Celsius
    "email_alerts": False,
    "email_recipient": "admin@example.com",
    "cpu_permit_man_update": 50
}

# Load configuration
try:
    with open(CONFIG_FILE, "r") as cfg:
        config = json.load(cfg)
except FileNotFoundError:
    print("config.json not found. Using defaults.")
    config = DEFAULT_CONFIG

# Ensure all keys are in the config
for k, v in DEFAULT_CONFIG.items():
    config.setdefault(k, v)

# Logging function
def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    output = f"{timestamp} - {message}"
    print(output)
    with open(LOG_FILE, "a") as lf:
        lf.write(output + "\n")

# Email alerts
def send_email_alert(subject, body):
    if not config["email_alerts"]:
        return
    recipient = config["email_recipient"]
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = "system-agent@localhost"
    msg["To"] = recipient
    try:
        with smtplib.SMTP("localhost") as server:
            server.sendmail(msg["From"], [msg["To"]], msg.as_string())
            log(f"Email alert sent to {recipient} with subject: {subject}")
    except Exception as e:
        log(f"Failed to send email alert: {e}")

# Monitor CPU
def monitor_cpu():
    cpu_usage = psutil.cpu_percent(interval=1)
    log(f"CPU usage: {cpu_usage}%")
    if cpu_usage > config["cpu_alert_threshold"]:
        log(f"High CPU usage detected: {cpu_usage}%")
        handle_high_cpu(cpu_usage)

# Monitor memory and disk
def monitor_memory_and_disk():
    mem_info = psutil.virtual_memory()
    disk_info = psutil.disk_usage("/")
    log(f"Memory usage: {mem_info.percent}%, Disk usage: {disk_info.percent}%")
    if disk_info.percent > config["disk_alert_threshold"]:
        log(f"High disk usage detected: {disk_info.percent}%")
        handle_high_disk(disk_info.percent)

# Monitor network usage
def monitor_network():
    net_before = psutil.net_io_counters()
    time.sleep(1)  # Measure over a 1-second interval
    net_after = psutil.net_io_counters()
    sent = (net_after.bytes_sent - net_before.bytes_sent) / 1024  # KB/s
    recv = (net_after.bytes_recv - net_before.bytes_recv) / 1024  # KB/s
    log(f"Network usage - Sent: {sent:.2f} KB/s, Received: {recv:.2f} KB/s")
    if max(sent, recv) > config["network_alert_threshold"]:
        log(f"High network usage detected: Sent={sent:.2f} KB/s, Received={recv:.2f} KB/s")
        send_email_alert("High Network Usage Alert", f"Sent: {sent:.2f} KB/s, Received: {recv:.2f} KB/s")

# Monitor temperatures
def monitor_temperatures():
    try:
        temps = psutil.sensors_temperatures()
        for name, entries in temps.items():
            for entry in entries:
                temp = entry.current
                log(f"Temperature sensor {name}: {temp}°C")
                if temp > config["temp_alert_threshold"]:
                    log(f"High temperature detected: {name} - {temp}°C")
                    send_email_alert("High Temperature Alert", f"{name} sensor is {temp}°C")
    except AttributeError:
        log("Temperature monitoring not supported on this system.")

# Handle high CPU
def handle_high_cpu(cpu_usage):
    log("Investigating high CPU usage.")
    try:
        output = subprocess.check_output(["ps", "aux", "--sort=-%cpu", "--no-headers"], text=True)
        top_lines = output.strip().split("\n")[:10]
        log("Top CPU processes:\n" + "\n".join(top_lines))
    except Exception as e:
        log(f"Failed to gather process list: {e}")
    send_email_alert("High CPU Usage Alert", f"CPU usage exceeded threshold: {cpu_usage}%")

# Handle high disk usage
def handle_high_disk(disk_percent):
    log("Attempting disk cleanup.")
    try:
        for root, dirs, files in os.walk("/var/log/aion"):
            for file in files:
                os.remove(os.path.join(root, file))
        log("Old log files removed.")
    except Exception as e:
        log(f"Failed to clean up logs: {e}")
    send_email_alert("High Disk Usage Alert", f"Disk usage is {disk_percent}%")

# Update manual database if CPU is low
def update_man_db_if_permitted():
    cpu_usage = psutil.cpu_percent(interval=1)
    if cpu_usage < config["cpu_permit_man_update"]:
        log(f"CPU usage low ({cpu_usage}%), running `mandb`.")
        try:
            subprocess.run(["mandb", "-q"], check=True)
            log("Manual page indexes updated.")
        except subprocess.CalledProcessError as e:
            log(f"`mandb` update failed: {e}")
    else:
        log(f"CPU usage {cpu_usage}% too high for `mandb` update.")

# Self-healing for stuck processes
def self_healing():
    one_hour = 3600
    for proc in psutil.process_iter(attrs=['pid', 'create_time', 'cmdline']):
        try:
            running_time = time.time() - proc.info['create_time']
            if running_time > one_hour and "python" in (proc.info["cmdline"] or []):
                log(f"Killing stale Python process PID {proc.info['pid']} running for {running_time:.0f}s")
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

# Main monitoring loop
def main():
    log("system.agent started.")
    while True:
        monitor_cpu()
        monitor_memory_and_disk()
        monitor_network()
        monitor_temperatures()
        self_healing()
        update_man_db_if_permitted()
        time.sleep(config["monitor_interval"])

if __name__ == "__main__":
    main()
