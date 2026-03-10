"""
skills/__init__.py — Skills Package

Provides skill loading and management for the Go2 robot.
"""

from skills.base import Skill, SkillResult, SkillLoader, get_skill_loader, get_skill

__all__ = ["Skill", "SkillResult", "SkillLoader", "get_skill_loader", "get_skill"]