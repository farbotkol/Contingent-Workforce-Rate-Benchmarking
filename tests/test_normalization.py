"""
Unit Tests for Role Normalization Module

EPIC 10 - Testing & Reliability
"""

import pytest
import os
from processing.normalization import RoleNormalizer


@pytest.fixture
def normalizer():
    """Fixture to create a RoleNormalizer instance."""
    return RoleNormalizer()


class TestRoleMapping:
    """Tests for role title mapping."""
    
    def test_direct_mapping(self, normalizer):
        """Test direct mapping of a known external title."""
        result = normalizer.map_title("software engineer")
        assert result == "Software Engineer"
    
    def test_case_insensitive(self, normalizer):
        """Test that mapping is case-insensitive."""
        result1 = normalizer.map_title("SOFTWARE ENGINEER")
        result2 = normalizer.map_title("Software Engineer")
        result3 = normalizer.map_title("software engineer")
        
        assert result1 == result2 == result3 == "Software Engineer"
    
    def test_partial_match(self, normalizer):
        """Test partial matching of titles."""
        result = normalizer.map_title("Senior DevOps Engineer")
        assert result == "DevOps Engineer"
    
    def test_unmapped_role(self, normalizer):
        """Test that unmapped roles return 'Unmapped Role'."""
        result = normalizer.map_title("Chief Happiness Officer")
        assert result == "Unmapped Role"
    
    def test_empty_title(self, normalizer):
        """Test handling of empty title."""
        result = normalizer.map_title("")
        assert result == "Unmapped Role"
    
    def test_multiple_mappings(self, normalizer):
        """Test that multiple external titles map to same canonical role."""
        titles = ["sde", "software developer", "application developer"]
        expected = "Software Engineer"
        
        for title in titles:
            assert normalizer.map_title(title) == expected


class TestSeniorityClassification:
    """Tests for seniority level classification."""
    
    def test_junior_detection(self, normalizer):
        """Test detection of Junior level."""
        level, confidence = normalizer.classify_seniority("Junior Software Engineer")
        assert level == "Junior"
        assert confidence >= 0.7
    
    def test_senior_detection(self, normalizer):
        """Test detection of Senior level."""
        level, confidence = normalizer.classify_seniority("Senior Developer")
        assert level == "Senior"
        assert confidence >= 0.7
    
    def test_lead_detection(self, normalizer):
        """Test detection of Lead level."""
        level, confidence = normalizer.classify_seniority("Lead Software Engineer")
        assert level == "Lead"
        assert confidence >= 0.7
    
    def test_architect_detection(self, normalizer):
        """Test detection of Architect level."""
        level, confidence = normalizer.classify_seniority("Solutions Architect")
        assert level == "Architect"
        assert confidence > 0.7
    
    def test_default_level(self, normalizer):
        """Test that default level is Mid with lower confidence."""
        level, confidence = normalizer.classify_seniority("Software Engineer")
        assert level == "Mid"
        assert confidence <= 0.9
    
    def test_override(self, normalizer):
        """Test that user override takes precedence."""
        level, confidence = normalizer.classify_seniority(
            "Software Engineer",
            override="Senior"
        )
        assert level == "Senior"
        assert confidence == 1.0
    
    def test_empty_title_classification(self, normalizer):
        """Test seniority classification with empty title."""
        level, confidence = normalizer.classify_seniority("")
        assert level == "Mid"
        assert confidence < 0.5


class TestNormalization:
    """Tests for complete normalization."""
    
    def test_complete_normalization(self, normalizer):
        """Test complete normalization process."""
        result = normalizer.normalize("Senior Full Stack Developer")
        
        assert result['canonical_role'] == "Full Stack Developer"
        assert result['seniority_level'] == "Senior"
        assert result['confidence'] > 0.0
        assert result['original_title'] == "Senior Full Stack Developer"
    
    def test_normalization_with_override(self, normalizer):
        """Test normalization with seniority override."""
        result = normalizer.normalize(
            "Software Engineer",
            seniority_override="Lead"
        )
        
        assert result['canonical_role'] == "Software Engineer"
        assert result['seniority_level'] == "Lead"
        assert result['confidence'] == 1.0
    
    def test_normalization_returns_dict(self, normalizer):
        """Test that normalization returns a dictionary with expected keys."""
        result = normalizer.normalize("Data Scientist")
        
        assert isinstance(result, dict)
        assert 'canonical_role' in result
        assert 'seniority_level' in result
        assert 'confidence' in result
        assert 'original_title' in result
