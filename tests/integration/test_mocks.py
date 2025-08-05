"""
Test utilities and assertion helpers for integration tests.
Provides centralized test helpers to ensure consistent validation across tests.
"""

import re
from typing import Dict, Any, List


class TestAssertionHelpers:
    """Helper methods for updated test assertions"""
    
    @staticmethod
    def assert_research_content(result: str):
        """Assert research content contains expected patterns"""
        patterns = [
            r"research|analysis|findings|summary",
            r"sources?|references?|information",
            r"key|important|significant|main"
        ]
        
        matched_patterns = 0
        for pattern in patterns:
            if re.search(pattern, result, re.IGNORECASE):
                matched_patterns += 1
        
        assert matched_patterns >= 2, f"Research result should contain at least 2 expected patterns. Content: {result[:200]}..."
    
    @staticmethod
    def assert_security_validation(result: str):
        """Assert security validation contains expected patterns"""
        patterns = [
            r"security|validation|safe|risk",
            r"approved|denied|restricted|allowed",
            r"check|review|analysis|scan"
        ]
        
        matched_patterns = 0
        for pattern in patterns:
            if re.search(pattern, result, re.IGNORECASE):
                matched_patterns += 1
        
        assert matched_patterns >= 1, f"Security result should contain security-related patterns. Content: {result[:200]}..."
    
    @staticmethod
    def assert_plan_structure(plan: List[Dict[str, Any]]):
        """Assert plan has valid structure"""
        assert isinstance(plan, list), "Plan should be a list"
        assert len(plan) > 0, "Plan should contain at least one task"
        
        for i, task in enumerate(plan):
            assert isinstance(task, dict), f"Task {i} should be a dictionary"
            
            required_fields = ['id', 'type', 'description', 'dependencies', 'status']
            for field in required_fields:
                assert field in task, f"Task {i} missing required field: {field}"
            
            assert isinstance(task['id'], int), f"Task {i} id should be an integer"
            assert isinstance(task['dependencies'], list), f"Task {i} dependencies should be a list"
    
    @staticmethod
    def assert_response_format(response: Dict[str, Any], expected_fields: List[str]):
        """Assert response has expected format"""
        assert isinstance(response, dict), "Response should be a dictionary"
        
        for field in expected_fields:
            assert field in response, f"Response missing required field: {field}"
        
        if 'response' in response:
            assert isinstance(response['response'], str), "Response content should be a string"
            assert len(response['response']) > 0, "Response content should not be empty"