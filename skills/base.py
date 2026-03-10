"""
skills/base.py — Skill Base Classes for Go2 Robot

Provides SkillLoader that reads skill definitions from Markdown files.
"""

from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable
from pathlib import Path
import re
import logging

logger = logging.getLogger("go2-skills")


@dataclass
class SkillResult:
    """Result of a skill execution."""
    success: bool
    message: str
    data: Optional[dict] = None
    audio_response: Optional[str] = None


@dataclass
class Skill:
    """
    A skill loaded from a Markdown file.
    
    Attributes:
        name: Skill identifier (from frontmatter)
        description: Short description for LLM (from frontmatter)
        content: Full markdown content with instructions
        path: Path to the source .md file
    """
    name: str
    description: str
    content: str
    path: Optional[Path] = None
    
    def to_tool_schema(self) -> dict:
        """Convert to OpenAI function calling schema for load_skill tool."""
        return {
            "type": "function",
            "function": {
                "name": f"use_{self.name}",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        }


class SkillLoader:
    """
    Loads skills from Markdown files in a directory.
    
    Markdown format:
    ```markdown
    ---
    name: skill-name
    description: Short description for LLM
    ---
    
    # Skill Title
    
    ## Overview
    ...
    
    ## Instructions
    ...
    ```
    """
    
    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = Path(skills_dir)
        self._skills: dict[str, Skill] = {}
    
    def load_all(self) -> dict[str, Skill]:
        """Load all skill markdown files from the skills directory."""
        if not self.skills_dir.exists():
            logger.warning(f"Skills directory not found: {self.skills_dir}")
            return {}
        
        for md_file in self.skills_dir.glob("*.md"):
            try:
                skill = self._load_file(md_file)
                if skill:
                    self._skills[skill.name] = skill
                    logger.info(f"Loaded skill: {skill.name} from {md_file.name}")
            except Exception as e:
                logger.error(f"Error loading skill from {md_file}: {e}")
        
        return self._skills
    
    def _load_file(self, path: Path) -> Optional[Skill]:
        """Parse a single skill markdown file."""
        content = path.read_text(encoding="utf-8")
        
        # Parse YAML frontmatter
        frontmatter = self._parse_frontmatter(content)
        if not frontmatter:
            logger.warning(f"No frontmatter found in {path}")
            return None
        
        name = frontmatter.get("name", "")
        description = frontmatter.get("description", "")
        
        if not name:
            logger.warning(f"Skill missing 'name' in frontmatter: {path}")
            return None
        
        return Skill(
            name=name,
            description=description,
            content=content,
            path=path
        )
    
    def _parse_frontmatter(self, content: str) -> dict:
        """Parse YAML frontmatter from markdown content."""
        pattern = r"^---\s*\n(.*?)\n---\s*\n"
        match = re.match(pattern, content, re.DOTALL)
        
        if not match:
            return {}
        
        frontmatter_str = match.group(1)
        result = {}
        
        for line in frontmatter_str.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                result[key.strip()] = value.strip()
        
        return result
    
    def get(self, name: str) -> Optional[Skill]:
        """Get a skill by name."""
        return self._skills.get(name)
    
    def list_skills(self) -> list[Skill]:
        """List all loaded skills."""
        return list(self._skills.values())
    
    def get_skills_description(self) -> str:
        """Get a markdown description of all skills for system prompt."""
        if not self._skills:
            return "No skills available."
        
        lines = ["## Available Skills\n"]
        lines.append("You have access to these skills. Use `load_skill(name)` to get detailed instructions.\n")
        
        for skill in sorted(self._skills.values(), key=lambda s: s.name):
            lines.append(f"- **{skill.name}**: {skill.description}")
        
        return "\n".join(lines)


# Global loader instance
_loader: Optional[SkillLoader] = None


def get_skill_loader(skills_dir: str = "skills") -> SkillLoader:
    """Get or create the global skill loader."""
    global _loader
    if _loader is None:
        _loader = SkillLoader(skills_dir)
        _loader.load_all()
    return _loader


def get_skill(name: str) -> Optional[Skill]:
    """Get a skill by name from the global loader."""
    global _loader
    if _loader is None:
        return None
    return _loader.get(name)