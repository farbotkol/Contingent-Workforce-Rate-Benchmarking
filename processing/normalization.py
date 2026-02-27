"""
Role Normalization Module

Handles mapping of external job titles to internal taxonomy and seniority classification.
EPIC 1 - Role Normalisation Engine
"""

import yaml
import os
from typing import Dict, List, Tuple, Optional


class RoleNormalizer:
    """Maps external job titles to canonical internal roles and seniority levels."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the role normalizer.
        
        Args:
            config_path: Path to role_mapping.yaml. If None, uses default location.
        """
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'config',
                'role_mapping.yaml'
            )
        
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.canonical_roles = self.config.get('canonical_roles', [])
        self.seniority_levels = self.config.get('seniority_levels', [])
        self.seniority_keywords = self.config.get('seniority_keywords', {})
        self.role_mappings = self.config.get('role_mappings', {})
        
        # Create reverse mapping for faster lookup
        self._create_reverse_mapping()
    
    def _create_reverse_mapping(self) -> None:
        """Create a reverse mapping from external title to canonical role."""
        self.reverse_mapping = {}
        for canonical_role, external_titles in self.role_mappings.items():
            for external_title in external_titles:
                self.reverse_mapping[external_title.lower()] = canonical_role
    
    def map_title(self, external_title: str) -> str:
        """
        Map an external job title to a canonical internal role.
        
        Args:
            external_title: The external job title to map
            
        Returns:
            The canonical role name, or "Unmapped Role" if no match found
        """
        if not external_title:
            return "Unmapped Role"
        
        external_lower = external_title.lower().strip()
        
        # Direct lookup
        if external_lower in self.reverse_mapping:
            return self.reverse_mapping[external_lower]
        
        # Partial match - check if any external title is contained in the input
        for external_title_key, canonical_role in self.reverse_mapping.items():
            if external_title_key in external_lower:
                return canonical_role
        
        # Check if the input contains any external title
        for external_title_key, canonical_role in self.reverse_mapping.items():
            if external_title_key in external_lower or external_lower in external_title_key:
                return canonical_role
        
        return "Unmapped Role"
    
    def classify_seniority(
        self,
        job_title: str,
        override: Optional[str] = None
    ) -> Tuple[str, float]:
        """
        Classify the seniority level from a job title.
        
        Args:
            job_title: The job title to classify
            override: Optional user-provided seniority level (takes precedence)
            
        Returns:
            Tuple of (seniority_level, confidence)
            confidence: 0.0 to 1.0, where 1.0 is certain, 0.5 is default/ambiguous
        """
        # User override takes precedence
        if override and override in self.seniority_levels:
            return override, 1.0
        
        if not job_title:
            return "Mid", 0.3  # Default with low confidence
        
        job_title_lower = job_title.lower()
        
        # Check for seniority keywords
        matches = []
        for level, keywords in self.seniority_keywords.items():
            for keyword in keywords:
                if keyword.lower() in job_title_lower:
                    matches.append(level)
                    break
        
        # If multiple matches, prioritize in order: Architect, Lead, Senior, Junior, Mid
        priority_order = ["Architect", "Lead", "Senior", "Junior", "Mid"]
        
        if matches:
            for level in priority_order:
                if level in matches:
                    confidence = 0.9 if len(matches) == 1 else 0.7
                    return level, confidence
        
        # Default to Mid with low confidence
        return "Mid", 0.5
    
    def normalize(
        self,
        external_title: str,
        seniority_override: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Complete normalization: map title and classify seniority.
        
        Args:
            external_title: External job title
            seniority_override: Optional user-provided seniority level
            
        Returns:
            Dictionary with canonical_role, seniority_level, and confidence
        """
        canonical_role = self.map_title(external_title)
        seniority_level, confidence = self.classify_seniority(
            external_title,
            seniority_override
        )
        
        return {
            'canonical_role': canonical_role,
            'seniority_level': seniority_level,
            'confidence': confidence,
            'original_title': external_title
        }


def load_normalizer(config_path: Optional[str] = None) -> RoleNormalizer:
    """
    Factory function to load a RoleNormalizer instance.
    
    Args:
        config_path: Optional path to role_mapping.yaml
        
    Returns:
        RoleNormalizer instance
    """
    return RoleNormalizer(config_path)
