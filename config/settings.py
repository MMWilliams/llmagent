import os
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union, Literal

class ModelSettings(BaseModel):
    model_id: str = "TheBloke/Mistral-7B-Instruct-v0.2-GGUF"
    model_file: str = "mistral-7b-instruct-v0.2.Q4_K_M.gguf"
    context_length: int = 8192
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 2048
    repetition_penalty: float = 1.1
    stop_tokens: List[str] = ["<|im_end|>", "<|endoftext|>"]

class FileSystemSettings(BaseModel):
    workspace_path: str = Field(default_factory=lambda: os.path.join(os.getcwd(), "workspace"))
    allowed_extensions: List[str] = [".py", ".txt", ".md", ".json", ".yaml", ".yml", ".html", ".css", ".js", ".jsx", ".ts", ".tsx"]
    max_file_size_mb: int = 10
    backup_enabled: bool = True
    backup_path: Optional[str] = None

class ExecutorSettings(BaseModel):
    timeout_seconds: int = 30
    max_output_size_kb: int = 1024
    sandbox_enabled: bool = True
    environment_vars: Dict[str, str] = {}
    allowed_modules: List[str] = ["os", "sys", "pathlib", "json", "yaml", "re", "datetime", "collections", "math", "random", "time"]

class AgentSettings(BaseModel):
    mode: Literal["approval", "autonomous"] = "approval"
    max_iterations: int = 100
    think_aloud: bool = True
    max_thinking_tokens: int = 2000
    memory_enabled: bool = True
    memory_limit_mb: int = 100

class MonitoringSettings(BaseModel):
    status_interval_seconds: int = 60
    log_level: str = "INFO"
    telemetry_enabled: bool = True
    metrics_path: Optional[str] = None

class Settings(BaseModel):
    model: ModelSettings = ModelSettings()
    filesystem: FileSystemSettings = FileSystemSettings()
    executor: ExecutorSettings = ExecutorSettings()
    agent: AgentSettings = AgentSettings()
    monitoring: MonitoringSettings = MonitoringSettings()
    
    @classmethod
    def load_from_file(cls, filepath: str) -> 'Settings':
        """Load settings from a YAML or JSON file"""
        import json
        import yaml
        
        with open(filepath, 'r') as f:
            if filepath.endswith('.json'):
                data = json.load(f)
            elif filepath.endswith(('.yaml', '.yml')):
                data = yaml.safe_load(f)
            else:
                raise ValueError(f"Unsupported file format: {filepath}")
        
        return cls(**data)

# Default settings instance
settings = Settings()
