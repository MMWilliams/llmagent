import os
import sys
import logging
import click
import json
import time
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.syntax import Syntax
from rich.table import Table
from rich.markdown import Markdown
from rich.prompt import Confirm
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Add parent directory to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent import Agent
from core.models import get_model
from core.file_manager import FileManager
from core.executor import CodeExecutor
from config.settings import Settings, settings
from monitoring.status_reporter import StatusReporter
from monitoring.telemetry import Telemetry

# Initialize rich console
console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("llmagent")

def setup_workspace(workspace_path: str) -> None:
    """Set up the workspace directory"""
    try:
        os.makedirs(workspace_path, exist_ok=True)
        console.print(f"[green]Workspace initialized at: {workspace_path}[/green]")
    except Exception as e:
        console.print(f"[red]Error creating workspace: {str(e)}[/red]")
        sys.exit(1)

def setup_logging(log_file: Optional[str] = None) -> None:
    """Set up logging to file"""
    if log_file:
        try:
            log_dir = os.path.dirname(log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
                
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
            
            root_logger = logging.getLogger()
            root_logger.addHandler(file_handler)
            
            console.print(f"[green]Logging to: {log_file}[/green]")
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to set up logging to file: {str(e)}[/yellow]")

def load_settings(config_file: Optional[str] = None) -> Settings:
    """Load settings from config file"""
    if not config_file:
        return settings
        
    try:
        console.print(f"Loading settings from: {config_file}")
        loaded_settings = Settings.load_from_file(config_file)
        return loaded_settings
    except Exception as e:
        console.print(f"[red]Error loading settings: {str(e)}[/red]")
        console.print("[yellow]Falling back to default settings[/yellow]")
        return settings

def print_action(action: Dict[str, Any]) -> None:
    """Print an action in a nice format"""
    action_type = action.get("type", "unknown")
    params = action.get("params", {})
    
    # Format parameters based on action type
    param_table = Table(show_header=False, box=None, padding=(0, 1))
    
    for key, value in params.items():
        if key == "content" and len(str(value)) > 100:
            # For file content, show a truncated version
            truncated = str(value)[:100] + "..."
            param_table.add_row(key, truncated)
        elif key == "code" and len(str(value)) > 100:
            # For code, show a truncated version
            truncated = str(value)[:100] + "..."
            param_table.add_row(key, truncated)
        else:
            param_table.add_row(key, str(value))
    
    console.print(f"[bold blue]Action:[/bold blue] {action_type}")
    console.print(param_table)

def print_result(result: Dict[str, Any]) -> None:
    """Print an action result in a nice format"""
    status = result.get("status", "unknown")
    color = "green" if status == "success" else "red"
    
    console.print(f"[bold {color}]Status:[/bold {color}] {status}")
    
    # Print output if present
    if "output" in result and result["output"]:
        output = result["output"]
        console.print("[bold]Output:[/bold]")
        
        # Try to detect if output is JSON
        if output.strip().startswith(("{", "[")):
            try:
                output_obj = json.loads(output)
                console.print(json.dumps(output_obj, indent=2))
            except:
                console.print(output)
        else:
            console.print(output)
    
    # Print error if present
    if "error" in result and result["error"]:
        console.print("[bold red]Error:[/bold red]")
        console.print(result["error"])
    
    # Print return value if present
    if "return_value" in result and result["return_value"] is not None:
        console.print("[bold]Return value:[/bold]", result["return_value"])
    
    # Print execution time if present
    if "execution_time" in result:
        console.print(f"[dim]Execution time: {result['execution_time']:.3f}s[/dim]")

def handle_actions(agent: Agent, on_action_callback) -> bool:
    """Handle agent actions with callback"""
    def on_action(action: Dict[str, Any]) -> bool:
        """Callback for agent actions"""
        print_action(action)
        
        # Special handling for file write operations
        if action.get("type") == "write_file":
            filepath = action.get("params", {}).get("filepath", "")
            content = action.get("params", {}).get("content", "")
            
            if content and len(content) > 100:
                # For longer content, show syntax highlighting
                syntax = Syntax(
                    content, 
                    lexer=get_lexer_for_file(filepath),
                    theme="monokai",
                    line_numbers=True,
                    word_wrap=True
                )
                console.print("[bold]File content:[/bold]")
                console.print(syntax)
        
        # Special handling for code execution
        elif action.get("type") == "run_code":
            code = action.get("params", {}).get("code", "")
            
            if code and len(code) > 100:
                # Show syntax highlighting for code
                syntax = Syntax(
                    code,
                    lexer="python",
                    theme="monokai",
                    line_numbers=True,
                    word_wrap=True
                )
                console.print("[bold]Code:[/bold]")
                console.print(syntax)
        
        # Call user-provided callback if available
        if on_action_callback:
            return on_action_callback(action)
            
        # Default behavior: ask for confirmation
        return Confirm.ask("[bold yellow]Approve this action?[/bold yellow]")
    
    return on_action

def get_lexer_for_file(filepath: str) -> str:
    """Get lexer name based on file extension"""
    ext = os.path.splitext(filepath)[1].lower()
    
    lexer_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".html": "html",
        ".css": "css",
        ".json": "json",
        ".md": "markdown",
        ".txt": "text",
        ".sh": "bash",
        ".yml": "yaml",
        ".yaml": "yaml"
    }
    
    return lexer_map.get(ext, "text")

def handle_iteration_complete(progress) -> Callable:
    """Create a callback for iteration completion"""
    def on_iteration_complete(data: Dict[str, Any]) -> None:
        """Callback for iteration completion"""
        iteration = data.get("iteration", 0)
        actions = data.get("actions", [])
        
        # Update progress
        progress.update(task_id=1, completed=iteration)
        
        # Print summary
        console.print(f"\n[bold]Iteration {iteration} complete[/bold]")
        console.print(f"[dim]Actions executed: {len(actions)}[/dim]\n")
        
    return on_iteration_complete

@click.group()
@click.option('--workspace', '-w', default='./workspace', help='Workspace directory')
@click.option('--config', '-c', help='Path to config file')
@click.option('--log-file', '-l', help='Log file path')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.pass_context
def cli(ctx, workspace, config, log_file, verbose):
    """LLMAgent - LLM-powered development agent"""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Set up workspace
    setup_workspace(workspace)
    
    # Set up logging
    setup_logging(log_file)
    
    # Load settings
    config_settings = load_settings(config)
    
    # Override workspace in settings
    config_settings.filesystem.workspace_path = workspace
    
    # Save context for subcommands
    ctx.obj = {
        'workspace': workspace,
        'settings': config_settings
    }

@cli.command()
@click.argument('prompt')
@click.option('--mode', '-m', type=click.Choice(['approval', 'autonomous']), default='approval', 
              help='Agent operation mode')
@click.option('--model-type', type=click.Choice(['llamacpp', 'transformers']), default='llamacpp',
              help='Type of model to use')
@click.option('--model-id', help='Model ID or path')
@click.option('--iterations', '-i', type=int, help='Maximum number of iterations')
@click.option('--context-docs', '-d', multiple=True, help='Path to context documents')
@click.pass_context
def run(ctx, prompt, mode, model_type, model_id, iterations, context_docs):
    """Run the agent with the given prompt"""
    workspace = ctx.obj['workspace']
    config_settings = ctx.obj['settings']
    
    # Override settings
    config_settings.agent.mode = mode
    if iterations:
        config_settings.agent.max_iterations = iterations
    if model_id:
        config_settings.model.model_id = model_id
    
    # Initialize components
    model_kwargs = {"model_id": model_id} if model_id else {}
    agent = Agent(
        workspace_path=workspace,
        model_type=model_type,
        model_kwargs=model_kwargs
    )
    
    # Load context documents
    for doc_path in context_docs:
        try:
            with open(doc_path, 'r') as f:
                content = f.read()
            agent.add_context_doc(os.path.basename(doc_path), content)
            console.print(f"[green]Loaded context document: {doc_path}[/green]")
        except Exception as e:
            console.print(f"[red]Error loading context document {doc_path}: {str(e)}[/red]")
    
    # Create progress display
    progress = Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
    )
    
    # Start agent
    console.print(f"[bold green]Starting agent with prompt:[/bold green] {prompt}")
    console.print(f"[dim]Mode: {mode}, Model: {model_type}, Workspace: {workspace}[/dim]\n")
    
    with progress:
        # Create task
        task_id = progress.add_task(
            "Running agent", 
            total=iterations or config_settings.agent.max_iterations
        )
        
        # Define iteration callback
        def on_iteration_complete(data):
            iteration = data.get("iteration", 0)
            progress.update(task_id, completed=iteration)
            
            # Print thinking if available
            if "thinking" in data:
                console.print("\n[bold]Agent's thinking:[/bold]")
                console.print(data["thinking"])
            
            # Print action results
            for action_result in data.get("actions", []):
                action = action_result.get("action", {})
                result = action_result.get("result", {})
                
                if action and result:
                    console.print("\n[bold cyan]Action:[/bold cyan]", action.get("type"))
                    print_action(action)
                    print_result(result)
        
        try:
            # Run agent
            if mode == "approval":
                summary = agent.run(
                    initial_prompt=prompt,
                    on_action=handle_actions(agent, None),
                    on_iteration_complete=on_iteration_complete
                )
            else:
                summary = agent.run(
                    initial_prompt=prompt,
                    on_iteration_complete=on_iteration_complete
                )
            
            # Print summary
            console.print("\n[bold green]Agent execution complete![/bold green]")
            console.print(f"[bold]Summary:[/bold]")
            
            summary_table = Table(show_header=False)
            summary_table.add_column("Property")
            summary_table.add_column("Value")
            
            summary_table.add_row("Iterations", str(summary.get("iterations", 0)))
            summary_table.add_row("Total files", str(summary.get("total_files", 0)))
            summary_table.add_row("Elapsed time", f"{summary.get('elapsed_time', 0):.2f}s")
            
            file_types = summary.get("file_types", {})
            if file_types:
                file_types_str = ", ".join([f"{ext}: {count}" for ext, count in file_types.items()])
                summary_table.add_row("File types", file_types_str)
                
            console.print(summary_table)
            
            # Show workspace files
            console.print("\n[bold]Workspace files:[/bold]")
            files = summary.get("files", [])
            
            if files:
                file_table = Table(show_header=True)
                file_table.add_column("Type")
                file_table.add_column("Name")
                file_table.add_column("Path")
                file_table.add_column("Size")
                
                for file in files:
                    if file.get("is_dir", False):
                        file_table.add_row(
                            "📁", 
                            file.get("name", ""),
                            file.get("path", ""),
                            ""
                        )
                    else:
                        size_str = f"{file.get('size', 0) / 1024:.1f} KB" if file.get('size', 0) > 0 else ""
                        file_table.add_row(
                            "📄",
                            file.get("name", ""),
                            file.get("path", ""),
                            size_str
                        )
                
                console.print(file_table)
            else:
                console.print("[yellow]No files created[/yellow]")
            
        except KeyboardInterrupt:
            console.print("\n[bold yellow]Agent execution interrupted by user[/bold yellow]")
            agent.stop()
        except Exception as e:
            console.print(f"\n[bold red]Error during agent execution: {str(e)}[/bold red]")
            agent.stop()
            raise
    
    console.print("\n[bold green]Done![/bold green]")

@cli.command()
@click.option('--model-type', type=click.Choice(['llamacpp', 'transformers']), default='llamacpp', 
              help='Type of model to use')
@click.option('--model-id', help='Model ID or path')
@click.pass_context
def test_model(ctx, model_type, model_id):
    """Test the LLM model"""
    console.print(f"[bold]Testing {model_type} model[/bold]")
    
    if model_id:
        console.print(f"Model ID: {model_id}")
    
    try:
        # Initialize model
        model_kwargs = {"model_id": model_id} if model_id else {}
        model = get_model(model_type, **model_kwargs)
        
        # Test loading
        console.print("Loading model...")
        start_time = time.time()
        model.load()
        load_time = time.time() - start_time
        console.print(f"[green]Model loaded successfully in {load_time:.2f}s[/green]")
        
        # Test generation
        console.print("\nTesting text generation...")
        prompt = "Write a function that calculates the factorial of a number."
        
        start_time = time.time()
        response = model.generate(prompt, temperature=0.7, max_tokens=200)
        generation_time = time.time() - start_time
        
        console.print(f"[bold]Prompt:[/bold] {prompt}")
        console.print("[bold]Response:[/bold]")
        console.print(response)
        console.print(f"[dim]Generation time: {generation_time:.2f}s[/dim]")
        
        # Test tokenization
        console.print("\nTesting tokenization...")
        tokens = model.tokenize(prompt)
        console.print(f"[green]Tokenized prompt into {len(tokens)} tokens[/green]")
        
        console.print("\n[bold green]Model test completed successfully![/bold green]")
        
    except Exception as e:
        console.print(f"[bold red]Error testing model: {str(e)}[/bold red]")

@cli.command()
@click.pass_context
def init(ctx):
    """Initialize a new project in the workspace"""
    workspace = ctx.obj['workspace']
    
    console.print(f"[bold]Initializing new project in {workspace}[/bold]")
    
    try:
        # Create standard project structure
        os.makedirs(os.path.join(workspace, "src"), exist_ok=True)
        os.makedirs(os.path.join(workspace, "tests"), exist_ok=True)
        os.makedirs(os.path.join(workspace, "docs"), exist_ok=True)
        
        # Create README.md
        with open(os.path.join(workspace, "README.md"), 'w') as f:
            f.write("# Project\n\nCreated with LLMAgent\n")
        
        # Create .gitignore
        with open(os.path.join(workspace, ".gitignore"), 'w') as f:
            f.write("__pycache__/\n*.py[cod]\n*$py.class\n.env\nvenv/\n.vscode/\n")
        
        # Create initial files
        with open(os.path.join(workspace, "src", "__init__.py"), 'w') as f:
            f.write("")
            
        with open(os.path.join(workspace, "tests", "__init__.py"), 'w') as f:
            f.write("")
            
        console.print("[green]Project initialized successfully![/green]")
        
        # Print structure
        console.print("\n[bold]Project structure:[/bold]")
        console.print("├── src/")
        console.print("│   └── __init__.py")
        console.print("├── tests/")
        console.print("│   └── __init__.py")
        console.print("├── docs/")
        console.print("├── README.md")
        console.print("└── .gitignore")
        
    except Exception as e:
        console.print(f"[bold red]Error initializing project: {str(e)}[/bold red]")

if __name__ == '__main__':
    cli(obj={})
