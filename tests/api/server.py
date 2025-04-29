from typing import Dict, Any, List, Optional
import os
import logging
import json
import time
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import uvicorn
from threading import Thread

from ..core.agent import Agent
from ..config.settings import settings

app = FastAPI(title="LLMAgent API", description="API for LLM-powered development agent")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logger
logger = logging.getLogger(__name__)

# Store active agents
active_agents = {}

# Models
class AgentRequest(BaseModel):
    """Request to create a new agent"""
    workspace_id: Optional[str] = None
    model_type: str = "llamacpp"
    model_id: Optional[str] = None
    
class PromptRequest(BaseModel):
    """Request to run a prompt"""
    prompt: str
    max_iterations: Optional[int] = None
    mode: str = "approval"
    
class ActionRequest(BaseModel):
    """Request to approve or reject an action"""
    action_id: str
    approved: bool
    
class ContextDocRequest(BaseModel):
    """Request to add a context document"""
    name: str
    content: str

# Routes
@app.post("/agents", response_model=Dict[str, Any])
async def create_agent(request: AgentRequest):
    """Create a new agent instance"""
    # Generate workspace ID if not provided
    workspace_id = request.workspace_id or f"workspace_{int(time.time())}"
    
    # Create workspace path
    workspace_path = os.path.join(settings.filesystem.workspace_path, workspace_id)
    
    try:
        # Initialize agent
        model_kwargs = {"model_id": request.model_id} if request.model_id else {}
        agent = Agent(
            workspace_path=workspace_path,
            model_type=request.model_type,
            model_kwargs=model_kwargs
        )
        
        # Store agent
        active_agents[workspace_id] = {
            "agent": agent,
            "created_at": time.time(),
            "status": "initialized",
            "pending_actions": []
        }
        
        return {
            "workspace_id": workspace_id,
            "status": "initialized",
            "workspace_path": workspace_path
        }
        
    except Exception as e:
        logger.error(f"Error creating agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/agents/{workspace_id}/prompt", response_model=Dict[str, Any])
async def run_prompt(workspace_id: str, request: PromptRequest, background_tasks: BackgroundTasks):
    """Run a prompt with the agent"""
    # Check if agent exists
    if workspace_id not in active_agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent_data = active_agents[workspace_id]
    agent = agent_data["agent"]
    
    # Update agent mode
    agent.mode = request.mode
    
    # Start agent in background if autonomous mode
    if request.mode == "autonomous":
        background_tasks.add_task(
            run_agent_task, 
            agent, 
            request.prompt, 
            request.max_iterations,
            workspace_id
        )
        
        agent_data["status"] = "running"
        
        return {
            "status": "running",
            "workspace_id": workspace_id,
            "mode": request.mode
        }
    
    # For approval mode, run first iteration and return pending actions
    def on_action(action):
        # Store action for later approval
        action_id = f"action_{int(time.time())}_{len(agent_data['pending_actions'])}"
        agent_data["pending_actions"].append({
            "id": action_id,
            "action": action,
            "created_at": time.time()
        })
        # Always return False to prevent execution
        return False
    
    # Run one iteration
    try:
        agent.run(
            initial_prompt=request.prompt,
            max_iterations=1,
            on_action=on_action
        )
        
        agent_data["status"] = "waiting_approval"
        
        return {
            "status": "waiting_approval",
            "workspace_id": workspace_id,
            "pending_actions": [
                {"id": a["id"], "action": a["action"]} 
                for a in agent_data["pending_actions"]
            ]
        }
        
    except Exception as e:
        logger.error(f"Error running prompt: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/agents/{workspace_id}/status", response_model=Dict[str, Any])
async def get_agent_status(workspace_id: str):
    """Get the status of an agent"""
    # Check if agent exists
    if workspace_id not in active_agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent_data = active_agents[workspace_id]
    agent = agent_data["agent"]
    
    # Get status
    status_data = agent.status_reporter.get_status()
    
    return {
        "workspace_id": workspace_id,
        "agent_status": agent_data["status"],
        "iteration": agent.iteration,
        "progress": status_data
    }

@app.post("/agents/{workspace_id}/actions/{action_id}", response_model=Dict[str, Any])
async def handle_action(workspace_id: str, action_id: str, request: ActionRequest):
    """Approve or reject an action"""
    # Check if agent exists
    if workspace_id not in active_agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent_data = active_agents[workspace_id]
    agent = agent_data["agent"]
    
    # Find the action
    action_data = None
    for a in agent_data["pending_actions"]:
        if a["id"] == action_id:
            action_data = a
            break
    
    if not action_data:
        raise HTTPException(status_code=404, detail="Action not found")
    
    # Process action
    if request.approved:
        # Execute the action
        result = agent._execute_action(
            action_data["action"]["type"],
            action_data["action"]["params"]
        )
        
        # Remove from pending
        agent_data["pending_actions"] = [
            a for a in agent_data["pending_actions"] if a["id"] != action_id
        ]
        
        return {
            "status": "executed",
            "result": result
        }
    else:
        # Remove from pending
        agent_data["pending_actions"] = [
            a for a in agent_data["pending_actions"] if a["id"] != action_id
        ]
        
        return {
            "status": "rejected"
        }

# Helper function to run agent in background
async def run_agent_task(agent, prompt, max_iterations, workspace_id):
    """Run agent in background task"""
    try:
        summary = agent.run(initial_prompt=prompt, max_iterations=max_iterations)
        active_agents[workspace_id]["status"] = "completed"
        active_agents[workspace_id]["summary"] = summary
    except Exception as e:
        logger.error(f"Error in background agent task: {e}")
        active_agents[workspace_id]["status"] = "failed"
        active_agents[workspace_id]["error"] = str(e)

# Run the API server
def start_api(host="0.0.0.0", port=8000):
    """Start the API server"""
    uvicorn.run(app, host=host, port=port)

# Run directly
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_api()