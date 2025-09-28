"""
SEIDRA FLUX.1-dev Local Generator
Local image generation with FLUX.1-dev optimized for RTX 3090
"""

import os
import torch
import asyncio
from typing import Dict, List, Optional, Any
from diffusers import FluxPipeline
from diffusers.models import FluxTransformer2DModel
from transformers import CLIPTextModel, CLIPTokenizer, T5EncoderModel, T5TokenizerFast
import numpy as np
from PIL import Image
import json
import uuid
from datetime import datetime
from pathlib import Path

class FluxLocalGenerator:
    """Local FLUX.1-dev generator optimized for RTX 3090"""
    
    def __init__(self):
        self.models_dir = Path("../models/flux1-dev")
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        self.loras_dir = Path("../models/loras")
        self.loras_dir.mkdir(parents=True, exist_ok=True)
        
        self.outputs_dir = Path("../data/outputs")
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        
        self.pipeline = None
        self.loaded_loras = {}
        
        # FLUX.1-dev configuration
        self.model_config = {
            "model_id": "black-forest-labs/FLUX.1-dev",
            "torch_dtype": torch.bfloat16,
            "variant": "fp16",
            "use_safetensors": True
        }
        
        # RTX 3090 optimizations
        self.rtx3090_config = {
            "enable_model_cpu_offload": True,
            "enable_sequential_cpu_offload": False,
            "enable_attention_slicing": True,
            "enable_xformers": True,
            "memory_efficient_attention": True,
            "max_batch_size": 2,  # Conservative for 24GB VRAM
            "guidance_scale": 3.5,  # FLUX optimal
            "num_inference_steps": 28  # FLUX optimal
        }
        
        # Style presets optimized for FLUX
        self.style_presets = {
            "photorealistic": {
                "prompt_prefix": "photorealistic, high quality, detailed, professional photography",
                "negative": "cartoon, anime, drawing, painting, sketch, low quality, blurry",
                "guidance_scale": 3.5,
                "steps": 28
            },
            "cinematic": {
                "prompt_prefix": "cinematic, dramatic lighting, film grain, professional cinematography",
                "negative": "amateur, low quality, blurry, overexposed",
                "guidance_scale": 4.0,
                "steps": 32
            },
            "artistic": {
                "prompt_prefix": "artistic, creative, masterpiece, fine art, detailed",
                "negative": "low quality, amateur, blurry, distorted",
                "guidance_scale": 4.5,
                "steps": 35
            },
            "anime": {
                "prompt_prefix": "anime style, detailed, high quality, vibrant colors",
                "negative": "realistic, photograph, low quality, blurry",
                "guidance_scale": 4.0,
                "steps": 30
            },
            "fantasy": {
                "prompt_prefix": "fantasy art, mystical, magical, ethereal, detailed fantasy illustration",
                "negative": "modern, contemporary, realistic photo, low quality",
                "guidance_scale": 4.5,
                "steps": 35
            },
            "cyberpunk": {
                "prompt_prefix": "cyberpunk, neon lights, futuristic, high tech, detailed sci-fi art",
                "negative": "medieval, fantasy, low tech, low quality",
                "guidance_scale": 4.0,
                "steps": 32
            }
        }
        
        # Content safety levels
        self.content_levels = {
            "safe": {
                "allowed_tags": ["sfw", "safe", "appropriate", "family-friendly"],
                "blocked_tags": ["nsfw", "nude", "explicit", "sexual", "adult"],
                "negative_suffix": ", nsfw, nude, explicit, sexual content"
            },
            "artistic": {
                "allowed_tags": ["artistic nude", "fine art", "tasteful"],
                "blocked_tags": ["explicit", "pornographic", "hardcore"],
                "negative_suffix": ", explicit sexual content, pornographic"
            },
            "mature": {
                "allowed_tags": ["mature", "suggestive", "sensual"],
                "blocked_tags": ["illegal", "extreme"],
                "negative_suffix": ", illegal content, extreme explicit content"
            }
        }
    
    async def initialize(self):
        """Initialize FLUX.1-dev pipeline locally"""
        print("🚀 Initializing FLUX.1-dev Local Generator...")
        
        try:
            # Check if model exists locally
            if not self._check_local_model():
                print("📥 FLUX.1-dev not found locally. Downloading...")
                await self._download_flux_model()
            
            # Load FLUX pipeline
            print("🔄 Loading FLUX.1-dev pipeline...")
            self.pipeline = FluxPipeline.from_pretrained(
                self.model_config["model_id"],
                torch_dtype=self.model_config["torch_dtype"],
                variant=self.model_config["variant"],
                use_safetensors=self.model_config["use_safetensors"],
                cache_dir=str(self.models_dir)
            )
            
            # Apply RTX 3090 optimizations
            await self._apply_rtx3090_optimizations()
            
            print("✅ FLUX.1-dev Local Generator initialized")
            
        except Exception as e:
            print(f"❌ Failed to initialize FLUX Local Generator: {e}")
            raise
    
    def _check_local_model(self) -> bool:
        """Check if FLUX model exists locally"""
        model_path = self.models_dir / "model_index.json"
        return model_path.exists()
    
    async def _download_flux_model(self):
        """Download FLUX.1-dev model locally"""
        try:
            from huggingface_hub import snapshot_download
            
            print("📦 Downloading FLUX.1-dev (~12GB)...")
            snapshot_download(
                repo_id=self.model_config["model_id"],
                cache_dir=str(self.models_dir),
                local_files_only=False,
                resume_download=True
            )
            print("✅ FLUX.1-dev downloaded successfully")
            
        except Exception as e:
            print(f"❌ Failed to download FLUX model: {e}")
            raise
    
    async def _apply_rtx3090_optimizations(self):
        """Apply RTX 3090 specific optimizations"""
        try:
            # Move to GPU
            if torch.cuda.is_available():
                self.pipeline = self.pipeline.to("cuda")
                print("✅ FLUX pipeline moved to CUDA")
            
            # Enable memory optimizations
            if self.rtx3090_config["enable_model_cpu_offload"]:
                self.pipeline.enable_model_cpu_offload()
                print("✅ Model CPU offload enabled")
            
            if self.rtx3090_config["enable_attention_slicing"]:
                self.pipeline.enable_attention_slicing(1)
                print("✅ Attention slicing enabled")
            
            # Enable xFormers if available
            if self.rtx3090_config["enable_xformers"]:
                try:
                    self.pipeline.enable_xformers_memory_efficient_attention()
                    print("✅ xFormers memory efficient attention enabled")
                except:
                    print("⚠️ xFormers not available, using default attention")
            
            # Set optimal compilation
            if hasattr(self.pipeline.transformer, 'to'):
                self.pipeline.transformer = torch.compile(
                    self.pipeline.transformer, 
                    mode="reduce-overhead", 
                    fullgraph=True
                )
                print("✅ FLUX transformer compiled for optimization")
            
        except Exception as e:
            print(f"⚠️ Some optimizations failed: {e}")
    
    async def generate_image(self,
                           prompt: str,
                           negative_prompt: str = "",
                           style: str = "photorealistic",
                           content_level: str = "safe",
                           width: int = 1024,
                           height: int = 1024,
                           num_inference_steps: Optional[int] = None,
                           guidance_scale: Optional[float] = None,
                           seed: Optional[int] = None,
                           lora_models: List[str] = None) -> Dict[str, Any]:
        """Generate image with FLUX.1-dev locally"""
        
        if not self.pipeline:
            await self.initialize()
        
        try:
            # Get style configuration
            style_config = self.style_presets.get(style, self.style_presets["photorealistic"])
            content_config = self.content_levels.get(content_level, self.content_levels["safe"])
            
            # Build final prompt
            final_prompt = f"{style_config['prompt_prefix']}, {prompt}"
            
            # Build negative prompt
            negative_parts = [
                style_config["negative"],
                content_config["negative_suffix"],
                negative_prompt
            ]
            final_negative = ", ".join(filter(None, negative_parts))
            
            # Set parameters
            steps = num_inference_steps or style_config["steps"]
            guidance = guidance_scale or style_config["guidance_scale"]
            
            # Load LoRA models if specified
            if lora_models:
                await self._load_lora_models(lora_models)
            
            # Set seed for reproducibility
            generator = torch.Generator(device="cuda" if torch.cuda.is_available() else "cpu")
            if seed:
                generator.manual_seed(seed)
            
            print(f"🎨 Generating with FLUX.1-dev: {style} style")
            print(f"📝 Prompt: {final_prompt[:100]}...")
            
            # Generate image
            with torch.cuda.amp.autocast(dtype=torch.bfloat16):
                result = self.pipeline(
                    prompt=final_prompt,
                    negative_prompt=final_negative,
                    width=width,
                    height=height,
                    num_inference_steps=steps,
                    guidance_scale=guidance,
                    generator=generator,
                    num_images_per_prompt=1
                )
            
            generated_image = result.images[0]
            
            # Save image
            image_id = str(uuid.uuid4())
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"flux_{style}_{image_id}_{timestamp}.png"
            output_path = self.outputs_dir / filename
            
            generated_image.save(output_path, quality=95, optimize=True)
            
            # Generate metadata
            metadata = {
                "image_id": image_id,
                "model": "FLUX.1-dev",
                "style": style,
                "content_level": content_level,
                "prompt": final_prompt,
                "negative_prompt": final_negative,
                "parameters": {
                    "width": width,
                    "height": height,
                    "num_inference_steps": steps,
                    "guidance_scale": guidance,
                    "seed": seed
                },
                "lora_models": lora_models or [],
                "created_at": datetime.now().isoformat(),
                "file_path": str(output_path),
                "file_size": output_path.stat().st_size
            }
            
            # Save metadata
            metadata_path = output_path.with_suffix('.json')
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            print(f"✅ Image generated: {filename}")
            
            return {
                "image_id": image_id,
                "image_path": str(output_path),
                "metadata": metadata,
                "preview_url": f"/api/images/{image_id}/preview"
            }
            
        except Exception as e:
            print(f"❌ FLUX generation failed: {e}")
            raise
    
    async def generate_batch(self,
                           prompts: List[str],
                           style: str = "photorealistic",
                           content_level: str = "safe",
                           **kwargs) -> List[Dict[str, Any]]:
        """Generate multiple images in batch"""
        
        batch_size = min(len(prompts), self.rtx3090_config["max_batch_size"])
        results = []
        
        for i in range(0, len(prompts), batch_size):
            batch_prompts = prompts[i:i + batch_size]
            
            for prompt in batch_prompts:
                try:
                    result = await self.generate_image(
                        prompt=prompt,
                        style=style,
                        content_level=content_level,
                        **kwargs
                    )
                    results.append(result)
                    
                    # Small delay to prevent overheating
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    print(f"❌ Batch generation failed for prompt: {prompt[:50]}... Error: {e}")
                    continue
        
        return results
    
    async def _load_lora_models(self, lora_models: List[str]):
        """Load LoRA models for style consistency"""
        
        try:
            # Unload previous LoRAs
            if hasattr(self.pipeline, 'unload_lora_weights'):
                self.pipeline.unload_lora_weights()
            
            # Load new LoRAs
            for lora_id in lora_models:
                lora_path = self.loras_dir / f"{lora_id}.safetensors"
                if lora_path.exists():
                    self.pipeline.load_lora_weights(str(lora_path))
                    print(f"✅ Loaded LoRA: {lora_id}")
                else:
                    print(f"⚠️ LoRA not found: {lora_id}")
            
            self.loaded_loras = {lora: True for lora in lora_models}
            
        except Exception as e:
            print(f"⚠️ Failed to load LoRA models: {e}")
    
    async def get_model_info(self) -> Dict[str, Any]:
        """Get FLUX model information and status"""
        
        gpu_info = {}
        if torch.cuda.is_available():
            gpu_info = {
                "gpu_name": torch.cuda.get_device_name(0),
                "gpu_memory_total": f"{torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f}GB",
                "gpu_memory_allocated": f"{torch.cuda.memory_allocated(0) / 1024**3:.1f}GB",
                "gpu_memory_cached": f"{torch.cuda.memory_reserved(0) / 1024**3:.1f}GB"
            }
        
        return {
            "model": "FLUX.1-dev",
            "status": "loaded" if self.pipeline else "not_loaded",
            "local_model_path": str(self.models_dir),
            "available_styles": list(self.style_presets.keys()),
            "content_levels": list(self.content_levels.keys()),
            "loaded_loras": list(self.loaded_loras.keys()),
            "rtx3090_optimizations": self.rtx3090_config,
            "gpu_info": gpu_info
        }
    
    async def benchmark_performance(self) -> Dict[str, Any]:
        """Benchmark FLUX performance on RTX 3090"""
        
        if not self.pipeline:
            await self.initialize()
        
        try:
            print("🏃 Running FLUX.1-dev performance benchmark...")
            
            test_prompt = "a beautiful landscape, photorealistic, high quality"
            
            # Benchmark different configurations
            benchmarks = {}
            
            for size_name, (width, height) in [
                ("512x512", (512, 512)),
                ("768x768", (768, 768)),
                ("1024x1024", (1024, 1024))
            ]:
                for steps in [20, 28, 35]:
                    config_name = f"{size_name}_{steps}steps"
                    
                    start_time = asyncio.get_event_loop().time()
                    
                    result = await self.generate_image(
                        prompt=test_prompt,
                        width=width,
                        height=height,
                        num_inference_steps=steps,
                        seed=42  # Fixed seed for consistency
                    )
                    
                    end_time = asyncio.get_event_loop().time()
                    generation_time = end_time - start_time
                    
                    benchmarks[config_name] = {
                        "generation_time": round(generation_time, 2),
                        "image_path": result["image_path"],
                        "vram_used": f"{torch.cuda.memory_allocated(0) / 1024**3:.1f}GB" if torch.cuda.is_available() else "N/A"
                    }
                    
                    print(f"✅ {config_name}: {generation_time:.2f}s")
                    
                    # Clear cache between tests
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    
                    await asyncio.sleep(1)
            
            return {
                "model": "FLUX.1-dev",
                "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
                "benchmarks": benchmarks,
                "optimal_config": "1024x1024_28steps",  # FLUX optimal
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ Benchmark failed: {e}")
            return {"error": str(e)}
    
    async def cleanup(self):
        """Cleanup FLUX resources"""
        
        if self.pipeline:
            del self.pipeline
            self.pipeline = None
        
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        self.loaded_loras.clear()
        print("✅ FLUX Local Generator cleaned up")