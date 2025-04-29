import os
import logging
import json
import time
import re
from typing import List, Dict, Any, Optional, Union, Tuple, Callable
from datetime import datetime
from .models import get_model, ModelBase
from .file_manager import FileManager
from .executor import CodeExecutor, CodeExecutionResult
from .prompt_manager import get_system_prompt, format_user_prompt
from ..config.settings import settings
from ..monitoring.status_reporter import StatusReporter

logger = logging.getLogger(__name__)

class Agent:
    """LLM-powered development agent"""
    
    def __init__(self, 
                 workspace_path: Optional[str] = None,
                 model_type: str = "llamacpp",
                 model_kwargs: Optional[Dict[str, Any]] = None):
        
        self.workspace_path = workspace_path or settings.filesystem.workspace_path
        self.model_kwargs = model_kwargs or {}
        
        # Initialize components
        self.model = get_model(model_type, **self.model_kwargs)
        self.file_manager = FileManager(self.workspace_path)
        self.executor = CodeExecutor(self.workspace_path)
        self.status_reporter = StatusReporter()
        
        # Agent state
        self.mode = settings.agent.mode
        self.max_iterations = settings.agent.max_iterations
        self.iteration = 0
        self.memory = [] if settings.agent.memory_enabled else None
        self.context_docs = []
        self.conversation_history = []
        self.last_action_time = time.time()
        self.is_active = False
        
    def set_context_docs(self, docs: List[Dict[str, str]]) -> None:
        """Set documents to be used as context for the agent"""
        self.context_docs = docs
        
    def add_context_doc(self, doc_name: str, doc_content: str) -> None:
        """Add a document to the agent's context"""
        self.context_docs.append({
            'name': doc_name,
            'content': doc_content
        })
        
    def clear_context_docs(self) -> None:
        """Clear all context documents"""
        self.context_docs = []
        
    def run(self, 
            initial_prompt: str, 
            max_iterations: Optional[int] = None,
            on_action: Optional[Callable[[Dict[str, Any]], bool]] = None,
            on_iteration_complete: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
        """
        Run the agent with the given prompt
        
        Args:
            initial_prompt: The initial prompt from the user
            max_iterations: Maximum number of iterations to run (overrides settings)
            on_action: Callback function that receives proposed action and returns bool (approve/reject)
            on_iteration_complete: Callback function called after each iteration
            
        Returns:
            Dict containing summary of the agent's work
        """
        if max_iterations is not None:
            self.max_iterations = max_iterations
            
        self.iteration = 0
        self.is_active = True
        self.status_reporter.start_task("Agent execution", self.max_iterations)
        
        # Initialize conversation with system prompt
        system_prompt = get_system_prompt(self.context_docs)
        self.conversation_history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": initial_prompt}
        ]
        
        try:
            while self.iteration < self.max_iterations and self.is_active:
                self.iteration += 1
                self.status_reporter.update_status(f"Iteration {self.iteration}/{self.max_iterations}")
                
                # Generate agent response
                agent_response = self._get_agent_response()
                
                # Extract actions from the response
                actions = self._parse_actions(agent_response)
                
                if not actions:
                    # No actions found, just treat as thinking
                    logger.info(f"No actions found in agent response, treating as thinking")
                    self.conversation_history.append({"role": "assistant", "content": agent_response})
                    
                    if on_iteration_complete:
                        on_iteration_complete({
                            "iteration": self.iteration,
                            "actions": [],
                            "thinking": agent_response
                        })
                    
                    continue
                
                # Process each action
                all_results = []
                for action in actions:
                    action_type = action.get("type", "")
                    action_params = action.get("params", {})
                    
                    # Check if action should be approved
                    if self.mode == "approval" and on_action:
                        approved = on_action(action)
                        if not approved:
                            result = {"status": "rejected", "message": "Action rejected by user"}
                            all_results.append({"action": action, "result": result})
                            continue
                    
                    # Execute the action
                    result = self._execute_action(action_type, action_params)
                    all_results.append({"action": action, "result": result})
                    
                # Format action results for LLM
                results_str = json.dumps(all_results, indent=2)
                self.conversation_history.append({"role": "assistant", "content": agent_response})
                self.conversation_history.append({
                    "role": "user", 
                    "content": f"Action results:\n```json\n{results_str}\n```\n\nContinue based on these results."
                })
                
                # Update status and call iteration callback
                self.status_reporter.increment_progress()
                self.last_action_time = time.time()
                
                if on_iteration_complete:
                    on_iteration_complete({
                        "iteration": self.iteration,
                        "actions": all_results,
                        "thinking": agent_response
                    })
                    
                # Check if we're done (either reached max iterations or all tasks complete)
                if self._check_if_done(agent_response):
                    logger.info("Agent completed all tasks")
                    break
                    
        except Exception as e:
            logger.error(f"Error in agent execution: {e}")
            self.status_reporter.fail_task(str(e))
            raise
        finally:
            self.is_active = False
            self.status_reporter.complete_task()
            
        # Generate final summary
        return self._generate_summary()
        
    def stop(self) -> None:
        """Stop the agent execution"""
        self.is_active = False
        logger.info("Agent execution stopped")
        
    def _get_agent_response(self) -> str:
        """Get the next response from the LLM agent"""
        # Combine context and conversation history
        prompt = self.conversation_history
        
        # Generate response
        response = self.model.generate(
            prompt=format_user_prompt(prompt),
            temperature=settings.model.temperature,
            max_tokens=settings.model.max_tokens
        )
        
        return response
        
    def _parse_actions(self, text: str) -> List[Dict[str, Any]]:
        """Parse actions from the agent's response"""
        actions = []
        
        # Match code blocks with language and content
        pattern = r"```(?:(\w+))?\s*\n(.*?)```"
        matches = re.finditer(pattern, text, re.DOTALL)
        
        for match in matches:
            language = match.group(1) or ""
            content = match.group(2).strip()
            
            # Check for action blocks
            if language.lower() == "json" and content.startswith("{") and "type" in content:
                try:
                    action = json.loads(content)
                    if isinstance(action, dict) and "type" in action:
                        actions.append(action)
                except:
                    pass
                    
            # Check for multiple actions in a JSON array
            elif language.lower() == "json" and content.startswith("["):
                try:
                    action_list = json.loads(content)
                    if isinstance(action_list, list):
                        for item in action_list:
                            if isinstance(item, dict) and "type" in item:
                                actions.append(item)
                except:
                    pass
        
        # If no JSON actions found, look for command patterns
        if not actions:
            # Look for command patterns like READ_FILE, WRITE_FILE, etc.
            cmd_patterns = {
                r"READ_FILE\s*\(\s*['\"]([^'\"]+)['\"]\s*\)": 
                    lambda m: {"type": "read_file", "params": {"filepath": m.group(1)}},
                    
                r"WRITE_FILE\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*(['\"])(((?!\2).)*)\2\s*\)":
                    lambda m: {"type": "write_file", "params": {"filepath": m.group(1), "content": m.group(3)}},
                    
                r"RUN_CODE\s*\(\s*(['\"])(((?!\1).)*)\1\s*\)":
                    lambda m: {"type": "run_code", "params": {"code": m.group(2)}},
                    
                r"LIST_FILES\s*\(\s*(?:['\"]([^'\"]+)['\"]\s*)?\)":
                    lambda m: {"type": "list_files", "params": {"path": m.group(1) or ""}},
                    
                r"CREATE_DIR\s*\(\s*['\"]([^'\"]+)['\"]\s*\)":
                    lambda m: {"type": "create_directory", "params": {"path": m.group(1)}}
            }
            
            for pattern, action_fn in cmd_patterns.items():
                for match in re.finditer(pattern, text, re.DOTALL):
                    try:
                        action = action_fn(match)
                        actions.append(action)
                    except:
                        pass
        
        return actions
        
    def _execute_action(self, action_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single action and return the result"""
        try:
            if action_type == "read_file":
                filepath = params.get("filepath", "")
                content = self.file_manager.read_file(filepath)
                return {
                    "status": "success",
                    "content": content
                }
                
            elif action_type == "write_file":
                filepath = params.get("filepath", "")
                content = params.get("content", "")
                success = self.file_manager.write_file(filepath, content)
                return {
                    "status": "success" if success else "error",
                    "message": f"File {'written' if success else 'write failed'}: {filepath}"
                }
                
            elif action_type == "list_files":
                path = params.get("path", "")
                files = self.file_manager.list_files(path)
                return {
                    "status": "success",
                    "files": files
                }
                
            elif action_type == "create_directory":
                path = params.get("path", "")
                success = self.file_manager.create_directory(path)
                return {
                    "status": "success" if success else "error",
                    "message": f"Directory {'created' if success else 'creation failed'}: {path}"
                }
                
            elif action_type == "delete_file":
                filepath = params.get("filepath", "")
                success = self.file_manager.delete_file(filepath)
                return {
                    "status": "success" if success else "error",
                    "message": f"File {'deleted' if success else 'deletion failed'}: {filepath}"
                }
                
            elif action_type == "run_code":
                code = params.get("code", "")
                mode = params.get("mode", "exec")
                result = self.executor.execute_code(code, mode)
                return {
                    "status": "success" if result.success else "error",
                    "output": result.output,
                    "error": result.error,
                    "return_value": result.return_value,
                    "execution_time": result.execution_time
                }
                
            elif action_type == "run_command":
                command = params.get("command", "")
                result = self.executor.run_command(command)
                return {
                    "status": "success" if result.success else "error",
                    "output": result.output,
                    "error": result.error,
                    "execution_time": result.execution_time
                }
                
            elif action_type == "run_test":
                test_path = params.get("test_path", "")
                result = self.executor.run_test(test_path)
                return {
                    "status": "success" if result.success else "error",
                    "output": result.output,
                    "error": result.error,
                    "execution_time": result.execution_time
                }
                
            elif action_type == "read_logs":
                log_path = params.get("log_path", "")
                num_lines = params.get("num_lines", 100)
                content = self.executor.read_logs(log_path, num_lines)
                return {
                    "status": "success",
                    "content": content
                }
                
            else:
                return {
                    "status": "error",
                    "message": f"Unknown action type: {action_type}"
                }
                
        except Exception as e:
            logger.error(f"Error executing action {action_type}: {e}")
            return {
                "status": "error",
                "message": f"Error executing action: {str(e)}"
            }
    
    def _check_if_done(self, response: str) -> bool:
        """Check if the agent has completed all tasks"""
        lower_response = response.lower()
        
        done_phrases = [
            "all tasks complete",
            "tasks completed",
            "implementation complete",
            "finished all tasks",
            "project complete",
            "completed all requested tasks",
            "implementation is now complete",
            "work is complete"
        ]
        
        for phrase in done_phrases:
            if phrase in lower_response:
                return True
                
        return False
        
    def _generate_summary(self) -> Dict[str, Any]:
        """Generate a summary of the agent's work"""
        files = self.file_manager.list_files()
        
        # Get file counts by type
        file_types = {}
        for file in files:
            if not file['is_dir']:
                ext = file.get('extension', '')
                file_types[ext] = file_types.get(ext, 0) + 1
                
        # Format summary
        return {
            "iterations": self.iteration,
            "total_files": len([f for f in files if not f['is_dir']]),
            "file_types": file_types,
            "elapsed_time": time.time() - self.last_action_time,
            "timestamp": datetime.now().isoformat(),
            "workspace": self.workspace_path,
            "files": files
        }
