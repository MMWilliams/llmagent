# LLMAgent: LLM-Powered Development Agent

LLMAgent is an open source Python library that provides an LLM-powered development agent capable of creating, editing, and managing files and code autonomously.

## Table of Contents
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
  - [Basic Usage](#basic-usage)
  - [Advanced Usage](#advanced-usage)
  - [Configuration](#configuration)
- [Core Components](#core-components)
  - [Agent](#agent)
  - [Models](#models)
  - [File Manager](#file-manager)
  - [Code Executor](#code-executor)
  - [Vector Store](#vector-store)
- [Available Actions](#available-actions)
- [API Server](#api-server)
- [VSCode Extension](#vscode-extension)
- [Custom Extensions](#custom-extensions)
- [Best Practices](#best-practices)
- [Example Workflow: Creating a FastAPI Project](#example-workflow-creating-a-fastapi-project)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Features

- **File Management**: Create, edit, and manage files within a predefined workspace
- **Code Generation**: Generate code files and manage project structure
- **Code Execution**: Run and test code with built-in sandboxing
- **Document Context**: Pass documentation to the LLM for context
- **CLI Interface**: Easy-to-use command line interface
- **Multiple Models**: Support for different LLM backends
- **Monitoring**: Built-in status reporting and telemetry
- **Approval Modes**: Choose between manual approval or autonomous operation

## Installation

```bash
# Clone the repository
git clone https://github.com/mmwilliams/llmagent.git
cd llmagent

# Install the package
pip install -e .
```

## Usage

### Basic Usage

```bash
# Initialize a workspace
llmagent --workspace ./my_project init

# Run the agent with a prompt
llmagent --workspace ./my_project run "Create a Flask API with two endpoints: /users and /products"
```

### Advanced Usage

```bash
# Run in autonomous mode with a specific model
llmagent --workspace ./my_project run --mode autonomous --model-type llamacpp --model-id "TheBloke/Mistral-7B-Instruct-v0.2-GGUF" "Create a TODO application with FastAPI backend and React frontend"

# Provide context documents
llmagent --workspace ./my_project run --context-docs docs/api_spec.md --context-docs docs/architecture.md "Implement the API according to the provided specification"
```

### Configuration

LLMAgent can be configured with a YAML or JSON configuration file:

```bash
llmagent --config config.yaml run "Create a web scraper that extracts product data"
```

Example configuration (config.yaml):

```yaml
model:
  model_id: "TheBloke/Mistral-7B-Instruct-v0.2-GGUF"
  temperature: 0.7
  max_tokens: 2048

agent:
  mode: "approval"  # or "autonomous"
  max_iterations: 50

filesystem:
  max_file_size_mb: 10
  backup_enabled: true

executor:
  timeout_seconds: 30
  sandbox_enabled: true
```

## Core Components

### Agent

The central component that orchestrates the entire system:

```python
from llmagent.core.agent import Agent

# Initialize an agent
agent = Agent(
    workspace_path="./my_project",
    model_type="llamacpp",
    model_kwargs={"model_id": "TheBloke/Mistral-7B-Instruct-v0.2-GGUF"}
)

# Run the agent with a prompt
summary = agent.run(
    initial_prompt="Create a simple web scraper that extracts product data",
    max_iterations=10,
    on_action=lambda action: True  # Auto-approve all actions
)

# Print summary
print(summary)
```

### Models

LLMAgent supports multiple LLM backends:

```python
from llmagent.core.models import get_model

# Use LlamaCPP model
model = get_model(
    model_type="llamacpp", 
    model_id="TheBloke/Mistral-7B-Instruct-v0.2-GGUF"
)

# Or use HuggingFace Transformers model
model = get_model(
    model_type="transformers", 
    model_id="mistralai/Mistral-7B-Instruct-v0.2"
)

# Generate text
response = model.generate(
    prompt="Write a function to calculate factorial",
    temperature=0.7,
    max_tokens=500
)
```

### File Manager

Safely manage files within a workspace:

```python
from llmagent.core.file_manager import FileManager

# Initialize file manager
fm = FileManager(workspace_path="./my_project")

# List files
files = fm.list_files()

# Read file
content = fm.read_file("main.py")

# Write file
fm.write_file("new_file.py", "print('Hello world')")
```

### Code Executor

Execute code safely:

```python
from llmagent.core.executor import CodeExecutor

# Initialize executor
executor = CodeExecutor(workspace_path="./my_project")

# Execute Python code
result = executor.execute_code("print('Hello world')")
print(result.output)  # "Hello world"

# Run a shell command
result = executor.run_command("ls -la")
print(result.output)
```

### Vector Store

For knowledge management and semantic search:

```python
from llmagent.core.vector_store import VectorStore

# Initialize vector store
vs = VectorStore(workspace_path="./my_project")

# Add documents
vs.add_document("Flask is a lightweight WSGI web application framework.")
vs.add_document("FastAPI is a modern, fast web framework for building APIs.")

# Search for similar documents
results = vs.search("How do I create a web API?")
for result in results:
    print(f"Score: {result['score']}, Text: {result['text']}")
```

## Available Actions

The agent can perform various actions:

### Read File
```json
{
  "type": "read_file",
  "params": {
    "filepath": "path/to/file.py"
  }
}
```

### Write File
```json
{
  "type": "write_file",
  "params": {
    "filepath": "path/to/file.py",
    "content": "# Python code here\n\ndef example():\n    return 'Hello World!'"
  }
}
```

### List Files
```json
{
  "type": "list_files",
  "params": {
    "path": "path/to/directory"  // Optional, defaults to root workspace
  }
}
```

### Create Directory
```json
{
  "type": "create_directory",
  "params": {
    "path": "path/to/new/directory"
  }
}
```

### Delete File
```json
{
  "type": "delete_file",
  "params": {
    "filepath": "path/to/file.py"
  }
}
```

### Run Code
```json
{
  "type": "run_code",
  "params": {
    "code": "print('Hello World!')",
    "mode": "exec"  // Optional, can be "exec" or "eval", defaults to "exec"
  }
}
```

### Run Command
```json
{
  "type": "run_command",
  "params": {
    "command": "pip list"
  }
}
```

### Run Test
```json
{
  "type": "run_test",
  "params": {
    "test_path": "tests/test_example.py"
  }
}
```

### Read Logs
```json
{
  "type": "read_logs",
  "params": {
    "log_path": "logs/app.log",
    "num_lines": 100  // Optional, defaults to 100
  }
}
```

## API Server

LLMAgent includes a REST API for remote control:

```bash
# Start the API server
python -m llmagent.api.server
```

Example API usage:

```python
import requests

# Create a new agent
response = requests.post("http://localhost:8000/agents", json={
    "model_type": "llamacpp",
    "model_id": "TheBloke/Mistral-7B-Instruct-v0.2-GGUF"
})
workspace_id = response.json()["workspace_id"]

# Run a prompt
response = requests.post(f"http://localhost:8000/agents/{workspace_id}/prompt", json={
    "prompt": "Create a Flask API with two endpoints: /users and /products",
    "mode": "autonomous"
})

# Check status
response = requests.get(f"http://localhost:8000/agents/{workspace_id}/status")
print(response.json())
```

## VSCode Extension

LLMAgent includes a VSCode extension for direct integration with your editor:

1. Install the extension from the `extensions/vscode` directory
2. Start the API server
3. Use the extension to initialize and control agents directly from VSCode

## Custom Extensions

You can extend the agent with custom actions by subclassing the `Agent` class:

```python
from llmagent.core.agent import Agent

class CustomAgent(Agent):
    def _execute_action(self, action_type, params):
        # Handle custom actions
        if action_type == "my_custom_action":
            # Implement custom action
            return {
                "status": "success",
                "result": "Custom action executed"
            }
        
        # Fall back to default implementation
        return super()._execute_action(action_type, params)
```

## Best Practices

1. **Start Small**: Begin with well-defined, specific tasks rather than large open-ended projects
2. **Approval Mode**: Use approval mode initially to review actions before they're executed
3. **Context Documents**: Provide context documents for more complex tasks
4. **Clear Prompts**: Be specific in your prompts, including desired technologies and patterns
5. **Security**: Use sandboxing and limit filesystem access for untrusted code
6. **Review Output**: Always review generated code for security and correctness
7. **Iterative Approach**: Build complex applications in stages
8. **Provide Examples**: When possible, provide examples of the code style or patterns you prefer
9. **Keep Context Small**: For large projects, focus on specific components in each prompt

## Example Workflow: Creating a FastAPI Project

This section walks through a complete workflow using LLMAgent to create a FastAPI application with a database backend.

### Setup

First, make sure you have LLMAgent installed:

```bash
# Clone the repository
git clone https://github.com/mmwilliams/llmagent.git
cd llmagent

# Install the package
pip install -e .
```

### Step 1: Initialize a Workspace

Create a new workspace for your project:

```bash
# Create and initialize a new workspace
llmagent --workspace ./fastapi_project init
```

### Step 2: Create a Specification Document

Create a file called `spec.md` with the application requirements:

```markdown
# FastAPI Application Specification

## Overview
Create a FastAPI application that provides a RESTful API for a book inventory system.

## Requirements

### Database Models
- Book: id, title, author, published_year, genre, description, in_stock
- Author: id, name, birth_year, biography

### API Endpoints
- GET /books - List all books
- GET /books/{id} - Get a specific book
- POST /books - Create a new book
- PUT /books/{id} - Update a book
- DELETE /books/{id} - Delete a book
- GET /authors - List all authors
- GET /authors/{id} - Get a specific author
- POST /authors - Create a new author

### Additional Features
- Add pagination to list endpoints
- Add filtering capabilities
- Include OpenAPI documentation
- Implement proper error handling
- Add SQLAlchemy for database operations
```

### Step 3: Run the Agent

Run LLMAgent with the specification as context:

```bash
llmagent --workspace ./fastapi_project run \
  --context-docs spec.md \
  --mode approval \
  "Create a FastAPI application according to the provided specification"
```

### Step 4: Review and Approve Actions

The agent will start proposing actions. For each action, review and approve:

1. The agent will first list the files to understand the workspace
2. The agent will create a project structure
3. The agent will write code files one by one

For example, when it proposes to write a file like `models.py`:

```json
{
  "type": "write_file",
  "params": {
    "filepath": "app/models.py",
    "content": "from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey\nfrom sqlalchemy.ext.declarative import declarative_base\nfrom sqlalchemy.orm import relationship\n\nBase = declarative_base()\n\nclass Author(Base):\n    __tablename__ = 'authors'\n    \n    id = Column(Integer, primary_key=True, index=True)\n    name = Column(String(100), nullable=False)\n    birth_year = Column(Integer)\n    biography = Column(Text)\n    books = relationship('Book', back_populates='author')\n\nclass Book(Base):\n    __tablename__ = 'books'\n    \n    id = Column(Integer, primary_key=True, index=True)\n    title = Column(String(200), nullable=False)\n    author_id = Column(Integer, ForeignKey('authors.id'))\n    published_year = Column(Integer)\n    genre = Column(String(50))\n    description = Column(Text)\n    in_stock = Column(Boolean, default=True)\n    author = relationship('Author', back_populates='books')\n"
  }
}
```

Review the content and approve if it looks good.

### Step 5: Testing the Application

After the agent has created all the necessary files, it will propose to run tests:

```json
{
  "type": "run_command",
  "params": {
    "command": "cd ./fastapi_project && pytest"
  }
}
```

Approve this to run the tests.

### Step 6: Running the Application

Finally, the agent will propose to run the application:

```json
{
  "type": "run_command",
  "params": {
    "command": "cd ./fastapi_project && uvicorn app.main:app --reload"
  }
}
```

Approve this to start the application.

### Step 7: Exploring the API

Once the application is running, you can access:

- API documentation: http://localhost:8000/docs
- API endpoints directly: http://localhost:8000/books

### Step 8: Making Modifications

To modify the application, you can run LLMAgent again with a new prompt:

```bash
llmagent --workspace ./fastapi_project run \
  "Add a 'ratings' feature to the book model with corresponding API endpoints"
```

The agent will:
1. Analyze the existing codebase
2. Propose changes to add the new feature
3. Update the necessary files
4. Run tests to ensure everything works

### Step 9: Debugging Issues

If you encounter any issues, you can ask the agent to debug them:

```bash
llmagent --workspace ./fastapi_project run \
  "Debug the error that occurs when trying to delete an author who has books"
```

The agent will:
1. Analyze the error
2. Propose a solution
3. Implement the fix
4. Test the solution

### Complete Project Structure

After completion, your project should look like this:

```
fastapi_project/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── models.py
│   ├── database.py
│   ├── schemas.py
│   ├── crud/
│   │   ├── __init__.py
│   │   ├── authors.py
│   │   └── books.py
│   └── routers/
│       ├── __init__.py
│       ├── authors.py
│       └── books.py
├── tests/
│   ├── __init__.py
│   ├── test_authors.py
│   └── test_books.py
├── requirements.txt
└── README.md
```

### Going Further

You can enhance your application by instructing the agent to:

1. Add authentication
2. Implement caching
3. Create a frontend using a framework like React
4. Deploy the application to a cloud provider
5. Set up CI/CD pipelines

Simply run LLMAgent with the appropriate prompts, and it will handle the implementation.

## Troubleshooting

### Model Loading Issues

If you encounter issues loading models:

```bash
# Check model path
llmagent test-model --model-type llamacpp --model-id "your-model-path"

# Use a different model
llmagent --workspace ./my_project run --model-type transformers --model-id "small-model" "Create a simple script"
```

### Permission Errors

If you encounter permission errors:

```bash
# Check workspace directory permissions
chmod -R 755 ./my_project

# Run with elevated privileges for system operations
sudo llmagent --workspace ./system_config run "..."
```

## Contributing

Contributions are welcome! Please see the [CONTRIBUTING.md](CONTRIBUTING.md) file for details.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.