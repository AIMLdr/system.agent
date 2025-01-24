#!/usr/bin/env python3
import os
import time
import psutil
import json
import logging
import subprocess
import traceback
import threading
import socket
import shutil

class CognitiveMonitor:
    def __init__(self, config_path: str):
        self.config = self.load_config(config_path)
        self.logger = self.configure_logging()
        self.last_audit = time.time()
        self.health_issues = {}
        
    def load_config(self, path: str) -> dict:
        with open(path) as f:
            return json.load(f)
            
    def configure_logging(self) -> logging.Logger:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('/var/log/aion/system_audit.log'),
                logging.StreamHandler()
            ]
        )
        return logging.getLogger('SystemAgent')
    
    def get_system_state(self) -> dict:
        return {
            "cpu": {
                "percent": psutil.cpu_percent(interval=1),
                "cores": psutil.cpu_count(),
                "load_avg": os.getloadavg()
            },
            "memory": {
                "total": psutil.virtual_memory().total,
                "available": psutil.virtual_memory().available,
                "percent": psutil.virtual_memory().percent
            },
            "disk": {
                "total": shutil.disk_usage('/').total,
                "free": shutil.disk_usage('/').free,
                "percent": shutil.disk_usage('/').percent
            },
            "network": self.get_network_state(),
            "processes": {
                "total": len(psutil.pids()),
                "zombie": len([p for p in psutil.process_iter() if p.status() == psutil.STATUS_ZOMBIE])
            }
        }
    
    def get_network_state(self) -> dict:
        try:
            # Get network interfaces and their stats
            net_io = psutil.net_io_counters()
            return {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv
            }
        except Exception as e:
            self.logger.error(f"Network state collection failed: {e}")
            return {}
    
    def diagnose_system(self, state: dict):
        """
        Advanced system diagnosis with multi-level analysis
        """
        diagnostics = {
            "cpu_health": self.diagnose_cpu(state['cpu']),
            "memory_health": self.diagnose_memory(state['memory']),
            "disk_health": self.diagnose_disk(state['disk']),
            "process_health": self.diagnose_processes(state['processes']),
            "network_health": self.diagnose_network(state['network'])
        }
        
        return diagnostics
    
    def diagnose_cpu(self, cpu_state: dict) -> dict:
        """Detailed CPU diagnostic"""
        health = {
            "status": "NOMINAL",
            "issues": []
        }
        
        # High CPU usage
        if cpu_state['percent'] > self.config.get('cpu_threshold', 85):
            health['status'] = "CRITICAL"
            health['issues'].append({
                "type": "HIGH_CPU_USAGE",
                "value": cpu_state['percent'],
                "description": "CPU usage exceeds threshold"
            })
        
        # Load average analysis
        if cpu_state['load_avg'][0] > cpu_state['cores'] * 1.5:
            health['status'] = "WARNING"
            health['issues'].append({
                "type": "HIGH_LOAD_AVERAGE",
                "value": cpu_state['load_avg'][0],
                "description": "System load is significantly higher than core count"
            })
        
        return health
    
    def diagnose_memory(self, memory_state: dict) -> dict:
        """Detailed memory diagnostic"""
        health = {
            "status": "NOMINAL",
            "issues": []
        }
        
        # Memory pressure
        if memory_state['percent'] > self.config.get('memory_threshold', 90):
            health['status'] = "CRITICAL"
            health['issues'].append({
                "type": "HIGH_MEMORY_USAGE",
                "value": memory_state['percent'],
                "description": "Memory usage exceeds safe threshold"
            })
        
        return health
    
    def diagnose_disk(self, disk_state: dict) -> dict:
        """Detailed disk diagnostic"""
        health = {
            "status": "NOMINAL",
            "issues": []
        }
        
        # Disk space
        if disk_state['percent'] > self.config.get('disk_threshold', 90):
            health['status'] = "CRITICAL"
            health['issues'].append({
                "type": "LOW_DISK_SPACE",
                "value": disk_state['percent'],
                "description": "Disk space is critically low"
            })
        
        return health
    
    def diagnose_processes(self, process_state: dict) -> dict:
        """Process health diagnostic"""
        health = {
            "status": "NOMINAL",
            "issues": []
        }
        
        # Zombie process check
        if process_state['zombie'] > 10:
            health['status'] = "WARNING"
            health['issues'].append({
                "type": "ZOMBIE_PROCESSES",
                "value": process_state['zombie'],
                "description": "Excessive zombie processes detected"
            })
        
        return health
    
    def diagnose_network(self, network_state: dict) -> dict:
        """Network health diagnostic"""
        health = {
            "status": "NOMINAL",
            "issues": []
        }
        
        # Basic network connectivity test
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3)
        except (socket.error, socket.timeout):
            health['status'] = "CRITICAL"
            health['issues'].append({
                "type": "NETWORK_CONNECTIVITY",
                "description": "Unable to establish network connection"
            })
        
        return health
    
    def self_healing(self, diagnostics: dict):
        """
        Autonomous self-healing mechanism
        """
        healing_actions = []
        
        # CPU High Usage Mitigation
        if diagnostics['cpu_health']['status'] in ["WARNING", "CRITICAL"]:
            healing_actions.append(self.mitigate_cpu_pressure())
        
        # Memory Pressure Mitigation
        if diagnostics['memory_health']['status'] in ["WARNING", "CRITICAL"]:
            healing_actions.append(self.free_memory())
        
        # Zombie Process Cleanup
        if diagnostics['process_health']['status'] in ["WARNING", "CRITICAL"]:
            healing_actions.append(self.cleanup_zombie_processes())
        
        # Disk Space Management
        if diagnostics['disk_health']['status'] in ["WARNING", "CRITICAL"]:
            healing_actions.append(self.manage_disk_space())
        
        # Network Restoration
        if diagnostics['network_health']['status'] in ["WARNING", "CRITICAL"]:
            healing_actions.append(self.restore_network_connectivity())
        
        return healing_actions
    
    def mitigate_cpu_pressure(self):
        """Reduce CPU pressure by killing high-consumption processes"""
        try:
            # Find top CPU consuming processes
            processes = sorted(
                psutil.process_iter(['pid', 'name', 'cpu_percent']), 
                key=lambda x: x.info['cpu_percent'], 
                reverse=True
            )
            
            # Kill top 3 CPU consumers (excluding critical system processes)
            killed = 0
            for proc in processes[:3]:
                if proc.info['name'] not in ['systemd', 'sshd', 'login', 'agetty']:
                    try:
                        os.kill(proc.info['pid'], signal.SIGTERM)
                        killed += 1
                    except Exception as e:
                        self.logger.error(f"Failed to kill process {proc.info['pid']}: {e}")
            
            return {
                "action": "CPU_PRESSURE_MITIGATION",
                "processes_killed": killed
            }
        except Exception as e:
            self.logger.error(f"CPU pressure mitigation failed: {e}")
            return None
    
    def free_memory(self):
        """Attempt to free memory"""
        try:
            # Trigger system memory cleanup
            subprocess.run(['sync'], check=True)
            subprocess.run(['echo', '3', '>', '/proc/sys/vm/drop_caches'], shell=True, check=True)
            
            return {
                "action": "MEMORY_CLEANUP",
                "status": "SUCCESS"
            }
        except Exception as e:
            self.logger.error(f"Memory cleanup failed: {e}")
            return None
    
    def cleanup_zombie_processes(self):
        """Clean up zombie processes"""
        try:
            zombie_processes = [
                p for p in psutil.process_iter() if p.status() == psutil.STATUS_ZOMBIE
            ]
            
            for proc in zombie_processes:
                try:
                    proc.terminate()
                except Exception:
                    pass
            
            return {
                "action": "ZOMBIE_PROCESS_CLEANUP",
                "zombies_terminated": len(zombie_processes)
            }
        except Exception as e:
            self.logger.error(f"Zombie process cleanup failed: {e}")
            return None
    
    def manage_disk_space(self):
        """Manage disk space by removing old logs and temporary files"""
        try:
            # Remove old log files
            subprocess.run(['find', '/var/log', '-type', 'f', '-mtime', '+30', '-delete'], check=True)
            
            # Clean temporary directories
            subprocess.run(['find', '/tmp', '-type', 'f', '-atime', '+7', '-delete'], check=True)
            
            return {
                "action": "DISK_SPACE_MANAGEMENT",
                "status": "SUCCESS"
            }
        except Exception as e:
            self.logger.error(f"Disk space management failed: {e}")
            return None
    
    def restore_network_connectivity(self):
        """Attempt to restore network connectivity"""
        try:
            # Restart networking service
            subprocess.run(['systemctl', 'restart', 'networking'], check=True)
            
            return {
                "action": "NETWORK_RESTORATION",
                "status": "SUCCESS"
            }
        except Exception as e:
            self.logger.error(f"Network restoration failed: {e}")
            return None
    
    def perform_audit(self):
        """Comprehensive system audit and self-healing"""
        try:
            # Collect system state
            state = self.get_system_state()
            
            # Diagnose system
            diagnostics = self.diagnose_system(state)
            
            # Log diagnostics
            self.logger.info(f"System Diagnostics: {json.dumps(diagnostics, indent=2)}")
            
            # Trigger self-healing if issues detected
            if any(diag['status'] != "NOMINAL" for diag in diagnostics.values()):
                healing_actions = self.self_healing(diagnostics)
                
                # Log healing actions
                if healing_actions:
                    self.logger.warning(f"Self-Healing Actions: {json.dumps(healing_actions, indent=2)}")
            
        except Exception as e:
            self.logger.error(f"Audit process failed: {e}")
            self.logger.error(traceback.format_exc())
    
    def run(self):
        """Main monitoring loop"""
        self.logger.info("Starting cognitive monitoring")
        while True:
            try:
                self.perform_audit()
                
                # Sleep interval between audits
                time.sleep(self.config.get('monitor_interval', 60))
                
            except Exception as e:
                self.logger.error(f"Monitoring loop error: {e}")
                time.sleep(30)  # Backoff on continuous errors

if __name__ == "__main__":
    monitor = CognitiveMonitor('/opt/aion/system_agent/config.json')
    monitor.run()
