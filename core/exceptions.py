class LLMAgentError(Exception):
    """Base exception class for LLMAgent"""
    pass

class ModelError(LLMAgentError):
    """Exception raised for errors in the model component"""
    pass

class FileOperationError(LLMAgentError):
    """Exception raised for errors in file operations"""
    pass

class ExecutionError(LLMAgentError):
    """Exception raised for errors in code execution"""
    pass

class AgentError(LLMAgentError):
    """Exception raised for errors in the agent's operation"""
    pass

class ConfigError(LLMAgentError):
    """Exception raised for configuration errors"""
    pass