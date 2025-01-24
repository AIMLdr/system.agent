# system_agent.py
import os
import sys
import json
import logging
import threading
import ollama

class AISystemAgent:
    def __init__(self, config_path='/opt/aion/system_agent/config.json'):
        self.config = self.load_config(config_path)
        self.logger = self.setup_logging()
        self.ollama_client = self.initialize_ollama_client()
        
    def load_config(self, config_path):
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                'model': 'llama2',
                'log_level': 'INFO',
                'monitoring_interval': 60
            }
    
    def setup_logging(self):
        logging.basicConfig(
            level=getattr(logging, self.config.get('log_level', 'INFO')),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('/var/log/aion/system_agent.log'),
                logging.StreamHandler()
            ]
        )
        return logging.getLogger('AISystemAgent')
    
    def initialize_ollama_client(self):
        try:
            client = ollama.Client(host='http://localhost:11434')
            # Verify model availability
            models = client.list()
            if not any(model['name'] == self.config.get('model', 'llama2') for model in models['models']):
                self.logger.warning(f"Model not found. Pulling {self.config.get('model', 'llama2')}")
                client.pull(self.config.get('model', 'llama2'))
            return client
        except Exception as e:
            self.logger.error(f"Ollama client initialization failed: {e}")
            return None

    def generate_system_prompt(self, system_data):
        """Generate a system analysis prompt for the AI"""
        return f"""
        Analyze the following system data and provide insights:
        
        {json.dumps(system_data, indent=2)}
        
        Provide:
        1. Potential system issues
        2. Recommended actions
        3. Severity assessment
        """

    def ai_system_analysis(self, system_data):
        """Perform AI-powered system analysis"""
        if not self.ollama_client:
            self.logger.error("Ollama client not initialized")
            return None
        
        try:
            response = self.ollama_client.chat(
                model=self.config.get('model', 'llama2'),
                messages=[{
                    'role': 'user', 
                    'content': self.generate_system_prompt(system_data)
                }]
            )
            return response['message']['content']
        except Exception as e:
            self.logger.error(f"AI analysis failed: {e}")
            return None

    def run(self):
        """Main monitoring loop"""
        self.logger.info("AION System Agent started")
        
        while True:
            try:
                # Collect system data (implement your system data collection)
                system_data = self.collect_system_data()
                
                # Perform AI analysis
                ai_insights = self.ai_system_analysis(system_data)
                
                if ai_insights:
                    self.logger.info(f"AI System Insights: {ai_insights}")
                
                # Sleep for configured interval
                time.sleep(self.config.get('monitoring_interval', 60))
            
            except Exception as e:
                self.logger.error(f"Monitoring loop error: {e}")
                time.sleep(30)  # Backoff on continuous errors

    def collect_system_data(self):
        """Collect comprehensive system data"""
        # Implement system data collection logic
        return {
            'cpu_usage': psutil.cpu_percent(),
            'memory_usage': psutil.virtual_memory().percent,
            'disk_usage': psutil.disk_usage('/').percent,
            # Add more system metrics
        }

if __name__ == "__main__":
    agent = AISystemAgent()
    agent.run()
