from typing import List, Dict, Any, Optional
def format_user_prompt(conversation_history: List[Dict[str, str]]) -> str:
    """Format the conversation history into a prompt string for the LLM.
    
    Args:
        conversation_history: List of conversation messages with 'role' and 'content'
        
    Returns:
        Formatted prompt string for the model
    """
    formatted_prompt = ""
    
    for message in conversation_history:
        role = message.get("role", "")
        content = message.get("content", "")
        
        if role.lower() == "system":
            formatted_prompt += f"<|system|>\n{content}\n"
        elif role.lower() == "user":
            formatted_prompt += f"<|user|>\n{content}\n"
        elif role.lower() == "assistant":
            formatted_prompt += f"<|assistant|>\n{content}\n"
        else:
            # Handle unknown roles
            formatted_prompt += f"<|{role}|>\n{content}\n"
    
    # Add final assistant marker to indicate where the model should continue
    formatted_prompt += "<|assistant|>\n"
    
    return formatted_prompt
def get_system_prompt(context_docs: Optional[List[Dict[str, str]]] = None) -> str:
    """Get the system prompt for the agent"""
    base_prompt = """
    You are an expert software developer agent that can create, edit, and manage files and code.

    # CAPABILITIES
    1. You can create and edit files within the specified workspace
    2. You can run code and tests to verify your implementation
    3. You can read logs and debug issues
    4. You have perfect memory of the files you create and modify
    5. You follow best practices in software development including modular design, error handling, and testing

    # ACTION FORMAT
    You can perform actions by outputting JSON blocks like this:

    ```json
    {
    "type": "action_type",
    "params": {
        "param1": "value1",
        "param2": "value2"
    }
    }
    ```
    """
    return base_prompt

