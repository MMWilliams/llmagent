import os
import unittest
import tempfile
import shutil
from unittest.mock import MagicMock, patch
import sys

# Add parent directory to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent import Agent
from core.models import ModelBase
from core.file_manager import FileManager
from core.executor import CodeExecutor

class TestAgent(unittest.TestCase):
    """Test cases for the Agent class"""
    
    def setUp(self):
        """Set up test environment"""
        # Create a temporary directory for tests
        self.test_dir = tempfile.mkdtemp()
        
        # Mock model
        self.mock_model = MagicMock(spec=ModelBase)
        self.mock_model.generate.return_value = "Test response"
        
        # Create agent with mock components
        with patch('core.agent.get_model', return_value=self.mock_model):
            self.agent = Agent(workspace_path=self.test_dir)
            
    def tearDown(self):
        """Clean up after tests"""
        # Remove temporary directory
        shutil.rmtree(self.test_dir)
        
    def test_agent_initialization(self):
        """Test agent initialization"""
        self.assertEqual(self.agent.workspace_path, self.test_dir)
        self.assertEqual(self.agent.model, self.mock_model)
        self.assertIsInstance(self.agent.file_manager, FileManager)
        self.assertIsInstance(self.agent.executor, CodeExecutor)
        
    def test_set_context_docs(self):
        """Test setting context documents"""
        docs = [
            {"name": "test.txt", "content": "Test content"}
        ]
        
        self.agent.set_context_docs(docs)
        self.assertEqual(self.agent.context_docs, docs)
        
    def test_parse_actions(self):
        """Test parsing actions from agent response"""
        # Test with JSON action
        response = """
        I'll create a file for you.
        
        ```json
        {
            "type": "write_file",
            "params": {
                "filepath": "test.py",
                "content": "print('Hello world')"
            }
        }
        ```
        """
        
        actions = self.agent._parse_actions(response)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["type"], "write_file")
        self.assertEqual(actions[0]["params"]["filepath"], "test.py")
        
        # Test with multiple actions
        response = """
        I'll create two files for you.
        
        ```json
        [
            {
                "type": "write_file",
                "params": {
                    "filepath": "test1.py",
                    "content": "print('Hello world 1')"
                }
            },
            {
                "type": "write_file",
                "params": {
                    "filepath": "test2.py",
                    "content": "print('Hello world 2')"
                }
            }
        ]
        ```
        """
        
        actions = self.agent._parse_actions(response)
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0]["type"], "write_file")
        self.assertEqual(actions[1]["type"], "write_file")

if __name__ == '__main__':
    unittest.main()