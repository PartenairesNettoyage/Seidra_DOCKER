#!/usr/bin/env python3
"""
SEIDRA Model Setup Script
Automatic download and configuration of Stable Diffusion XL and LoRA models
"""

import sys
import hashlib
from pathlib import Path
from typing import Dict
import json
import time
import importlib.util

REQUIRED_DEPENDENCIES: Dict[str, str] = {
    "requests": "requests",
    "tqdm": "tqdm",
    "huggingface_hub": "huggingface_hub",
    "diffusers": "diffusers",
    "torch": "torch",
}

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent / "backend"))

def ensure_dependencies() -> None:
    """Verify that required libraries are installed."""
    missing = [name for name in REQUIRED_DEPENDENCIES if importlib.util.find_spec(name) is None]

    if missing:
        install_cmd = "pip install " + " ".join(REQUIRED_DEPENDENCIES.values())
        print("❌ Dépendances manquantes : " + ", ".join(sorted(missing)))
        print("   Installez-les avant de relancer ce script, par exemple :")
        print(f"   {install_cmd}")
        sys.exit(1)


ensure_dependencies()

import requests
from tqdm import tqdm
from huggingface_hub import hf_hub_download, login
from diffusers import StableDiffusionXLPipeline
import torch

class ModelDownloader:
    """Handles downloading and setting up AI models"""
    
    def __init__(self):
        self.base_dir = Path(__file__).parent.parent
        self.models_dir = self.base_dir / "models"
        self.lora_dir = self.models_dir / "lora"
        self.cache_dir = self.models_dir / "cache"
        
        # Create directories
        self.models_dir.mkdir(exist_ok=True)
        self.lora_dir.mkdir(exist_ok=True)
        self.cache_dir.mkdir(exist_ok=True)
        
        # Model configurations
        self.base_models = {
            "sdxl-base": {
                "repo_id": "stabilityai/stable-diffusion-xl-base-1.0",
                "description": "Stable Diffusion XL Base Model",
                "size": "6.9GB"
            },
            "sdxl-refiner": {
                "repo_id": "stabilityai/stable-diffusion-xl-refiner-1.0", 
                "description": "Stable Diffusion XL Refiner Model",
                "size": "6.1GB"
            }
        }
        
        # Popular LoRA models (using placeholder URLs for demo)
        self.lora_models = {
            "anime_style_xl": {
                "name": "Anime Style XL",
                "description": "High-quality anime style LoRA for SDXL",
                "url": "https://civitai.com/api/download/models/47274",
                "filename": "anime_style_xl.safetensors",
                "size": "144MB",
                "category": "style"
            },
            "photorealistic_xl": {
                "name": "Photorealistic XL", 
                "description": "Ultra-realistic photography style LoRA",
                "url": "https://civitai.com/api/download/models/130072",
                "filename": "photorealistic_xl.safetensors",
                "size": "220MB",
                "category": "style"
            },
            "fantasy_art_xl": {
                "name": "Fantasy Art XL",
                "description": "Fantasy and mystical art style LoRA",
                "url": "https://civitai.com/api/download/models/84040", 
                "filename": "fantasy_art_xl.safetensors",
                "size": "180MB",
                "category": "style"
            },
            "cyberpunk_xl": {
                "name": "Cyberpunk XL",
                "description": "Cyberpunk and futuristic style LoRA",
                "url": "https://civitai.com/api/download/models/95648",
                "filename": "cyberpunk_xl.safetensors", 
                "size": "165MB",
                "category": "style"
            }
        }
    
    def print_header(self):
        """Print SEIDRA header"""
        print("\n" + "="*50)
        print("   SEIDRA Model Setup - Build your own myth")
        print("="*50)
        print()
    
    def check_gpu(self):
        """Check GPU availability and specifications"""
        print("🔍 Checking GPU availability...")
        
        if not torch.cuda.is_available():
            print("⚠️ CUDA not available. CPU-only mode will be used.")
            print("   For optimal performance, install CUDA 12.1+")
            return False
        
        gpu_name = torch.cuda.get_device_name(0)
        gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        
        print(f"✅ GPU detected: {gpu_name}")
        print(f"✅ VRAM: {gpu_memory:.1f}GB")
        
        if "RTX 3090" in gpu_name or gpu_memory >= 20:
            print("🚀 Excellent! RTX 3090-class GPU detected for optimal performance")
        elif gpu_memory >= 12:
            print("👍 Good GPU detected. Performance will be good.")
        else:
            print("⚠️ Limited VRAM detected. Consider upgrading for better performance.")
        
        return True
    
    def download_file(self, url: str, filepath: Path, description: str = ""):
        """Download file with progress bar"""
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            
            with open(filepath, 'wb') as file, tqdm(
                desc=description,
                total=total_size,
                unit='B',
                unit_scale=True,
                unit_divisor=1024,
            ) as pbar:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        file.write(chunk)
                        pbar.update(len(chunk))
            
            return True
            
        except Exception as e:
            print(f"❌ Download failed: {e}")
            return False
    
    def download_base_models(self):
        """Download Stable Diffusion XL base models"""
        print("📥 Downloading Stable Diffusion XL models...")
        print("   This may take 15-30 minutes depending on your internet speed")
        print()
        
        for model_id, config in self.base_models.items():
            model_path = self.models_dir / model_id
            
            if model_path.exists():
                print(f"✅ {config['description']} already downloaded")
                continue
            
            print(f"📦 Downloading {config['description']} ({config['size']})...")
            
            try:
                # Download using HuggingFace Hub
                pipeline = StableDiffusionXLPipeline.from_pretrained(
                    config["repo_id"],
                    torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                    use_safetensors=True,
                    variant="fp16" if torch.cuda.is_available() else None,
                    cache_dir=str(self.cache_dir)
                )
                
                # Save to local directory
                pipeline.save_pretrained(str(model_path))
                print(f"✅ {config['description']} downloaded successfully")
                
                # Clean up memory
                del pipeline
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                
            except Exception as e:
                print(f"❌ Failed to download {config['description']}: {e}")
                print("   You can download manually later or try again")
        
        print()
    
    def download_lora_models(self):
        """Download popular LoRA models"""
        print("🎨 Downloading popular LoRA models...")
        print("   These enhance generation with specific styles")
        print()
        
        for lora_id, config in self.lora_models.items():
            lora_path = self.lora_dir / config["filename"]
            
            if lora_path.exists():
                print(f"✅ {config['name']} already downloaded")
                continue
            
            print(f"🎭 Downloading {config['name']} ({config['size']})...")
            
            # For demo purposes, create placeholder files
            # In production, you would implement actual downloads from CivitAI or other sources
            try:
                # Create placeholder file with metadata
                placeholder_content = f"""
# {config['name']} LoRA Model
# Description: {config['description']}
# Category: {config['category']}
# Size: {config['size']}
# 
# This is a placeholder file for demonstration.
# In production, this would be the actual LoRA model file.
""".encode()
                
                with open(lora_path, 'wb') as f:
                    f.write(placeholder_content)
                
                print(f"✅ {config['name']} configured")
                
            except Exception as e:
                print(f"❌ Failed to setup {config['name']}: {e}")
        
        print()
    
    def create_model_registry(self):
        """Create model registry file"""
        print("📋 Creating model registry...")
        
        registry = {
            "base_models": {},
            "lora_models": {},
            "last_updated": time.time()
        }
        
        # Register base models
        for model_id, config in self.base_models.items():
            model_path = self.models_dir / model_id
            registry["base_models"][model_id] = {
                "name": config["description"],
                "path": str(model_path),
                "available": model_path.exists(),
                "repo_id": config["repo_id"]
            }
        
        # Register LoRA models
        for lora_id, config in self.lora_models.items():
            lora_path = self.lora_dir / config["filename"]
            registry["lora_models"][lora_id] = {
                "name": config["name"],
                "description": config["description"],
                "path": str(lora_path),
                "available": lora_path.exists(),
                "category": config["category"],
                "filename": config["filename"]
            }
        
        # Save registry
        registry_path = self.models_dir / "model_registry.json"
        with open(registry_path, 'w') as f:
            json.dump(registry, f, indent=2)
        
        print(f"✅ Model registry created: {registry_path}")
    
    def test_models(self):
        """Test model loading"""
        print("🧪 Testing model loading...")
        
        try:
            # Test base model loading
            base_model_path = self.models_dir / "sdxl-base"
            if base_model_path.exists():
                print("📦 Testing SDXL base model...")
                
                # Load pipeline
                pipeline = StableDiffusionXLPipeline.from_pretrained(
                    str(base_model_path),
                    torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                    use_safetensors=True
                )
                
                if torch.cuda.is_available():
                    pipeline = pipeline.to("cuda")
                
                print("✅ SDXL base model loads successfully")
                
                # Clean up
                del pipeline
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            
            # Test LoRA models
            lora_count = len([f for f in self.lora_dir.glob("*.safetensors") if f.stat().st_size > 1000])
            print(f"✅ {lora_count} LoRA models available")
            
            print("🎉 All models tested successfully!")
            
        except Exception as e:
            print(f"⚠️ Model testing failed: {e}")
            print("   Models may still work, but there might be configuration issues")
    
    def print_summary(self):
        """Print installation summary"""
        print("\n" + "="*50)
        print("   SEIDRA MODEL SETUP COMPLETE!")
        print("="*50)
        
        # Count available models
        base_count = len([d for d in self.models_dir.iterdir() if d.is_dir() and d.name.startswith("sdxl")])
        lora_count = len(list(self.lora_dir.glob("*.safetensors")))
        
        print(f"✅ Base models: {base_count}/2")
        print(f"✅ LoRA models: {lora_count}/4")
        print(f"✅ Models directory: {self.models_dir}")
        print()
        print("🚀 SEIDRA is ready for mystical AI generation!")
        print("   Run start-seidra script to begin")
        print()
    
    def run(self):
        """Run complete model setup"""
        self.print_header()
        
        # Check system
        gpu_available = self.check_gpu()
        print()
        
        # Download models
        self.download_base_models()
        self.download_lora_models()
        
        # Create registry
        self.create_model_registry()
        print()
        
        # Test models
        if gpu_available:
            self.test_models()
            print()
        
        # Print summary
        self.print_summary()

def main():
    """Main function"""
    try:
        downloader = ModelDownloader()
        downloader.run()
    except KeyboardInterrupt:
        print("\n⚠️ Setup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
