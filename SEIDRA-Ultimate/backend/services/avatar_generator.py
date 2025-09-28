"""
SEIDRA Avatar Generator
Full-body realistic avatar creation with LoRA styles
"""

import os
import torch
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from diffusers import StableDiffusionXLPipeline, StableDiffusionXLImg2ImgPipeline
from diffusers.loaders import LoraLoaderMixin
import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from pathlib import Path
import json
import uuid
from datetime import datetime

class AvatarGenerator:
    """Advanced avatar generation with full-body support and style consistency"""
    
    def __init__(self):
        self.models_dir = Path("../models")
        self.avatar_loras_dir = self.models_dir / "avatar-loras"
        self.avatar_loras_dir.mkdir(parents=True, exist_ok=True)
        
        self.pipeline = None
        self.img2img_pipeline = None
        
        # Avatar presets
        self.avatar_presets = {
            "realistic_female": {
                "base_prompt": "beautiful woman, photorealistic, detailed face, perfect skin, natural lighting",
                "negative": "cartoon, anime, drawing, painting, fake, artificial",
                "lora": "photorealistic_xl",
                "style": "photorealistic"
            },
            "realistic_male": {
                "base_prompt": "handsome man, photorealistic, detailed face, strong jawline, natural lighting",
                "negative": "cartoon, anime, drawing, painting, fake, artificial",
                "lora": "photorealistic_xl",
                "style": "photorealistic"
            },
            "anime_female": {
                "base_prompt": "beautiful anime girl, detailed eyes, perfect face, anime style, high quality",
                "negative": "realistic, photograph, 3d render, blurry, low quality",
                "lora": "anime_style_xl",
                "style": "anime"
            },
            "anime_male": {
                "base_prompt": "handsome anime boy, detailed eyes, perfect face, anime style, high quality",
                "negative": "realistic, photograph, 3d render, blurry, low quality",
                "lora": "anime_style_xl",
                "style": "anime"
            },
            "fantasy_female": {
                "base_prompt": "mystical fantasy woman, ethereal beauty, magical aura, detailed fantasy art",
                "negative": "modern, contemporary, realistic photo, low quality",
                "lora": "fantasy_art_xl",
                "style": "fantasy"
            },
            "cyberpunk_female": {
                "base_prompt": "cyberpunk woman, neon lights, futuristic, detailed cyberpunk art, high tech",
                "negative": "medieval, fantasy, low tech, blurry, low quality",
                "lora": "cyberpunk_xl",
                "style": "cyberpunk"
            }
        }
        
        # Body poses and compositions
        self.body_poses = {
            "portrait": "head and shoulders, portrait, upper body",
            "half_body": "half body, waist up, detailed torso",
            "full_body": "full body, standing, complete figure, head to toe",
            "sitting": "sitting pose, relaxed position, full body visible",
            "action": "dynamic pose, action shot, full body in motion",
            "elegant": "elegant pose, graceful posture, refined stance"
        }
        
        # Safe and NSFW content levels
        self.content_levels = {
            "safe": {
                "clothing": "fully clothed, modest outfit, appropriate attire",
                "negative": "nude, naked, nsfw, explicit, sexual, inappropriate"
            },
            "suggestive": {
                "clothing": "stylish outfit, fashionable clothing, attractive attire",
                "negative": "nude, naked, explicit sexual content, inappropriate"
            },
            "artistic_nude": {
                "clothing": "artistic nude, tasteful, artistic expression, fine art",
                "negative": "explicit sexual content, pornographic, inappropriate"
            },
            "nsfw": {
                "clothing": "minimal clothing, revealing outfit, sensual attire",
                "negative": "extreme explicit content, illegal content"
            }
        }
    
    async def initialize(self):
        """Initialize avatar generation pipelines"""
        print("🎭 Initializing Avatar Generator...")
        
        try:
            # Load main pipeline
            self.pipeline = StableDiffusionXLPipeline.from_pretrained(
                "stabilityai/stable-diffusion-xl-base-1.0",
                torch_dtype=torch.float16,
                use_safetensors=True,
                variant="fp16"
            )
            
            # Load img2img pipeline for refinement
            self.img2img_pipeline = StableDiffusionXLImg2ImgPipeline.from_pretrained(
                "stabilityai/stable-diffusion-xl-refiner-1.0",
                torch_dtype=torch.float16,
                use_safetensors=True,
                variant="fp16"
            )
            
            # Optimize for RTX 3090
            if torch.cuda.is_available():
                self.pipeline = self.pipeline.to("cuda")
                self.img2img_pipeline = self.img2img_pipeline.to("cuda")
                
                # Enable optimizations
                self.pipeline.enable_xformers_memory_efficient_attention()
                self.img2img_pipeline.enable_xformers_memory_efficient_attention()
                
                self.pipeline.enable_model_cpu_offload()
                self.img2img_pipeline.enable_model_cpu_offload()
            
            print("✅ Avatar Generator initialized")
            
        except Exception as e:
            print(f"❌ Failed to initialize Avatar Generator: {e}")
            raise
    
    async def generate_avatar(self,
                            preset: str = "realistic_female",
                            pose: str = "portrait",
                            content_level: str = "safe",
                            custom_prompt: str = "",
                            custom_negative: str = "",
                            consistency_seed: Optional[int] = None,
                            width: int = 1024,
                            height: int = 1024,
                            num_inference_steps: int = 30,
                            guidance_scale: float = 7.5) -> Dict[str, Any]:
        """Generate avatar with specified parameters"""
        
        if not self.pipeline:
            await self.initialize()
        
        try:
            # Get preset configuration
            if preset not in self.avatar_presets:
                raise ValueError(f"Unknown preset: {preset}")
            
            preset_config = self.avatar_presets[preset]
            pose_config = self.body_poses.get(pose, self.body_poses["portrait"])
            content_config = self.content_levels.get(content_level, self.content_levels["safe"])
            
            # Build prompt
            prompt_parts = [
                preset_config["base_prompt"],
                pose_config,
                content_config["clothing"]
            ]
            
            if custom_prompt:
                prompt_parts.append(custom_prompt)
            
            final_prompt = ", ".join(prompt_parts)
            
            # Build negative prompt
            negative_parts = [
                preset_config["negative"],
                content_config["negative"]
            ]
            
            if custom_negative:
                negative_parts.append(custom_negative)
            
            final_negative = ", ".join(negative_parts)
            
            # Load LoRA if specified
            lora_model = preset_config.get("lora")
            if lora_model:
                await self._load_lora_weights([lora_model])
            
            # Generate base image
            print(f"🎨 Generating {preset} avatar with {pose} pose...")
            
            generator = torch.Generator(device="cuda" if torch.cuda.is_available() else "cpu")
            if consistency_seed:
                generator.manual_seed(consistency_seed)
            
            # Base generation
            with torch.cuda.amp.autocast():
                result = self.pipeline(
                    prompt=final_prompt,
                    negative_prompt=final_negative,
                    width=width,
                    height=height,
                    num_inference_steps=num_inference_steps,
                    guidance_scale=guidance_scale,
                    generator=generator,
                    num_images_per_prompt=1
                )
            
            base_image = result.images[0]
            
            # Refine with img2img pipeline
            print("✨ Refining avatar quality...")
            
            with torch.cuda.amp.autocast():
                refined_result = self.img2img_pipeline(
                    prompt=final_prompt,
                    negative_prompt=final_negative,
                    image=base_image,
                    strength=0.3,  # Light refinement
                    num_inference_steps=20,
                    guidance_scale=guidance_scale,
                    generator=generator
                )
            
            final_image = refined_result.images[0]
            
            # Post-process image
            enhanced_image = await self._enhance_avatar(final_image, preset_config["style"])
            
            # Save avatar
            avatar_id = str(uuid.uuid4())
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"avatar_{preset}_{pose}_{avatar_id}_{timestamp}.png"
            
            output_dir = Path("../data/avatars")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / filename
            
            enhanced_image.save(output_path, quality=95)
            
            # Generate metadata
            metadata = {
                "avatar_id": avatar_id,
                "preset": preset,
                "pose": pose,
                "content_level": content_level,
                "style": preset_config["style"],
                "prompt": final_prompt,
                "negative_prompt": final_negative,
                "consistency_seed": consistency_seed,
                "parameters": {
                    "width": width,
                    "height": height,
                    "num_inference_steps": num_inference_steps,
                    "guidance_scale": guidance_scale
                },
                "created_at": datetime.now().isoformat(),
                "file_path": str(output_path)
            }
            
            # Save metadata
            metadata_path = output_path.with_suffix('.json')
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            print(f"✅ Avatar generated: {filename}")
            
            return {
                "avatar_id": avatar_id,
                "image_path": str(output_path),
                "metadata": metadata,
                "preview_url": f"/api/avatars/{avatar_id}/preview"
            }
            
        except Exception as e:
            print(f"❌ Avatar generation failed: {e}")
            raise
    
    async def generate_avatar_series(self,
                                   preset: str,
                                   poses: List[str],
                                   content_level: str = "safe",
                                   consistency_seed: Optional[int] = None,
                                   variations: int = 3) -> List[Dict[str, Any]]:
        """Generate series of consistent avatars with different poses"""
        
        if not consistency_seed:
            consistency_seed = torch.randint(0, 2**32, (1,)).item()
        
        avatars = []
        
        for pose in poses:
            for i in range(variations):
                # Use consistent seed with slight variation
                seed = consistency_seed + i
                
                avatar = await self.generate_avatar(
                    preset=preset,
                    pose=pose,
                    content_level=content_level,
                    consistency_seed=seed
                )
                
                avatars.append(avatar)
        
        return avatars
    
    async def _enhance_avatar(self, image: Image.Image, style: str) -> Image.Image:
        """Enhance avatar image quality based on style"""
        
        try:
            # Convert to numpy for processing
            img_array = np.array(image)
            
            # Style-specific enhancements
            if style == "photorealistic":
                # Enhance realism
                enhanced = Image.fromarray(img_array)
                enhanced = enhanced.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))
                
                # Adjust contrast and saturation
                enhancer = ImageEnhance.Contrast(enhanced)
                enhanced = enhancer.enhance(1.1)
                
                enhancer = ImageEnhance.Color(enhanced)
                enhanced = enhancer.enhance(1.05)
                
            elif style == "anime":
                # Enhance anime style
                enhanced = Image.fromarray(img_array)
                enhanced = enhanced.filter(ImageFilter.UnsharpMask(radius=0.5, percent=120, threshold=2))
                
                # Increase saturation for anime look
                enhancer = ImageEnhance.Color(enhanced)
                enhanced = enhancer.enhance(1.2)
                
            elif style == "fantasy":
                # Enhance fantasy/mystical look
                enhanced = Image.fromarray(img_array)
                
                # Add slight glow effect
                enhancer = ImageEnhance.Brightness(enhanced)
                enhanced = enhancer.enhance(1.05)
                
                enhancer = ImageEnhance.Color(enhanced)
                enhanced = enhancer.enhance(1.15)
                
            else:
                # Default enhancement
                enhanced = Image.fromarray(img_array)
                enhanced = enhanced.filter(ImageFilter.UnsharpMask(radius=1, percent=130, threshold=3))
            
            return enhanced
            
        except Exception as e:
            print(f"⚠️ Avatar enhancement failed: {e}")
            return image
    
    async def _load_lora_weights(self, lora_models: List[str]):
        """Load LoRA weights for avatar generation"""
        
        try:
            # Unload previous LoRA weights
            self.pipeline.unload_lora_weights()
            
            # Load new LoRA weights
            for lora_id in lora_models:
                lora_path = self.avatar_loras_dir / f"{lora_id}.safetensors"
                if lora_path.exists():
                    self.pipeline.load_lora_weights(str(lora_path))
                    print(f"✅ Loaded LoRA: {lora_id}")
                else:
                    print(f"⚠️ LoRA not found: {lora_id}")
            
        except Exception as e:
            print(f"⚠️ Failed to load LoRA weights: {e}")
    
    async def get_avatar_presets(self) -> Dict[str, Any]:
        """Get available avatar presets"""
        
        return {
            "presets": list(self.avatar_presets.keys()),
            "poses": list(self.body_poses.keys()),
            "content_levels": list(self.content_levels.keys()),
            "styles": list(set(preset["style"] for preset in self.avatar_presets.values()))
        }
    
    async def cleanup(self):
        """Cleanup avatar generator resources"""
        
        if self.pipeline:
            del self.pipeline
            self.pipeline = None
        
        if self.img2img_pipeline:
            del self.img2img_pipeline
            self.img2img_pipeline = None
        
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        print("✅ Avatar Generator cleaned up")