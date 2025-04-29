import os
import sys
import subprocess
import tempfile
import logging
import time
import json
import io
import traceback
from typing import Dict, List, Any, Optional, Tuple, Union
from pathlib import Path
import threading
import signal
from ..config.settings import settings

logger = logging.getLogger(__name__)

class CodeExecutionResult:
    """Stores the result of code execution"""
    
    def __init__(self, 
                 success: bool = False, 
                 output: str = "", 
                 error: str = "", 
                 return_value: Any = None,
                 execution_time: float = 0.0):
        self.success = success
        self.output = output
        self.error = error
        self.return_value = return_value
        self.execution_time = execution_time
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert the result to a dictionary"""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "return_value": self.return_value,
            "execution_time": self.execution_time
        }
        
    def __str__(self) -> str:
        """String representation of the result"""
        if self.success:
            result = f"✓ Execution succeeded in {self.execution_time:.2f}s\n"
            if self.output:
                result += f"Output:\n{self.output}\n"
            if self.return_value is not None:
                result += f"Return value: {self.return_value}\n"
        else:
            result = f"✗ Execution failed in {self.execution_time:.2f}s\n"
            if self.error:
                result += f"Error:\n{self.error}\n"
            if self.output:
                result += f"Output (before error):\n{self.output}\n"
                
        return result


class CodeExecutor:
    """Executes code safely within the workspace"""
    
    def __init__(self, workspace_path: Optional[str] = None):
        self.workspace_path = workspace_path or settings.filesystem.workspace_path
        self.timeout_seconds = settings.executor.timeout_seconds
        self.max_output_size = settings.executor.max_output_size_kb * 1024
        self.sandbox_enabled = settings.executor.sandbox_enabled
        self.environment_vars = settings.executor.environment_vars.copy()
        self.allowed_modules = set(settings.executor.allowed_modules)
        
    def execute_code(self, code: str, mode: str = "exec") -> CodeExecutionResult:
        """Execute Python code string in a safe environment"""
        if self.sandbox_enabled:
            return self._execute_sandboxed(code, mode)
        else:
            return self._execute_direct(code, mode)
    
    def _execute_direct(self, code: str, mode: str = "exec") -> CodeExecutionResult:
        """Execute code directly in the current process (unsafe)"""
        start_time = time.time()
        output_buffer = io.StringIO()
        error_buffer = io.StringIO()
        return_value = None
        success = False
        
        # Save original stdout and stderr
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        
        try:
            # Redirect stdout and stderr
            sys.stdout = output_buffer
            sys.stderr = error_buffer
            
            # Execute code
            if mode == "eval":
                return_value = eval(code, {"__builtins__": __builtins__}, {})
            else:
                exec(code, {"__builtins__": __builtins__}, {})
                
            success = True
            
        except Exception as e:
            error_buffer.write(f"{type(e).__name__}: {str(e)}\n")
            error_buffer.write(traceback.format_exc())
            
        finally:
            # Restore stdout and stderr
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            
            # Get execution time
            execution_time = time.time() - start_time
            
            # Get output and error messages
            output = output_buffer.getvalue()
            error = error_buffer.getvalue()
            
            # Truncate if too large
            if len(output) > self.max_output_size:
                output = output[:self.max_output_size] + "\n... [output truncated]"
            if len(error) > self.max_output_size:
                error = error[:self.max_output_size] + "\n... [error truncated]"
            
        return CodeExecutionResult(
            success=success,
            output=output,
            error=error,
            return_value=return_value,
            execution_time=execution_time
        )
    
    def _execute_sandboxed(self, code: str, mode: str = "exec") -> CodeExecutionResult:
        """Execute code in a separate process (safer)"""
        start_time = time.time()
        
        # Create a temporary file
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as temp_file:
            temp_path = temp_file.name
            
            # Prepare the code
            if mode == "eval":
                wrapped_code = f"""
import sys
import json
import traceback

try:
    result = eval({repr(code)})
    print("RESULT_VALUE: " + json.dumps(result, default=str))
    sys.exit(0)
except Exception as e:
    print("ERROR: " + str(e), file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
"""
            else:
                wrapped_code = f"""
import sys
import traceback

try:
    {code}
    sys.exit(0)
except Exception as e:
    print("ERROR: " + str(e), file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
"""
            
            # Write code to temp file
            temp_file.write(wrapped_code.encode('utf-8'))
            
        try:
            # Set environment variables
            env = os.environ.copy()
            env.update(self.environment_vars)
            
            # Add workspace to Python path
            python_path = env.get('PYTHONPATH', '')
            if python_path:
                env['PYTHONPATH'] = f"{self.workspace_path}:{python_path}"
            else:
                env['PYTHONPATH'] = self.workspace_path
                
            # Run in subprocess
            process = subprocess.Popen(
                [sys.executable, temp_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.workspace_path,
                env=env,
                text=True
            )
            
            # Set timeout using a thread
            timer = threading.Timer(self.timeout_seconds, lambda: process.kill())
            timer.start()
            
            try:
                stdout, stderr = process.communicate()
                exit_code = process.returncode
            finally:
                timer.cancel()
                
            # Process was killed due to timeout
            if exit_code == -9:
                return CodeExecutionResult(
                    success=False,
                    output=stdout[:self.max_output_size] if stdout else "",
                    error=f"Execution timed out after {self.timeout_seconds} seconds",
                    execution_time=self.timeout_seconds
                )
                
            # Extract return value if in eval mode
            return_value = None
            if mode == "eval" and stdout:
                for line in stdout.splitlines():
                    if line.startswith("RESULT_VALUE: "):
                        try:
                            return_value = json.loads(line[len("RESULT_VALUE: "):])
                        except:
                            pass
                
            # Create result
            success = exit_code == 0
            execution_time = time.time() - start_time
                
            return CodeExecutionResult(
                success=success,
                output=stdout[:self.max_output_size] if stdout else "",
                error=stderr[:self.max_output_size] if stderr else "",
                return_value=return_value,
                execution_time=execution_time
            )
                
        except Exception as e:
            execution_time = time.time() - start_time
            return CodeExecutionResult(
                success=False,
                output="",
                error=f"Execution failed: {str(e)}\n{traceback.format_exc()}",
                execution_time=execution_time
            )
        finally:
            # Remove temporary file
            try:
                os.unlink(temp_path)
            except:
                pass
    
    def run_test(self, test_path: str) -> CodeExecutionResult:
        """Run pytest on a specific test file or directory"""
        import pytest
        
        start_time = time.time()
        output_buffer = io.StringIO()
        
        try:
            exit_code = pytest.main([
                "-v",
                os.path.join(self.workspace_path, test_path)
            ], plugins=[PytestCapture(output_buffer)])
            
            success = exit_code == 0
            output = output_buffer.getvalue()
            
            if len(output) > self.max_output_size:
                output = output[:self.max_output_size] + "\n... [output truncated]"
                
            return CodeExecutionResult(
                success=success,
                output=output,
                error="" if success else "Tests failed",
                execution_time=time.time() - start_time
            )
            
        except Exception as e:
            return CodeExecutionResult(
                success=False,
                output="",
                error=f"Failed to run tests: {str(e)}\n{traceback.format_exc()}",
                execution_time=time.time() - start_time
            )
    
    def run_command(self, command: str) -> CodeExecutionResult:
        """Run a shell command in the workspace directory"""
        start_time = time.time()
        
        try:
            # Set environment variables
            env = os.environ.copy()
            env.update(self.environment_vars)
            
            # Run command
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.workspace_path,
                env=env,
                text=True
            )
            
            # Set timeout using a thread
            timer = threading.Timer(self.timeout_seconds, lambda: process.kill())
            timer.start()
            
            try:
                stdout, stderr = process.communicate()
                exit_code = process.returncode
            finally:
                timer.cancel()
                
            # Process was killed due to timeout
            if exit_code == -9:
                return CodeExecutionResult(
                    success=False,
                    output=stdout[:self.max_output_size] if stdout else "",
                    error=f"Command execution timed out after {self.timeout_seconds} seconds",
                    execution_time=self.timeout_seconds
                )
            
            # Truncate output if too large
            if len(stdout) > self.max_output_size:
                stdout = stdout[:self.max_output_size] + "\n... [output truncated]"
            if len(stderr) > self.max_output_size:
                stderr = stderr[:self.max_output_size] + "\n... [error truncated]"
                
            return CodeExecutionResult(
                success=exit_code == 0,
                output=stdout,
                error=stderr,
                execution_time=time.time() - start_time
            )
            
        except Exception as e:
            return CodeExecutionResult(
                success=False,
                output="",
                error=f"Command execution failed: {str(e)}\n{traceback.format_exc()}",
                execution_time=time.time() - start_time
            )
            
    def read_logs(self, log_path: str, num_lines: int = 100) -> str:
        """Read the last N lines from a log file"""
        full_path = os.path.join(self.workspace_path, log_path)
        
        if not os.path.exists(full_path):
            return f"Error: Log file '{log_path}' does not exist"
            
        try:
            # Read last N lines
            with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
                return ''.join(lines[-num_lines:]) if lines else ""
        except Exception as e:
            return f"Error reading log file: {str(e)}"


class PytestCapture:
    """Pytest plugin to capture test output"""
    
    def __init__(self, buffer):
        self.buffer = buffer
        
    def pytest_runtest_logreport(self, report):
        """Called for test setup/call/teardown report"""
        if report.when == 'call':
            if hasattr(report, 'capstdout'):
                self.buffer.write(report.capstdout)
            if hasattr(report, 'capstderr'):
                self.buffer.write(report.capstderr)
