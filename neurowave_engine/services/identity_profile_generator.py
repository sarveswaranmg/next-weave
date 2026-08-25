"""
Identity Profile Generator

Generates compressed user identity profiles from the identity graph.
Creates human-readable summaries of user identity.
"""

from typing import Dict, List, Optional, Tuple
import logging
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import and_

from neurowave_engine.db.models import IdentityNode, IdentityHistory

import openai


logger = logging.getLogger(__name__)


class IdentityProfileGenerator:
    """
    Generates user identity profiles.
    
    Creates:
    - Text summaries of user identity
    - Goal-interest mappings
    - Communication preferences
    - Skill profiles
    - Evolution narratives
    """

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def generate_profile(
        self,
        user_id: str,
        include_evolution: bool = True,
        min_confidence: float = 0.5
    ) -> Dict:
        """
        Generate comprehensive identity profile for user.
        
        Args:
            user_id: User ID
            include_evolution: Include identity evolution narrative
            min_confidence: Minimum confidence threshold
            
        Returns:
            Identity profile
        """
        # Get all traits
        nodes = self.db.query(IdentityNode).filter(
            and_(
                IdentityNode.user_id == user_id,
                IdentityNode.confidence >= min_confidence
            )
        ).all()

        if not nodes:
            logger.warning(f"No identity nodes found for user {user_id}")
            return {}

        # Organize by type
        profile_data = {
            "goals": [],
            "interests": [],
            "communication": [],
            "behaviors": [],
            "values": [],
            "skills": []
        }

        # IdentityNode.node_type is stored singular ("goal", "interest", ...);
        # profile_data buckets are plural category names.
        node_type_to_category = {
            "goal": "goals",
            "interest": "interests",
            "communication": "communication",
            "behavior": "behaviors",
            "value": "values",
            "skill": "skills",
        }

        for node in nodes:
            category = node_type_to_category.get(node.node_type)
            if category:
                profile_data[category].append({
                    "value": node.node_value,
                    "confidence": node.confidence,
                    "importance": node.importance,
                    "reinforcement_count": node.reinforcement_count,
                    "progression": node.progression_level if node.node_type == "skill" else None
                })

        # Sort by importance within each category
        for key in profile_data:
            profile_data[key].sort(key=lambda x: x["importance"], reverse=True)

        # Build profile
        profile = {
            "user_id": user_id,
            "generated_at": datetime.utcnow().isoformat(),
            "summary": self._generate_text_summary(user_id, profile_data),
            "goals": profile_data["goals"],
            "interests": profile_data["interests"],
            "communication_style": self._summarize_communication(profile_data["communication"]),
            "behavioral_traits": profile_data["behaviors"],
            "values": profile_data["values"],
            "skills": profile_data["skills"],
            "confidence_metrics": self._calculate_confidence_metrics(nodes),
        }

        if include_evolution:
            profile["evolution"] = self._generate_evolution_narrative(user_id)

        return profile

    def _generate_text_summary(
        self,
        user_id: str,
        profile_data: Dict
    ) -> str:
        """
        Generate human-readable text summary of user.
        
        Args:
            user_id: User ID
            profile_data: Organized profile data
            
        Returns:
            Text summary
        """
        summary_parts = []

        # Goals section
        if profile_data["goals"]:
            top_goal = profile_data["goals"][0]["value"].replace("_", " ").title()
            summary_parts.append(f"Working towards: {top_goal}")

            if len(profile_data["goals"]) > 1:
                other_goals = ", ".join([
                    g["value"].replace("_", " ").title()
                    for g in profile_data["goals"][1:3]
                ])
                summary_parts.append(f"Also interested in: {other_goals}")

        # Interests section
        if profile_data["interests"]:
            interests = ", ".join([
                i["value"].replace("_", " ").title()
                for i in profile_data["interests"][:3]
            ])
            summary_parts.append(f"Passionate about: {interests}")

        # Traits section
        if profile_data["behaviors"]:
            traits = ", ".join([
                t["value"].replace("_", " ").title()
                for t in profile_data["behaviors"][:2]
            ])
            summary_parts.append(f"Core traits: {traits}")

        # Communication section
        if profile_data["communication"]:
            comm_styles = ", ".join([
                c["value"].replace("_", " ").title()
                for c in profile_data["communication"]
            ])
            summary_parts.append(f"Prefers {comm_styles} communication")

        # Skills section
        if profile_data["skills"]:
            top_skills = ", ".join([
                s["value"].replace("_", " ").title()
                for s in profile_data["skills"][:3]
            ])
            summary_parts.append(f"Skilled in: {top_skills}")

        return ". ".join(summary_parts) + "."

    def _summarize_communication(self, comm_traits: List[Dict]) -> Dict:
        """
        Summarize communication preferences.
        
        Args:
            comm_traits: Communication trait list
            
        Returns:
            Communication summary
        """
        if not comm_traits:
            return {
                "style": "unknown",
                "preferences": []
            }

        sorted_traits = sorted(comm_traits, key=lambda x: x["confidence"], reverse=True)

        return {
            "primary": sorted_traits[0]["value"],
            "preferences": [t["value"] for t in sorted_traits],
            "confidence": sorted_traits[0]["confidence"] if sorted_traits else 0.0
        }

    def _calculate_confidence_metrics(self, nodes: List[IdentityNode]) -> Dict:
        """
        Calculate aggregate confidence metrics.
        
        Args:
            nodes: List of identity nodes
            
        Returns:
            Confidence metrics
        """
        if not nodes:
            return {}

        confidences = [n.confidence for n in nodes]
        reinforcements = [n.reinforcement_count for n in nodes]

        return {
            "average_confidence": sum(confidences) / len(confidences),
            "median_confidence": sorted(confidences)[len(confidences) // 2],
            "min_confidence": min(confidences),
            "max_confidence": max(confidences),
            "total_traits": len(nodes),
            "total_reinforcements": sum(reinforcements),
            "avg_reinforcements_per_trait": sum(reinforcements) / len(reinforcements)
        }

    def _generate_evolution_narrative(self, user_id: str) -> Dict:
        """
        Generate narrative of user's identity evolution.
        
        Args:
            user_id: User ID
            
        Returns:
            Evolution narrative
        """
        history = self.db.query(IdentityHistory).filter(
            IdentityHistory.user_id == user_id
        ).order_by(
            IdentityHistory.created_at.desc()
        ).limit(50).all()

        if not history:
            return {
                "narrative": "No identity evolution tracked yet.",
                "key_changes": []
            }

        # Find significant changes
        significant_changes = [
            h for h in history
            if abs(h.confidence_delta) >= 0.15
        ]

        # Build narrative
        emerged_traits = [
            h for h in significant_changes
            if h.event_type == "emerged"
        ]
        reinforced_traits = [
            h for h in significant_changes
            if h.event_type == "reinforced"
        ]
        declined_traits = [
            h for h in significant_changes
            if h.event_type in ["declined", "decayed"]
        ]

        narrative_parts = []

        if emerged_traits:
            emerging = ", ".join([h.node_value for h in emerged_traits[:3]])
            narrative_parts.append(f"Recent interests: {emerging}")

        if reinforced_traits:
            reinforced = ", ".join([h.node_value for h in reinforced_traits[:3]])
            narrative_parts.append(f"Strengthening: {reinforced}")

        if declined_traits:
            declined = ", ".join([h.node_value for h in declined_traits[:2]])
            narrative_parts.append(f"Shifting away from: {declined}")

        narrative = ". ".join(narrative_parts) if narrative_parts else "Identity remains stable."

        return {
            "narrative": narrative,
            "key_changes": {
                "emerged": [h.node_value for h in emerged_traits[:5]],
                "reinforced": [h.node_value for h in reinforced_traits[:5]],
                "declined": [h.node_value for h in declined_traits[:5]]
            },
            "total_changes": len(history)
        }

    def generate_concise_profile(self, user_id: str) -> str:
        """
        Generate one-sentence identity profile.
        
        Args:
            user_id: User ID
            
        Returns:
            Concise profile string
        """
        profile = self.generate_profile(user_id, include_evolution=False)

        if not profile.get("summary"):
            return "User identity profile not yet established."

        # Trim to reasonable length
        summary = profile["summary"]
        if len(summary) > 300:
            summary = summary[:297] + "..."

        return summary

    def generate_skill_profile(self, user_id: str) -> Dict:
        """
        Generate detailed skill profile.
        
        Args:
            user_id: User ID
            
        Returns:
            Skill profile
        """
        skills = self.db.query(IdentityNode).filter(
            and_(
                IdentityNode.user_id == user_id,
                IdentityNode.node_type == "skill",
                IdentityNode.confidence >= 0.4
            )
        ).order_by(
            IdentityNode.confidence.desc()
        ).all()

        if not skills:
            return {
                "skills": [],
                "summary": "No skills tracked yet."
            }

        skill_data = []
        for skill in skills:
            skill_data.append({
                "skill": skill.node_value,
                "confidence": skill.confidence,
                "level": skill.progression_level or "intermediate",
                "progression": skill.progression_score,
                "reinforcements": skill.reinforcement_count
            })

        # Categorize by proficiency
        expert = [s for s in skill_data if s["confidence"] >= 0.8]
        intermediate = [s for s in skill_data if 0.6 <= s["confidence"] < 0.8]
        learning = [s for s in skill_data if s["confidence"] < 0.6]

        return {
            "skills": skill_data,
            "expert_level": [s["skill"] for s in expert],
            "intermediate_level": [s["skill"] for s in intermediate],
            "learning": [s["skill"] for s in learning],
            "total_skills": len(skill_data)
        }

    def get_profile_for_context(self, user_id: str, context_type: str = "general") -> str:
        """
        Generate profile snippet optimized for different contexts.
        
        Args:
            user_id: User ID
            context_type: Type of context (general, technical, creative, etc.)
            
        Returns:
            Context-specific profile
        """
        profile = self.generate_profile(user_id, include_evolution=False)

        if context_type == "technical":
            # Focus on technical interests and skills
            parts = []
            if profile.get("interests"):
                tech_interests = [i for i in profile["interests"] if i["importance"] >= 0.6]
                if tech_interests:
                    interests_str = ", ".join([i["value"] for i in tech_interests[:3]])
                    parts.append(f"Technical interests: {interests_str}")

            if profile.get("skills"):
                tech_skills = [s for s in profile["skills"] if s["importance"] >= 0.6]
                if tech_skills:
                    skills_str = ", ".join([s["value"] for s in tech_skills[:3]])
                    parts.append(f"Technical skills: {skills_str}")

            return ". ".join(parts) if parts else "No technical profile available."

        elif context_type == "goals":
            # Focus on goals and values
            parts = []
            if profile.get("goals"):
                goal_str = ", ".join([g["value"] for g in profile["goals"][:2]])
                parts.append(f"Goals: {goal_str}")
            if profile.get("values"):
                value_str = ", ".join([v["value"] for v in profile["values"][:2]])
                parts.append(f"Values: {value_str}")

            return ". ".join(parts) if parts else "No goals profile available."

        else:  # general
            return profile.get("summary", "No identity profile available.")
