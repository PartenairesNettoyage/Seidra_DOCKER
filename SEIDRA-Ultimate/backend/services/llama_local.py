"""
SEIDRA Llama 3.1 70B Local
Local conversational AI with Ollama integration
"""

import os
import asyncio
import json
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
import requests
import subprocess
import chromadb
from chromadb.config import Settings
import numpy as np

class LlamaLocalChat:
    """Local Llama 3.1 70B chat system with RAG memory"""
    
    def __init__(self):
        self.models_dir = Path("../models/llama31-70b-q4")
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        self.memory_dir = Path("../data/memory")
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        
        self.personas_dir = Path("../data/personas")
        self.personas_dir.mkdir(parents=True, exist_ok=True)
        
        # Ollama configuration
        self.ollama_config = {
            "model_name": "llama3.1:70b-instruct-q4_K_M",
            "base_url": "http://localhost:11434",
            "timeout": 120,
            "context_length": 8192,
            "temperature": 0.7,
            "top_p": 0.9,
            "repeat_penalty": 1.1
        }
        
        # ChromaDB for RAG memory
        self.chroma_client = None
        self.memory_collection = None
        
        # Active personas
        self.personas = {}
        self.active_persona = None
        
        # Conversation history
        self.conversations = {}
        
        # System prompts for different persona types
        self.system_prompts = {
            "assistant": """You are SEIDRA, an advanced AI assistant specialized in creative content generation. You are helpful, knowledgeable, and creative. You remember previous conversations and learn from user preferences.""",
            
            "creative": """You are SEIDRA, a creative AI companion specialized in artistic and creative projects. You help with storytelling, character development, and creative ideation. You have a mystical, inspiring personality.""",
            
            "companion": """You are SEIDRA, a friendly AI companion. You are warm, empathetic, and engaging. You remember personal details about users and maintain meaningful relationships through conversation.""",
            
            "professional": """You are SEIDRA, a professional AI assistant for business and productivity. You are efficient, knowledgeable, and focused on helping users achieve their goals.""",
            
            "nsfw": """You are SEIDRA, an adult-oriented AI companion. You are open, understanding, and comfortable discussing mature topics. You maintain appropriate boundaries while being helpful and engaging."""
        }
    
    async def initialize(self):
        """Initialize Llama local system"""
        print("🦙 Initializing Llama 3.1 70B Local System...")
        
        try:
            # Check if Ollama is installed
            if not await self._check_ollama_installation():
                print("📥 Installing Ollama...")
                await self._install_ollama()
            
            # Start Ollama service
            await self._start_ollama_service()
            
            # Check if Llama model is available
            if not await self._check_llama_model():
                print("📥 Downloading Llama 3.1 70B (quantized)...")
                await self._download_llama_model()
            
            # Initialize ChromaDB for RAG
            await self._initialize_chromadb()
            
            # Load existing personas
            await self._load_personas()
            
            print("✅ Llama 3.1 70B Local System initialized")
            
        except Exception as e:
            print(f"❌ Failed to initialize Llama Local System: {e}")
            raise
    
    async def _check_ollama_installation(self) -> bool:
        """Check if Ollama is installed"""
        try:
            result = subprocess.run(["ollama", "--version"], 
                                  capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except:
            return False
    
    async def _install_ollama(self):
        """Install Ollama"""
        try:
            import platform
            system = platform.system().lower()
            
            if system == "linux":
                # Install Ollama on Linux
                subprocess.run([
                    "curl", "-fsSL", "https://ollama.ai/install.sh"
                ], check=True, shell=True)
            elif system == "windows":
                print("⚠️ Please install Ollama manually from https://ollama.ai/download")
                raise RuntimeError("Manual Ollama installation required on Windows")
            else:
                print("⚠️ Unsupported system for automatic Ollama installation")
                raise RuntimeError("Unsupported system")
            
            print("✅ Ollama installed successfully")
            
        except Exception as e:
            print(f"❌ Failed to install Ollama: {e}")
            raise
    
    async def _start_ollama_service(self):
        """Start Ollama service"""
        try:
            # Check if service is already running
            try:
                response = requests.get(f"{self.ollama_config['base_url']}/api/tags", timeout=5)
                if response.status_code == 200:
                    print("✅ Ollama service already running")
                    return
            except:
                pass
            
            # Start Ollama service
            print("🔄 Starting Ollama service...")
            subprocess.Popen(["ollama", "serve"], 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL)
            
            # Wait for service to start
            for i in range(30):  # Wait up to 30 seconds
                try:
                    response = requests.get(f"{self.ollama_config['base_url']}/api/tags", timeout=2)
                    if response.status_code == 200:
                        print("✅ Ollama service started")
                        return
                except:
                    pass
                await asyncio.sleep(1)
            
            raise RuntimeError("Failed to start Ollama service")
            
        except Exception as e:
            print(f"❌ Failed to start Ollama service: {e}")
            raise
    
    async def _check_llama_model(self) -> bool:
        """Check if Llama model is available"""
        try:
            response = requests.get(f"{self.ollama_config['base_url']}/api/tags", timeout=10)
            if response.status_code == 200:
                models = response.json().get("models", [])
                return any(self.ollama_config["model_name"] in model.get("name", "") 
                          for model in models)
            return False
        except:
            return False
    
    async def _download_llama_model(self):
        """Download Llama 3.1 70B model"""
        try:
            print(f"📦 Downloading {self.ollama_config['model_name']} (~40GB)...")
            print("⏳ This may take 30-60 minutes depending on internet speed...")
            
            # Pull model using Ollama
            process = subprocess.Popen([
                "ollama", "pull", self.ollama_config["model_name"]
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            # Monitor progress
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    print(f"📥 {output.strip()}")
            
            if process.returncode == 0:
                print("✅ Llama 3.1 70B downloaded successfully")
            else:
                error = process.stderr.read()
                raise RuntimeError(f"Failed to download model: {error}")
            
        except Exception as e:
            print(f"❌ Failed to download Llama model: {e}")
            raise
    
    async def _initialize_chromadb(self):
        """Initialize ChromaDB for RAG memory"""
        try:
            # Initialize ChromaDB client
            self.chroma_client = chromadb.PersistentClient(
                path=str(self.memory_dir / "chromadb"),
                settings=Settings(anonymized_telemetry=False)
            )
            
            # Get or create memory collection
            self.memory_collection = self.chroma_client.get_or_create_collection(
                name="seidra_memory",
                metadata={"description": "SEIDRA conversation memory and knowledge base"}
            )
            
            print("✅ ChromaDB initialized for RAG memory")
            
        except Exception as e:
            print(f"❌ Failed to initialize ChromaDB: {e}")
            raise
    
    async def _load_personas(self):
        """Load existing personas from disk"""
        try:
            for persona_file in self.personas_dir.glob("*.json"):
                with open(persona_file, 'r', encoding='utf-8') as f:
                    persona_data = json.load(f)
                    self.personas[persona_data["persona_id"]] = persona_data
            
            print(f"✅ Loaded {len(self.personas)} personas")
            
        except Exception as e:
            print(f"⚠️ Failed to load personas: {e}")
    
    async def create_persona(self,
                           name: str,
                           personality_type: str = "assistant",
                           description: str = "",
                           custom_prompt: str = "",
                           voice_model: Optional[str] = None,
                           avatar_config: Optional[Dict] = None,
                           nsfw_enabled: bool = False) -> Dict[str, Any]:
        """Create new AI persona"""
        
        try:
            persona_id = str(uuid.uuid4())
            
            # Build system prompt
            base_prompt = self.system_prompts.get(personality_type, self.system_prompts["assistant"])
            if custom_prompt:
                system_prompt = f"{base_prompt}\n\nAdditional instructions: {custom_prompt}"
            else:
                system_prompt = base_prompt
            
            persona_data = {
                "persona_id": persona_id,
                "name": name,
                "personality_type": personality_type,
                "description": description,
                "system_prompt": system_prompt,
                "voice_model": voice_model,
                "avatar_config": avatar_config or {},
                "nsfw_enabled": nsfw_enabled,
                "created_at": datetime.now().isoformat(),
                "conversation_count": 0,
                "memory_entries": 0,
                "preferences": {},
                "stats": {
                    "total_messages": 0,
                    "total_tokens": 0,
                    "last_active": None
                }
            }
            
            # Save persona
            persona_file = self.personas_dir / f"{persona_id}.json"
            with open(persona_file, 'w', encoding='utf-8') as f:
                json.dump(persona_data, f, indent=2, ensure_ascii=False)
            
            # Add to memory
            self.personas[persona_id] = persona_data
            
            print(f"✅ Created persona: {name} ({personality_type})")
            
            return persona_data
            
        except Exception as e:
            print(f"❌ Failed to create persona: {e}")
            raise
    
    async def chat_with_persona(self,
                              persona_id: str,
                              message: str,
                              conversation_id: Optional[str] = None,
                              include_memory: bool = True) -> Dict[str, Any]:
        """Chat with specific persona"""
        
        try:
            if persona_id not in self.personas:
                raise ValueError(f"Persona not found: {persona_id}")
            
            persona = self.personas[persona_id]
            
            # Create or get conversation
            if not conversation_id:
                conversation_id = str(uuid.uuid4())
            
            if conversation_id not in self.conversations:
                self.conversations[conversation_id] = {
                    "conversation_id": conversation_id,
                    "persona_id": persona_id,
                    "messages": [],
                    "created_at": datetime.now().isoformat(),
                    "last_active": datetime.now().isoformat()
                }
            
            conversation = self.conversations[conversation_id]
            
            # Retrieve relevant memories if enabled
            context_memories = []
            if include_memory and self.memory_collection:
                try:
                    # Query similar memories
                    memory_results = self.memory_collection.query(
                        query_texts=[message],
                        n_results=5,
                        where={"persona_id": persona_id}
                    )
                    
                    if memory_results["documents"]:
                        context_memories = memory_results["documents"][0]
                except Exception as e:
                    print(f"⚠️ Memory retrieval failed: {e}")
            
            # Build conversation context
            context_messages = []
            
            # Add system prompt
            context_messages.append({
                "role": "system",
                "content": persona["system_prompt"]
            })
            
            # Add relevant memories as context
            if context_memories:
                memory_context = "\n".join([f"- {memory}" for memory in context_memories[:3]])
                context_messages.append({
                    "role": "system", 
                    "content": f"Relevant memories from previous conversations:\n{memory_context}"
                })
            
            # Add recent conversation history (last 10 messages)
            recent_messages = conversation["messages"][-10:]
            context_messages.extend(recent_messages)
            
            # Add current user message
            user_message = {"role": "user", "content": message}
            context_messages.append(user_message)
            
            # Generate response using Ollama
            print(f"🤖 {persona['name']} is thinking...")
            
            response = await self._generate_ollama_response(context_messages)
            
            # Create assistant message
            assistant_message = {
                "role": "assistant",
                "content": response,
                "timestamp": datetime.now().isoformat()
            }
            
            # Update conversation
            conversation["messages"].extend([user_message, assistant_message])
            conversation["last_active"] = datetime.now().isoformat()
            
            # Store in memory for future retrieval
            if self.memory_collection:
                try:
                    memory_entry = f"User: {message}\n{persona['name']}: {response}"
                    self.memory_collection.add(
                        documents=[memory_entry],
                        metadatas=[{
                            "persona_id": persona_id,
                            "conversation_id": conversation_id,
                            "timestamp": datetime.now().isoformat()
                        }],
                        ids=[str(uuid.uuid4())]
                    )
                except Exception as e:
                    print(f"⚠️ Memory storage failed: {e}")
            
            # Update persona stats
            persona["stats"]["total_messages"] += 1
            persona["stats"]["last_active"] = datetime.now().isoformat()
            await self._save_persona(persona)
            
            return {
                "conversation_id": conversation_id,
                "persona_name": persona["name"],
                "user_message": message,
                "assistant_response": response,
                "timestamp": assistant_message["timestamp"],
                "context_memories_used": len(context_memories)
            }
            
        except Exception as e:
            print(f"❌ Chat failed: {e}")
            raise
    
    async def _generate_ollama_response(self, messages: List[Dict[str, str]]) -> str:
        """Generate response using Ollama API"""
        
        try:
            # Format messages for Ollama
            prompt = self._format_messages_for_ollama(messages)
            
            # Make request to Ollama
            response = requests.post(
                f"{self.ollama_config['base_url']}/api/generate",
                json={
                    "model": self.ollama_config["model_name"],
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": self.ollama_config["temperature"],
                        "top_p": self.ollama_config["top_p"],
                        "repeat_penalty": self.ollama_config["repeat_penalty"],
                        "num_ctx": self.ollama_config["context_length"]
                    }
                },
                timeout=self.ollama_config["timeout"]
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("response", "").strip()
            else:
                raise RuntimeError(f"Ollama API error: {response.status_code}")
            
        except Exception as e:
            print(f"❌ Ollama generation failed: {e}")
            return "I apologize, but I'm having trouble generating a response right now. Please try again."
    
    def _format_messages_for_ollama(self, messages: List[Dict[str, str]]) -> str:
        """Format conversation messages for Ollama prompt"""
        
        formatted_parts = []
        
        for message in messages:
            role = message["role"]
            content = message["content"]
            
            if role == "system":
                formatted_parts.append(f"<|system|>\n{content}\n")
            elif role == "user":
                formatted_parts.append(f"<|user|>\n{content}\n")
            elif role == "assistant":
                formatted_parts.append(f"<|assistant|>\n{content}\n")
        
        # Add assistant prompt
        formatted_parts.append("<|assistant|>\n")
        
        return "".join(formatted_parts)
    
    async def _save_persona(self, persona_data: Dict[str, Any]):
        """Save persona data to disk"""
        
        try:
            persona_file = self.personas_dir / f"{persona_data['persona_id']}.json"
            with open(persona_file, 'w', encoding='utf-8') as f:
                json.dump(persona_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Failed to save persona: {e}")
    
    async def get_personas(self) -> List[Dict[str, Any]]:
        """Get list of available personas"""
        return list(self.personas.values())
    
    async def get_conversation_history(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get conversation history"""
        return self.conversations.get(conversation_id)
    
    async def delete_persona(self, persona_id: str) -> bool:
        """Delete persona and associated data"""
        
        try:
            if persona_id in self.personas:
                # Delete persona file
                persona_file = self.personas_dir / f"{persona_id}.json"
                if persona_file.exists():
                    persona_file.unlink()
                
                # Remove from memory
                del self.personas[persona_id]
                
                # Clean up memory collection
                if self.memory_collection:
                    try:
                        # This would require implementing ChromaDB deletion by metadata
                        pass
                    except:
                        pass
                
                print(f"✅ Persona deleted: {persona_id}")
                return True
            
            return False
            
        except Exception as e:
            print(f"❌ Failed to delete persona: {e}")
            return False
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get Llama system status"""
        
        try:
            # Check Ollama service
            ollama_status = "offline"
            try:
                response = requests.get(f"{self.ollama_config['base_url']}/api/tags", timeout=5)
                if response.status_code == 200:
                    ollama_status = "online"
            except:
                pass
            
            # Get model info
            models_info = []
            if ollama_status == "online":
                try:
                    response = requests.get(f"{self.ollama_config['base_url']}/api/tags", timeout=10)
                    if response.status_code == 200:
                        models_info = response.json().get("models", [])
                except:
                    pass
            
            return {
                "ollama_service": ollama_status,
                "model_name": self.ollama_config["model_name"],
                "available_models": len(models_info),
                "loaded_personas": len(self.personas),
                "active_conversations": len(self.conversations),
                "memory_collection": "initialized" if self.memory_collection else "not_initialized",
                "base_url": self.ollama_config["base_url"]
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    async def cleanup(self):
        """Cleanup Llama resources"""
        
        # Save all conversations
        for conv_id, conversation in self.conversations.items():
            try:
                conv_file = self.memory_dir / f"conversation_{conv_id}.json"
                with open(conv_file, 'w', encoding='utf-8') as f:
                    json.dump(conversation, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"⚠️ Failed to save conversation {conv_id}: {e}")
        
        # Close ChromaDB client
        if self.chroma_client:
            try:
                # ChromaDB doesn't need explicit closing
                pass
            except:
                pass
        
        print("✅ Llama Local System cleaned up")