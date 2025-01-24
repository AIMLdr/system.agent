#!/usr/bin/env python3
import os
import sys
import time
import json
import logging
import threading
import subprocess
import traceback
import signal
import psutil
import shutil
import socket
import requests

# Ollama Integration
import ollama

class AISystemAgent:
    def __init__(self, config_path: str):
        # Core Initialization
        self.config_path = config_path
        self.config = self.load_config()
        self.logger = self.configure_logging()
        
        # Ollama Integration
        self.ollama_client = None
        self.ai_model = self.config.get('ai_model', 'llama2')
        
        # State Tracking
        self.system_state = {}
        self.diagnostic_history = []
        self.healing_log = []
        
        # Concurrency Controls
        self.stop_event = threading.Event()
        
        # Initialize Components
        self.initialize_components()
    
    def initialize_components(self):
        """Initialize all system agent components"""
        try:
            self.initialize_ollama_client()
            self.validate_system_requirements()
        except Exception as e:
            self.logger.critical(f"Initialization failed: {e}")
            sys.exit(1)
    
    def load_config(self) -> dict:
        """Load configuration with robust error handling"""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            
            # Validate critical configuration
            required_keys = ['monitor_interval', 'ai_model']
            for key in required_keys:
                if key not in config:
                    raise KeyError(f"Missing required configuration key: {key}")
            
            return config
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Configuration load error: {e}")
            return {
                'monitor_interval': 60,
                'ai_model': 'llama2',
                'healing_enabled': True
            }
    
    def configure_logging(self) -> logging.Logger:
        """Advanced logging configuration"""
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        log_file = '/var/log/aion/system_agent.log'
        
        # Ensure log directory exists
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        
        logger = logging.getLogger('AISystemAgent')
        
        # Add log rotation (requires additional setup)
        try:
            import logging.handlers
            file_handler = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=10*1024*1024, backupCount=5
            )
            file_handler.setFormatter(logging.Formatter(log_format))
            logger.addHandler(file_handler)
        except ImportError:
            logger.warning("Log rotation not available")
        
        return logger
    
    def initialize_ollama_client(self):
        """Initialize Ollama client with robust error handling"""
        try:
            # Check if Ollama service is running
            subprocess.run(['systemctl', 'is-active', 'ollama'], 
                           check=True, 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL)
            
            # Initialize Ollama client
            self.ollama_client = ollama.Client(host='http://localhost:11434')
            
            # Validate model availability
            available_models = self.ollama_client.list()
            if not any(model['name'] == self.ai_model for model in available_models['models']):
                self.logger.warning(f"Model {self.ai_model} not found. Pulling model...")
                self.ollama_client.pull(self.ai_model)
            
            self.logger.info(f"Ollama client initialized with model: {self.ai_model}")
        
        except (subprocess.CalledProcessError, ConnectionError) as e:
            self.logger.error(f"Ollama initialization failed: {e}")
            self.ollama_client = None
    
    def validate_system_requirements(self):
        """Comprehensive system requirement validation"""
        checks = [
            self.check_python_version(),
            self.check_system_resources(),
            self.check_network_connectivity()
        ]
        
        if not all(checks):
            self.logger.critical("System does not meet minimum requirements")
            sys.exit(1)
    
    def check_python_version(self) -> bool:
        """Validate Python version"""
        min_version = (3, 8)
        current_version = sys.version_info
        
        if current_version < min_version:
            self.logger.error(f"Unsupported Python version: {current_version}")
            return False
        return True
    
    def check_system_resources(self) -> bool:
        """Check minimum system resources"""
        min_ram = 4 * 1024 * 1024 * 1024  # 4GB
        min_cpu_cores = 2
        
        ram = psutil.virtual_memory().total
        cpu_cores = psutil.cpu_count()
        
        if ram < min_ram:
            self.logger.warning(f"Low RAM: {ram/1024/1024/1024:.2f}GB")
        
        if cpu_cores < min_cpu_cores:
            self.logger.warning(f"Low CPU cores: {cpu_cores}")
        
        return ram >= min_ram and cpu_cores >= min_cpu_cores
    
    def check_network_connectivity(self) -> bool:
        """Advanced network connectivity check"""
        test_urls = [
            'https://8.8.8.8',
            'https://1.1.1.1',
            'https://9.9.9.9'
        ]
        
        for url in test_urls:
            try:
                requests.get(url, timeout=5)
                return True
            except requests.RequestException:
                continue
        
        self.logger.error("No network connectivity")
        return False
    
    def ai_diagnostic_analysis(self, system_state: dict):
        """Use AI to provide diagnostic insights"""
        if not self.ollama_client:
            return None
        
        try:
            prompt = f"""
            Analyze the following system state and provide diagnostic insights:
            {json.dumps(system_state, indent=2)}
            
            Provide:
            1. Potential issues
            2. Recommended actions
            3. Severity assessment
            """
            
            response = self.ollama_client.chat(
                model=self.ai_model,
                messages=[{'role': 'user', 'content': prompt}]
            )
            
            return response['message']['content']
        
        except Exception as e:
            self.logger.error(f"AI diagnostic analysis failed: {e}")
            return None
    
    def collect_system_state(self):
        """Comprehensive system state collection"""
        state = {
            'timestamp': time.time(),
            'cpu': {
                'usage': psutil.cpu_percent(interval=1),
                'cores': psutil.cpu_count(),
                'load_avg': os.getloadavg()
            },
            'memory': {
                'total': psutil.virtual_memory().total,
                'available': psutil.virtual_memory().available,
                'percent': psutil.virtual_memory().percent
            },
            'disk': {
                'total': shutil.disk_usage('/').total,
                'free': shutil.disk_usage('/').free,
                'percent': shutil.disk_usage('/').percent
            },
            'processes': {
                'total': len(psutil.pids()),
                'running': len([p for p in psutil.process_iter() if p.status() == psutil.STATUS_RUNNING])
            },
            'network': self.get_network_state()
        }
        
        return state
    
    def get_network_state(self):
        """Detailed network state collection"""
        try:
            net_io = psutil.net_io_counters()
            return {
                'bytes_sent': net_io.bytes_sent,
                'bytes_recv': net_io.bytes_recv,
                'packets_sent': net_io.packets_sent,
                'packets_recv': net_io.packets_recv
            }
        except Exception as e:
            self.logger.error(f"Network state collection failed: {e}")
            return {}
    
    def run_diagnostic_cycle(self):
        """Main diagnostic and healing cycle"""
        try:
            # Collect system state
            system_state = self.collect_system_state()
            
            # AI-Powered Diagnostic Analysis
            ai_insights = self.ai_diagnostic_analysis(system_state)
            
            if ai_insights:
                self.logger.info(f"AI Diagnostic Insights: {ai_insights}")
            
            # Store diagnostic history
            self.diagnostic_history.append({
                'timestamp': system_state['timestamp'],
                'state': system_state,
                'ai_insights': ai_insights
            })
            
            # Limit diagnostic history
            if len(self.diagnostic_history) > 100:
                self.diagnostic_history.pop(0)
        
        except Exception as e:
            self.logger.error(f"Diagnostic cycle failed: {e}")
            self.logger.error(traceback.format_exc())
    
    def run(self):
        """Main agent run loop"""
        self.logger.info("AI System Agent starting...")
        
        try:
            while not self.stop_event.is_set():
                self.run_diagnostic_cycle()
                
                # Sleep between cycles
                time.sleep(self.config.get('monitor_interval', 60))
        
        except KeyboardInterrupt:
            self.logger.info("Agent shutdown initiated")
        
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Graceful shutdown and cleanup"""
        self.logger.info("Performing cleanup...")
        self.stop_event.set()
    
    def signal_handler(self, signum, frame):
        """Handle system signals"""
        self.logger.info(f"Received signal {signum}")
        self.cleanup()
        sys.exit(0)

def main():
    # Configuration path
    config_path = '/opt/aion/system_agent/config.json'
    
    # Create default config if not exists
    if not os.path.exists(config_path):
        default_config = {
            'monitor_interval': 60,
            'ai_model': 'llama2',
            'healing_enabled': True
        }
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(default_config, f, indent=2)
    
    # Initialize and run agent
    agent = AISystemAgent(config_path)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, agent.signal_handler)
    signal.signal(signal.SIGTERM, agent.signal_handler)
    
    agent.run()

if __name__ == "__main__":
    main()
