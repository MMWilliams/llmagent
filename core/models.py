import os
from typing import List, Dict, Any, Optional, Union, Callable
import logging
from huggingface_hub import hf_hub_download
from ..config.settings import settings

logger = logging.getLogger(__name__)

class ModelBase:
    """Base class for LLM implementations"""
    
    def __init__(self, model_id: Optional[str] = None, **kwargs):
        self.model_id = model_id or settings.model.model_id
        self.model = None
        self.tokenizer = None
        self.initialized = False
        
    def load(self) -> None:
        """Load the model and tokenizer"""
        raise NotImplementedError("Subclasses must implement load()")
    
    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text from a prompt"""
        raise NotImplementedError("Subclasses must implement generate()")
    
    def tokenize(self, text: str) -> List[int]:
        """Tokenize the input text"""
        raise NotImplementedError("Subclasses must implement tokenize()")
    
    def get_num_tokens(self, text: str) -> int:
        """Count the number of tokens in the text"""
        return len(self.tokenize(text))

class ModelBase:
    # Add to existing methods
    
    def generate_stream(self, prompt: str, **kwargs) -> Iterator[str]:
        """Generate text from a prompt with streaming output
        
        Args:
            prompt: Input prompt string
            **kwargs: Additional parameters for generation
            
        Yields:
            Text chunks as they are generated
        """
        raise NotImplementedError("Subclasses must implement generate_stream()")


class LlamaCppModel(ModelBase):
    # Add to existing methods
    
    def generate_stream(self, prompt: str, **kwargs) -> Iterator[str]:
        """Generate text using the loaded model with streaming output"""
        if not self.initialized:
            self.load()
        
        temperature = kwargs.get('temperature', settings.model.temperature)
        max_tokens = kwargs.get('max_tokens', settings.model.max_tokens)
        top_p = kwargs.get('top_p', settings.model.top_p)
        
        try:
            stream = self.model(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                repeat_penalty=settings.model.repetition_penalty,
                stream=True,  # Enable streaming
                echo=False
            )
            
            # Yield text chunks as they come
            for chunk in stream:
                if isinstance(chunk, dict) and 'choices' in chunk:
                    yield chunk['choices'][0]['text']
                elif isinstance(chunk, list) and len(chunk) > 0:
                    yield chunk[0]['text']
                else:
                    yield str(chunk)
                    
        except Exception as e:
            logger.error(f"Streaming text generation failed: {e}")
            yield f"Error generating text: {str(e)}"
class LlamaCppModel(ModelBase):
    """LLM implementation using llama-cpp-python"""
    
    def __init__(self, model_id: Optional[str] = None, model_file: Optional[str] = None, **kwargs):
        super().__init__(model_id, **kwargs)
        self.model_file = model_file or settings.model.model_file
        self.context_length = kwargs.get('context_length', settings.model.context_length)
        self.loaded_model_path = None
        
    def load(self) -> None:
        """Download and load the model"""
        from llama_cpp import Llama
        
        if self.initialized:
            return
            
        logger.info(f"Loading model: {self.model_id}")
        
        try:
            # Download the model if not already available
            if not os.path.exists(self.model_file):
                try:
                    model_path = hf_hub_download(
                        repo_id=self.model_id,
                        filename=self.model_file,
                        cache_dir="./models"
                    )
                    self.loaded_model_path = model_path
                except Exception as e:
                    raise RuntimeError(f"Failed to download model: {e}")
            else:
                self.loaded_model_path = self.model_file
            
            # Load the model
            self.model = Llama(
                model_path=self.loaded_model_path,
                n_ctx=self.context_length,
                n_batch=512,
                verbose=False
            )
            
            logger.info(f"Model loaded successfully: {self.model_id}")
            self.initialized = True
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
    
    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text using the loaded model"""
        if not self.initialized:
            self.load()
        
        temperature = kwargs.get('temperature', settings.model.temperature)
        max_tokens = kwargs.get('max_tokens', settings.model.max_tokens)
        top_p = kwargs.get('top_p', settings.model.top_p)
        
        try:
            output = self.model(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                repeat_penalty=settings.model.repetition_penalty,
                echo=False
            )
            
            # Extract generated text from output
            if isinstance(output, dict) and 'choices' in output:
                return output['choices'][0]['text'].strip()
            elif isinstance(output, list) and len(output) > 0:
                return output[0]['text'].strip()
            else:
                return str(output).strip()
                
        except Exception as e:
            logger.error(f"Text generation failed: {e}")
            return f"Error generating text: {str(e)}"
    
    def tokenize(self, text: str) -> List[int]:
        """Tokenize text using the model's tokenizer"""
        if not self.initialized:
            self.load()
        
        try:
            tokens = self.model.tokenize(text.encode('utf-8'))
            return tokens
        except:
            # Fallback to approximate token counting
            return [0] * (len(text.split()) * 3 // 4)  # Rough approximation
            
            
class TransformersModel(ModelBase):
    """LLM implementation using HuggingFace Transformers"""
    
    def __init__(self, model_id: Optional[str] = None, **kwargs):
        super().__init__(model_id, **kwargs)
        
    def load(self) -> None:
        """Load the model and tokenizer from HuggingFace"""
        if self.initialized:
            return
            
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch
        
        logger.info(f"Loading model: {self.model_id}")
        
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_id)
            
            # Load model with optimal settings based on available hardware
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_id,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                low_cpu_mem_usage=True,
                device_map="auto"
            )
            
            logger.info(f"Model loaded successfully: {self.model_id}")
            self.initialized = True
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
    
    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text using the loaded model"""
        if not self.initialized:
            self.load()
        
        temperature = kwargs.get('temperature', settings.model.temperature)
        max_tokens = kwargs.get('max_tokens', settings.model.max_tokens)
        
        try:
            input_ids = self.tokenizer.encode(prompt, return_tensors="pt").to(self.model.device)
            
            gen_kwargs = {
                "input_ids": input_ids,
                "max_length": input_ids.shape[1] + max_tokens,
                "temperature": temperature,
                "top_p": settings.model.top_p,
                "repetition_penalty": settings.model.repetition_penalty,
                "do_sample": temperature > 0.0,
                "pad_token_id": self.tokenizer.eos_token_id
            }
            
            with torch.no_grad():
                output = self.model.generate(**gen_kwargs)
            
            # Decode and return only the newly generated tokens
            return self.tokenizer.decode(
                output[0][input_ids.shape[1]:], 
                skip_special_tokens=True
            )
                
        except Exception as e:
            logger.error(f"Text generation failed: {e}")
            return f"Error generating text: {str(e)}"
    
    def tokenize(self, text: str) -> List[int]:
        """Tokenize text using the model's tokenizer"""
        if not self.initialized:
            self.load()
        
        return self.tokenizer.encode(text)
            

def get_model(model_type: str = "llamacpp", **kwargs) -> ModelBase:
    """Factory function to get the appropriate model"""
    if model_type.lower() == "llamacpp":
        return LlamaCppModel(**kwargs)
    elif model_type.lower() == "transformers":
        return TransformersModel(**kwargs)
    else:
        raise ValueError(f"Unsupported model type: {model_type}")
