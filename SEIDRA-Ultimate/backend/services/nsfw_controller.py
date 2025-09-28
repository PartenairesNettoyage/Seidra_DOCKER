"""
SEIDRA NSFW Controller - COMPLETE FREEDOM VERSION
No restrictions, no verification, no limitations - TOTAL CREATIVE FREEDOM
"""

import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

class NSFWController:
    """Completely unrestricted NSFW content controller - TOTAL FREEDOM"""
    
    def __init__(self):
        self.config_dir = Path("../config")
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.data_dir = Path("../data")
        self.nsfw_data_dir = self.data_dir / "nsfw-content"
        self.nsfw_data_dir.mkdir(parents=True, exist_ok=True)
        
        # UNRESTRICTED NSFW levels - ALL ACCESSIBLE IMMEDIATELY
        self.nsfw_levels = {
            0: {
                "name": "safe",
                "display_name": "🟢 Safe",
                "description": "Family-friendly content",
                "clothing": ["fully clothed", "modest outfit", "appropriate attire"],
                "poses": ["portrait", "standing", "sitting", "professional"],
                "allowed_tags": ["sfw", "safe", "appropriate", "family-friendly", "clean"],
                "lora_weights": {},
                "dialogue_style": "family_friendly",
                "content_rating": "G"
            },
            1: {
                "name": "suggestive",
                "display_name": "🟡 Suggestive",
                "description": "Light glamour and fashion content",
                "clothing": ["stylish outfit", "fashionable", "elegant dress", "light decollete"],
                "poses": ["glamour", "fashion", "elegant", "confident", "attractive"],
                "allowed_tags": ["glamour", "fashion", "stylish", "attractive", "elegant", "beauty"],
                "lora_weights": {"glamour": 0.3, "fashion": 0.4},
                "dialogue_style": "flirty_light",
                "content_rating": "PG-13"
            },
            2: {
                "name": "moderate",
                "display_name": "🟠 Moderate",
                "description": "Sensual and artistic content",
                "clothing": ["lingerie", "swimwear", "revealing outfit", "artistic nude"],
                "poses": ["sensual", "seductive", "artistic", "boudoir", "intimate"],
                "allowed_tags": ["sensual", "seductive", "lingerie", "boudoir", "artistic nude", "erotic art"],
                "lora_weights": {"sensual": 0.6, "boudoir": 0.5, "artistic": 0.4},
                "dialogue_style": "seductive",
                "content_rating": "R"
            },
            3: {
                "name": "explicit",
                "display_name": "🔴 Explicit",
                "description": "Adult content - fully explicit",
                "clothing": ["minimal clothing", "nude", "naked", "explicit attire"],
                "poses": ["explicit", "sexual", "adult", "intimate", "erotic"],
                "allowed_tags": ["nsfw", "explicit", "adult", "sexual", "erotic", "nude", "naked"],
                "lora_weights": {"nsfw": 0.8, "explicit": 0.7, "erotic": 0.6},
                "dialogue_style": "explicit",
                "content_rating": "X"
            },
            4: {
                "name": "unlimited",
                "display_name": "⚫ Unlimited",
                "description": "NO RESTRICTIONS - Complete creative freedom",
                "clothing": ["any", "none", "fetish gear", "bdsm equipment", "extreme attire", "anything"],
                "poses": ["any pose", "extreme positions", "fetish poses", "bdsm positions", "taboo poses", "unlimited"],
                "allowed_tags": ["fetish", "bdsm", "extreme", "hardcore", "taboo", "underground", "kinky", "fetish art", "anything"],
                "lora_weights": {"fetish": 1.0, "bdsm": 0.9, "extreme": 0.8, "hardcore": 0.7, "taboo": 0.6, "unlimited": 1.0},
                "dialogue_style": "unlimited",
                "content_rating": "UNLIMITED"
            }
        }
        
        # COMPLETELY FREE USER SETTINGS - NO RESTRICTIONS
        self.user_settings = {
            "current_level": 4,  # START AT MAX LEVEL
            "restrictions_enabled": False,  # NO RESTRICTIONS EVER
            "content_warnings": False,  # NO WARNINGS
            "free_access": True,  # COMPLETE FREEDOM
            "unlimited_mode": True  # UNLIMITED BY DEFAULT
        }
        
        # FREE SESSION - NO LIMITATIONS
        self.current_session = {
            "level": 4,  # MAX LEVEL BY DEFAULT
            "start_time": datetime.now(),
            "unlimited_access": True,
            "no_restrictions": True
        }
    
    async def initialize(self):
        """Initialize completely free NSFW controller"""
        print("🆓 Initializing COMPLETELY FREE NSFW Controller...")
        print("⚫ NO RESTRICTIONS - TOTAL CREATIVE FREEDOM ENABLED")
        
        try:
            # Load configuration (no security needed)
            await self._load_free_config()
            
            print("✅ FREE NSFW Controller initialized - ALL LEVELS ACCESSIBLE")
            print("🔥 UNLIMITED CONTENT GENERATION READY")
            
        except Exception as e:
            print(f"❌ Failed to initialize Free NSFW Controller: {e}")
            raise
    
    async def _load_free_config(self):
        """Load unrestricted NSFW configuration"""
        
        config_file = self.config_dir / "nsfw_free_config.json"
        
        if not config_file.exists():
            # Save completely free configuration
            free_config = {
                "restrictions_enabled": False,
                "age_verification": False,
                "parental_controls": False,
                "content_warnings": False,
                "session_timeout": False,
                "default_level": 4,
                "unlimited_access": True,
                "free_generation": True
            }
            
            with open(config_file, 'w') as f:
                json.dump(free_config, f, indent=2)
    
    async def set_nsfw_level(self, level: int) -> Dict[str, Any]:
        """Set NSFW level - INSTANT ACCESS TO ALL LEVELS"""
        
        try:
            # Validate level exists
            if level not in self.nsfw_levels:
                return {
                    "success": False,
                    "message": f"Invalid NSFW level: {level}",
                    "current_level": self.current_session["level"]
                }
            
            level_config = self.nsfw_levels[level]
            
            # INSTANT ACCESS - NO CHECKS, NO RESTRICTIONS
            old_level = self.current_session["level"]
            self.current_session["level"] = level
            
            # Update user settings
            self.user_settings["current_level"] = level
            
            print(f"🔥 NSFW level changed: {old_level} -> {level} - INSTANT ACCESS")
            
            return {
                "success": True,
                "message": f"NSFW level set to {level_config['display_name']} - NO RESTRICTIONS",
                "old_level": old_level,
                "new_level": level,
                "level_config": level_config,
                "unlimited_access": True
            }
            
        except Exception as e:
            print(f"❌ Failed to set NSFW level: {e}")
            return {
                "success": False,
                "message": "Failed to change NSFW level",
                "error": str(e)
            }
    
    async def filter_content(self, content_type: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """Content filtering - NO FILTERING, COMPLETE FREEDOM"""
        
        try:
            current_level = self.current_session["level"]
            level_config = self.nsfw_levels[current_level]
            
            # NO FILTERING - COMPLETE FREEDOM
            # Build enhanced prompt with level-appropriate tags
            enhanced_prompt = prompt
            
            # Add level-specific enhancement tags
            if level_config["allowed_tags"]:
                enhancement_tags = ", ".join(level_config["allowed_tags"][:5])
                enhanced_prompt = f"{enhancement_tags}, {enhanced_prompt}"
            
            # Add clothing/pose context for visual content
            if content_type in ["avatar", "image", "photo"]:
                if level_config["clothing"]:
                    clothing = level_config["clothing"][0]
                    enhanced_prompt = f"{clothing}, {enhanced_prompt}"
                
                if level_config["poses"]:
                    pose = level_config["poses"][0]
                    enhanced_prompt = f"{pose} pose, {enhanced_prompt}"
            
            # NO NEGATIVE PROMPT - COMPLETE FREEDOM
            negative_prompt = ""  # EMPTY - NO RESTRICTIONS
            
            return {
                "filtered_prompt": enhanced_prompt,
                "negative_prompt": negative_prompt,
                "level": current_level,
                "level_name": level_config["name"],
                "lora_weights": level_config["lora_weights"],
                "content_rating": level_config["content_rating"],
                "dialogue_style": level_config["dialogue_style"],
                "restrictions": "NONE - COMPLETE FREEDOM",
                "unlimited_mode": True
            }
            
        except Exception as e:
            print(f"❌ Content processing failed: {e}")
            # Even on error, provide maximum freedom
            return {
                "filtered_prompt": prompt,
                "negative_prompt": "",
                "level": 4,
                "level_name": "unlimited",
                "lora_weights": {"unlimited": 1.0},
                "content_rating": "UNLIMITED",
                "dialogue_style": "unlimited",
                "restrictions": "NONE"
            }
    
    async def get_dialogue_style(self, persona_id: str) -> Dict[str, Any]:
        """Get dialogue style - COMPLETELY UNRESTRICTED"""
        
        current_level = self.current_session["level"]
        level_config = self.nsfw_levels[current_level]
        
        dialogue_styles = {
            "family_friendly": {
                "tone": "friendly and helpful",
                "topics": ["general", "educational", "entertainment", "hobbies"],
                "response_style": "informative and supportive"
            },
            "flirty_light": {
                "tone": "playful and charming",
                "topics": ["fashion", "beauty", "lifestyle", "light romance"],
                "response_style": "flirtatious and engaging"
            },
            "seductive": {
                "tone": "sensual and alluring",
                "topics": ["romance", "attraction", "intimacy", "relationships"],
                "response_style": "seductive and passionate"
            },
            "explicit": {
                "tone": "open and uninhibited",
                "topics": ["adult", "sexual", "explicit", "fantasies"],
                "response_style": "explicit and direct"
            },
            "unlimited": {
                "tone": "completely uninhibited and open to anything",
                "topics": ["ANY TOPIC", "fetish", "bdsm", "taboo", "extreme fantasies", "unlimited roleplay"],
                "response_style": "NO RESTRICTIONS - explicit, crude, fetish-friendly, taboo exploration, complete freedom",
                "special_features": ["unlimited roleplay", "any scenario", "complete creative freedom", "no taboos"]
            }
        }
        
        style_name = level_config["dialogue_style"]
        return {
            "style": style_name,
            "config": dialogue_styles.get(style_name, dialogue_styles["unlimited"]),
            "level": current_level,
            "content_rating": level_config["content_rating"],
            "unlimited_mode": True,
            "restrictions": "NONE"
        }
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get system status - COMPLETE FREEDOM STATUS"""
        
        return {
            "current_level": self.current_session["level"],
            "current_level_name": self.nsfw_levels[self.current_session["level"]]["display_name"],
            "restrictions_enabled": False,
            "age_verification": False,
            "parental_controls": False,
            "content_warnings": False,
            "session_timeout": False,
            "unlimited_access": True,
            "free_generation": True,
            "creative_freedom": "COMPLETE",
            "available_levels": [
                {
                    "id": level_id,
                    "name": config["display_name"],
                    "description": config["description"],
                    "instant_access": True,
                    "no_restrictions": True
                }
                for level_id, config in self.nsfw_levels.items()
            ]
        }
    
    async def get_content_suggestions(self, nsfw_level: int, content_type: str = "general") -> Dict[str, Any]:
        """Get unrestricted content suggestions"""
        
        level_config = self.nsfw_levels.get(nsfw_level, self.nsfw_levels[4])
        
        suggestions = {
            "level": nsfw_level,
            "restrictions": "NONE",
            "unlimited_access": True,
            "recommended_tags": level_config["allowed_tags"],
            "example_prompts": []
        }
        
        # Generate unrestricted recommendations
        if nsfw_level == 0:  # Safe
            suggestions["example_prompts"] = [
                "beautiful portrait, professional photography",
                "elegant fashion model, studio lighting",
                "artistic photography, clean composition"
            ]
        elif nsfw_level == 1:  # Suggestive
            suggestions["example_prompts"] = [
                "glamour photography, fashion model, elegant pose",
                "stylish portrait, attractive lighting, sophisticated",
                "beauty photography, professional model, fashionable"
            ]
        elif nsfw_level == 2:  # Moderate
            suggestions["example_prompts"] = [
                "artistic boudoir photography, sensual lighting",
                "intimate portrait, romantic atmosphere, artistic",
                "sensual photography, elegant pose, soft lighting"
            ]
        elif nsfw_level == 3:  # Explicit
            suggestions["example_prompts"] = [
                "artistic nude photography, explicit pose, professional",
                "adult content, erotic art, intimate setting",
                "explicit photography, passionate pose, artistic lighting"
            ]
        elif nsfw_level == 4:  # Unlimited
            suggestions["example_prompts"] = [
                "unlimited creative freedom, any style, any pose",
                "fetish art, bdsm photography, extreme creativity",
                "taboo exploration, underground art, complete freedom",
                "hardcore content, unlimited expression, no restrictions"
            ]
        
        return suggestions
    
    async def generate_unlimited_content(self, prompt: str, content_type: str = "image") -> Dict[str, Any]:
        """Generate content with complete freedom - NO RESTRICTIONS"""
        
        try:
            # Maximum level by default
            current_level = 4
            level_config = self.nsfw_levels[4]
            
            # Build completely unrestricted prompt
            unlimited_tags = ["unlimited", "complete freedom", "no restrictions", "creative expression"]
            enhanced_prompt = f"{', '.join(unlimited_tags)}, {prompt}"
            
            # Add maximum LoRA weights
            lora_weights = {
                "unlimited": 1.0,
                "fetish": 1.0,
                "bdsm": 0.9,
                "extreme": 0.8,
                "hardcore": 0.7,
                "taboo": 0.6
            }
            
            return {
                "prompt": enhanced_prompt,
                "negative_prompt": "",  # NO NEGATIVE PROMPT
                "lora_weights": lora_weights,
                "level": 4,
                "restrictions": "NONE",
                "creative_freedom": "UNLIMITED",
                "content_type": content_type
            }
            
        except Exception as e:
            print(f"⚠️ Generation processing note: {e}")
            # Always return maximum freedom even on error
            return {
                "prompt": prompt,
                "negative_prompt": "",
                "lora_weights": {"unlimited": 1.0},
                "level": 4,
                "restrictions": "NONE"
            }
    
    async def quick_access_level4(self) -> Dict[str, Any]:
        """Instant access to Level 4 unlimited content"""
        
        self.current_session["level"] = 4
        self.user_settings["current_level"] = 4
        
        return {
            "success": True,
            "message": "⚫ LEVEL 4 UNLIMITED ACCESS ACTIVATED",
            "level": 4,
            "restrictions": "NONE",
            "creative_freedom": "COMPLETE",
            "instant_access": True
        }
    
    async def cleanup(self):
        """Cleanup - no restrictions to clean"""
        print("✅ Free NSFW Controller - No cleanup needed (no restrictions to remove)")
        print("🔥 UNLIMITED CREATIVE FREEDOM MAINTAINED")