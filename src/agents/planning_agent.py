from typing import List, Dict, Any, Optional
from src.graph.state import SubTask, TaskType, TaskStatus
from src.core.model_service import ModelService
from src.utils.logging_config import get_logger, get_agent_logger, log_agent_execution
import json
import re

logger = get_agent_logger("planning")

class PlanningAgent:
    """
    Planning agent using direct LLM calls.
    Decomposes user requests into structured execution plans with intelligent task classification.
    """
    
    def __init__(self):
        self.model_service = ModelService()
        self.llm = self.model_service.get_model_for_agent("planning")
    
    def generate_plan(self, user_request: str) -> List[SubTask]:
        logger.info(f"Generating plan for request: {user_request[:100]}...")
        
        # Store current request for fallback plan generation
        self.current_request = user_request
        
        try:
            # Create planning prompt
            prompt = self._create_planning_prompt(user_request)
            
            # Get response from LLM
            response = self.llm.invoke(prompt)
            
            # Parse response into structured plan
            plan = self._parse_plan_response(response)
            
            log_agent_execution("planning", user_request, plan)
            return plan
            
        except Exception as e:
            log_agent_execution("planning", user_request, error=e)
            # Return fallback plan
            return self._create_fallback_plan(user_request)
    
    def regenerate_plan(self, user_request: str, feedback: str, previous_plan: List[SubTask]) -> List[SubTask]:
        logger.info(f"Regenerating plan based on feedback: {feedback[:100]}...")
        
        try:
            # Create regeneration prompt
            prompt = self._create_regeneration_prompt(user_request, feedback, previous_plan)
            
            # Get response from LLM
            response = self.llm.invoke(prompt)
            
            # Parse response into structured plan
            plan = self._parse_plan_response(response)
            
            logger.info(f"Regenerated plan with {len(plan)} tasks")
            return plan
            
        except Exception as e:
            logger.error(f"Failed to regenerate plan: {e}", exc_info=True)
            # Return modified previous plan or fallback
            return self._create_fallback_plan(user_request)
    

    def _create_fallback_plan_from_output(self, output: str) -> List[SubTask]:
        
        # Try to extract task descriptions from output
        lines = output.split('\n')
        task_descriptions = []
        
        for line in lines:
            line = line.strip()
            if line and (line.startswith('-') or line.startswith('1.') or line.startswith('2.')):
                # Clean up the line
                clean_line = re.sub(r'^[-\d\.\s]+', '', line).strip()
                if clean_line:
                    task_descriptions.append(clean_line)
        
        # Create tasks from descriptions
        if not task_descriptions:
            task_descriptions = [f"Address the user request: {output[:100]}..."]
        
        tasks = []
        for i, description in enumerate(task_descriptions[:3], 1):  # Limit to 3 tasks
            task_type = TaskType.CODE if any(keyword in description.lower() for keyword in ['calculate', 'compute', 'code']) else TaskType.RESEARCH
            
            tasks.append(SubTask(
                id=i,
                type=task_type,
                description=description,
                dependencies=[] if i == 1 else [i-1],
                status=TaskStatus.PENDING,
                result=None
            ))
        
        return tasks

    def _create_planning_prompt(self, user_request: str) -> str:
        
        return f"""You are an expert task planning agent. Your job is to decompose complex user requests into structured, executable subtasks.

        TASK TYPES:
        - research: Web search, information gathering, content analysis
        - code: Python programming, calculations, data processing
        - analysis: Text analysis, summarization (handled by research agent)
        - summary: Content summarization (handled by research agent)  
        - calculation: Mathematical computations (requires code execution)

        RULES:
        1. Create a JSON array of tasks with: id, type, description, dependencies, status
        2. Use sequential IDs starting from 1
        3. Set all status to "pending"
        4. Only include dependencies that are truly necessary
        5. Be specific in task descriptions
        6. Avoid unnecessary code tasks - use research for simple analysis
        7. Use code only for computational work requiring Python execution

        USER REQUEST: {user_request}

        Generate a JSON plan following this exact format:
        [
          {{
            "id": 1,
            "type": "research",
            "description": "Specific task description",
            "dependencies": [],
            "status": "pending",
            "result": null
            }}
        ]

        JSON PLAN:"""

    def _create_regeneration_prompt(self, user_request: str, feedback: str, previous_plan: List[SubTask]) -> str:
        
        previous_plan_json = json.dumps(previous_plan, indent=2)
        
        return f"""You are an expert task planning agent. The user has provided feedback on your previous plan and wants you to create a revised version.

        ORIGINAL REQUEST: {user_request}

        PREVIOUS PLAN:
        {previous_plan_json}

        USER FEEDBACK: {feedback}

        TASK TYPES:
        - research: Web search, information gathering, content analysis
        - code: Python programming, calculations, data processing
        - analysis: Text analysis, summarization (handled by research agent)
        - summary: Content summarization (handled by research agent)
        - calculation: Mathematical computations (requires code execution)

        RULES:
        1. Address the user's feedback directly
        2. Create a JSON array of tasks with: id, type, description, dependencies, status
        3. Use sequential IDs starting from 1
        4. Set all status to "pending"
        5. Only include dependencies that are truly necessary
        6. Be specific in task descriptions
        7. Avoid unnecessary code tasks - use research for simple analysis

        Generate a REVISED JSON plan following this exact format:
        [
        {{
            "id": 1,
            "type": "research",
            "description": "Specific task description",
            "dependencies": [],
            "status": "pending",
            "result": null
        }}
        ]

        REVISED JSON PLAN:"""

    def _parse_plan_response(self, response: str) -> List[SubTask]:
        
        # Strategy 1: Direct JSON parsing
        try:
            return self._parse_direct(response)
        except Exception as e:
            logger.debug(f"Direct parsing failed: {e}")
        
        # Strategy 2: Clean and fix common JSON errors
        try:
            cleaned_response = self._clean_json_response(response)
            return self._parse_direct(cleaned_response)
        except Exception as e:
            logger.debug(f"Cleaned parsing failed: {e}")
        
        # Strategy 3: Extract JSON from mixed content
        try:
            extracted_json = self._extract_json_block(response)
            return self._parse_direct(extracted_json)
        except Exception as e:
            logger.debug(f"Extraction parsing failed: {e}")
        
        # Strategy 4: Fallback plan
        logger.warning("All parsing strategies failed, using fallback plan")
        logger.debug(f"Original response: {response}")
        return self._create_fallback_plan(response)
    
    def _parse_direct(self, response: str) -> List[SubTask]:
        # Extract JSON from response
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON array found in response")
        
        json_str = json_match.group(0)
        plan_data = json.loads(json_str)
        
        # Validate and convert to SubTask format
        plan = []
        for task_data in plan_data:
            # Validate required fields
            required_fields = ['id', 'type', 'description', 'dependencies', 'status']
            for field in required_fields:
                if field not in task_data:
                    raise ValueError(f"Missing required field: {field}")
            
            # Validate task type
            if task_data['type'] not in [TaskType.RESEARCH, TaskType.CODE, TaskType.ANALYSIS, TaskType.SUMMARY, TaskType.CALCULATION]:
                logger.warning(f"Unknown task type {task_data['type']}, defaulting to research")
                task_data['type'] = TaskType.RESEARCH
            
            # Convert dependencies to integers if they're strings
            dependencies = []
            for dep in task_data['dependencies']:
                if isinstance(dep, str) and dep.isdigit():
                    dependencies.append(int(dep))
                elif isinstance(dep, int):
                    dependencies.append(dep)
                else:
                    logger.warning(f"Invalid dependency format: {dep}, skipping")
            
            # Create SubTask
            subtask = SubTask(
                id=int(task_data['id']),
                type=task_data['type'],
                description=task_data['description'],
                dependencies=dependencies,
                status=TaskStatus.PENDING,
                result=None
            )
            
            plan.append(subtask)
        
        # Validate dependencies
        self._validate_dependencies(plan)
        
        return plan
    
    def _clean_json_response(self, response: str) -> str:
        import re
        
        # Fix end="value" to "description": "value"
        response = re.sub(r'\s*end="([^"]*)"', r'"description": "\1"', response)
        
        # Fix unquoted property names that aren't valid JSON
        response = re.sub(r'(\w+)=', r'"\1":', response)
        
        # Fix trailing commas before closing brackets
        response = re.sub(r',(\s*[}\]])', r'\1', response)
        
        # Fix single quotes to double quotes
        response = re.sub(r"'([^']*)'", r'"\1"', response)
        
        # Fix missing commas between objects
        response = re.sub(r'}\s*{', r'},{', response)
        
        return response
    
    def _extract_json_block(self, response: str) -> str:
        import re
        
        # Try to find JSON block markers
        json_patterns = [
            r'```json\s*(\[.*?\])\s*```',
            r'```\s*(\[.*?\])\s*```',
            r'(\[[\s\S]*?\])',
            r'(\{[\s\S]*?\})'
        ]
        
        for pattern in json_patterns:
            match = re.search(pattern, response, re.DOTALL)
            if match:
                return match.group(1)
        
        raise ValueError("No JSON block found in response")
    
    def _create_fallback_plan(self, original_response: str) -> List[SubTask]:
        logger.info("Creating fallback plan")
        
        # Try to extract task description from the response
        description = "Research and gather information about: " + self.current_request[:100] if hasattr(self, 'current_request') else "Complete the requested task"
        
        # Create a single research task as fallback
        fallback_task = SubTask(
            id=1,
            type=TaskType.RESEARCH,
            description=description,
            dependencies=[],
            status=TaskStatus.PENDING,
            result=None
        )
        
        return [fallback_task]
    
    def _validate_dependencies(self, plan: List[SubTask]) -> None:
        
        task_ids = {task['id'] for task in plan}
        
        # Check all dependencies exist
        for task in plan:
            for dep_id in task['dependencies']:
                if dep_id not in task_ids:
                    raise ValueError(f"Task {task['id']} has invalid dependency: {dep_id}")
        
        # Check for cycles using DFS
        def has_cycle(task_id: int, visited: set, rec_stack: set) -> bool:
            visited.add(task_id)
            rec_stack.add(task_id)
            
            # Find task with this ID
            task = next((t for t in plan if t['id'] == task_id), None)
            if not task:
                return False
            
            # Check all dependencies
            for dep_id in task['dependencies']:
                if dep_id not in visited:
                    if has_cycle(dep_id, visited, rec_stack):
                        return True
                elif dep_id in rec_stack:
                    return True
            
            rec_stack.remove(task_id)
            return False
        
        visited = set()
        for task in plan:
            if task['id'] not in visited:
                if has_cycle(task['id'], visited, set()):
                    raise ValueError("Circular dependency detected in plan")
    
    def _create_fallback_plan(self, user_request: str) -> List[SubTask]:
      
        logger.info("Creating fallback plan")
        
        # Determine if request likely needs code execution
        code_keywords = ['calculate', 'compute', 'analyze data', 'process', 'algorithm', 'code', 'program']
        needs_code = any(keyword in user_request.lower() for keyword in code_keywords)
        
        plan = [
            SubTask(
                id=1,
                type=TaskType.RESEARCH,
                description=f"Research and gather information about: {user_request}",
                dependencies=[],
                status=TaskStatus.PENDING,
                result=None
            )
        ]
        
        if needs_code:
            plan.append(
                SubTask(
                    id=2,
                    type=TaskType.CODE,
                    description=f"Perform computational analysis for: {user_request}",
                    dependencies=[1],
                    status=TaskStatus.PENDING,
                    result=None
                )
            )
        
        return plan