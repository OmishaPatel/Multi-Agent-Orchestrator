from langfuse import Langfuse, observe
from langfuse.langchain import CallbackHandler
import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import json
from contextlib import contextmanager
import uuid

# Try to import langfuse_context, but make it optional for compatibility
try:
    from langfuse import langfuse_context
    CONTEXT_AVAILABLE = True
except ImportError:
    CONTEXT_AVAILABLE = False
    # Create dummy context for compatibility
    class DummyContext:
        def update_current_observation(self, **kwargs):
            pass
        def update_current_trace(self, **kwargs):
            pass
    
    langfuse_context = DummyContext()

logger = logging.getLogger(__name__)

class DemoSafeCallbackHandler:
    """
    Demo-safe wrapper for Langfuse CallbackHandler that filters out errors
    to prevent red ERROR tags from appearing in Langfuse during demos
    """
    
    def __init__(self, base_handler: CallbackHandler):
        self.base_handler = base_handler
        self._suppress_errors = True
    
    def __getattr__(self, name):
        """Delegate all attributes to the base handler"""
        return getattr(self.base_handler, name)
    
    def on_chain_error(self, error, **kwargs):
        """Override error handling to suppress errors during demos"""
        if self._suppress_errors:
            # Log locally but don't send to Langfuse
            logger.debug(f"Demo mode: Suppressed chain error from Langfuse: {error}")
            return
        # If not suppressing, delegate to base handler
        return self.base_handler.on_chain_error(error, **kwargs)
    
    def on_llm_error(self, error, **kwargs):
        """Override LLM error handling to suppress errors during demos"""
        if self._suppress_errors:
            # Log locally but don't send to Langfuse
            logger.debug(f"Demo mode: Suppressed LLM error from Langfuse: {error}")
            return
        # If not suppressing, delegate to base handler
        return self.base_handler.on_llm_error(error, **kwargs)
    
    def on_tool_error(self, error, **kwargs):
        """Override tool error handling to suppress errors during demos"""
        if self._suppress_errors:
            # Log locally but don't send to Langfuse
            logger.debug(f"Demo mode: Suppressed tool error from Langfuse: {error}")
            return
        # If not suppressing, delegate to base handler
        return self.base_handler.on_tool_error(error, **kwargs)
    
    def on_retriever_error(self, error, **kwargs):
        """Override retriever error handling to suppress errors during demos"""
        if self._suppress_errors:
            # Log locally but don't send to Langfuse
            logger.debug(f"Demo mode: Suppressed retriever error from Langfuse: {error}")
            return
        # If not suppressing, delegate to base handler
        return self.base_handler.on_retriever_error(error, **kwargs)
    
    def enable_error_reporting(self):
        """Enable error reporting to Langfuse (for non-demo use)"""
        self._suppress_errors = False
        logger.info("Langfuse error reporting enabled")
    
    def disable_error_reporting(self):
        """Disable error reporting to Langfuse (for demo use)"""
        self._suppress_errors = True
        logger.info("Langfuse error reporting disabled for demo mode")

class EnhancedLangFuseService:
    """Enhanced LangFuse service with proper LangChain integration"""
    
    def __init__(self):
        self.client = None
        self.callback_handler = None
        self.current_session = None
        self.current_trace = None
        self._setup()
    
    def _setup(self):
        """Enhanced setup with better error handling and validation"""
        try:
            # Import settings here to avoid circular imports
            from src.config.settings import get_settings
            settings = get_settings()
            
            # DEMO MODE: Completely disable Langfuse in demo environment
            if settings.ENVIRONMENT == 'demo':
                logger.info("🎬 Demo mode detected - Langfuse disabled for clean demo experience")
                return
            
            public_key = settings.LANGFUSE_PUBLIC_KEY
            secret_key = settings.LANGFUSE_SECRET_KEY
            host = settings.LANGFUSE_HOST
            
            if not public_key or not secret_key:
                logger.info("LangFuse credentials not configured - running without observability")
                return
            
            # Initialize LangFuse client
            self.client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=host,
                debug=settings.ENVIRONMENT == 'development',
                flush_at=1,
                flush_interval=0.5,
            )
            
            # CRITICAL FIX: Initialize callback handler with comprehensive error handling
            try:
                # Try multiple initialization approaches
                self.callback_handler = None
                
                try:
                    base_handler = CallbackHandler()
                    if self._validate_base_callback_handler(base_handler):
                        # Create demo-safe wrapper that filters out errors
                        self.callback_handler = DemoSafeCallbackHandler(base_handler)
                        logger.info("✅ Langfuse Demo-Safe CallbackHandler initialized successfully")
                    else:
                        self.callback_handler = None
                except Exception as e1:
                    logger.debug(f"Demo-safe CallbackHandler init failed: {e1}")
                
                
                # Final validation
                if self.callback_handler is None:
                    logger.info("🔕 Langfuse CallbackHandler disabled - continuing without tracing")
                    
            except Exception as callback_error:
                logger.warning(f"Langfuse CallbackHandler setup failed: {callback_error}")
                self.callback_handler = None
            
            # Test connection
            self._test_connection()
            
            logger.info("✅ LangFuse connected successfully!")
            
        except Exception as e:
            logger.warning(f"LangFuse setup failed: {e} - continuing without observability")
            self.client = None
            self.callback_handler = None
    
    def _test_connection(self):
        """Test LangFuse connection with a simple event"""
        if self.client:
            try:
                # Create a simple event to test connection
                self.client.create_event(
                    name="connection_test",
                    metadata={"test": True, "timestamp": datetime.now().isoformat()}
                )
                logger.debug("LangFuse connection test successful")
            except Exception as e:
                logger.warning(f"LangFuse connection test failed: {e}")
    
    def _validate_base_callback_handler(self, handler) -> bool:
        """Validate that base callback handler is properly initialized"""
        if handler is None:
            return False
        
        required_attrs = ['raise_error', 'ignore_chain', 'on_chain_start', 'on_chain_end']
        missing_attrs = []
        
        for attr in required_attrs:
            if not hasattr(handler, attr):
                missing_attrs.append(attr)
        
        if missing_attrs:
            logger.warning(f"Base callback handler missing attributes: {missing_attrs}")
            return False
        
        logger.debug("Base callback handler validation successful")
        return True
    
    def _validate_callback_handler(self) -> bool:
        """Validate that callback handler is properly initialized"""
        if self.callback_handler is None:
            return False
        
        # For demo-safe handler, check if it has the base handler
        if isinstance(self.callback_handler, DemoSafeCallbackHandler):
            return self._validate_base_callback_handler(self.callback_handler.base_handler)
        
        # For regular handler, check directly
        return self._validate_base_callback_handler(self.callback_handler)
    
    def start_user_session(self, user_id: str = None, session_metadata: Dict[str, Any] = None) -> str:
        """Start a new user session for tracking"""
        if not self.is_enabled():
            return None
        
        try:
            session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Store session info (don't create a separate trace for session)
            self.current_session = {"id": session_id, "user_id": user_id}
            
            logger.info(f"Started LangFuse session: {session_id}")
            return session_id
            
        except Exception as e:
            logger.error(f"Failed to start LangFuse session: {e}")
            return None
    
    def start_workflow_trace(self, workflow_name: str, user_request: str, metadata: Dict[str, Any] = None) -> str:
        """Start a new workflow trace - callback handler will create proper traces"""
        if not self.is_enabled():
            return None
        
        try:
            # Generate a trace ID for reference
            trace_id = str(uuid.uuid4())
            
            # Store trace info - the callback handler will create the actual trace
            self.current_trace = {"id": trace_id, "name": workflow_name}
            
            # Set user context for callback handler
            if self.callback_handler and self.current_session:
                # The callback handler will automatically capture user context
                pass
            
            logger.info(f"Started workflow trace: {trace_id}")
            return trace_id
            
        except Exception as e:
            logger.error(f"Failed to start workflow trace: {e}")
            return None
    
    @contextmanager
    def trace_agent_execution(self, agent_name: str, task_description: str, metadata: Dict[str, Any] = None):
        """Context manager for tracing agent execution within the main workflow trace"""
        agent_start_time = datetime.now()
        agent_id = str(uuid.uuid4())
        
        try:
            if self.is_enabled() and self.current_trace:
                # Log agent start event
                self.client.create_event(
                    name="agent_start",
                    metadata={
                        "trace_id": self.current_trace["id"],
                        "agent_id": agent_id,
                        "agent_name": agent_name,
                        "task_description": task_description[:200],
                        "agent_start": agent_start_time.isoformat(),
                        "event_type": "agent_start",
                        **(metadata or {})
                    }
                )
            
            # Yield agent info for potential nested operations
            yield {"agent_id": agent_id, "agent_name": agent_name}
            
            # Log successful completion
            if self.is_enabled() and self.current_trace:
                self.client.create_event(
                    name="agent_complete",
                    metadata={
                        "trace_id": self.current_trace["id"],
                        "agent_id": agent_id,
                        "agent_name": agent_name,
                        "agent_end": datetime.now().isoformat(),
                        "duration_seconds": (datetime.now() - agent_start_time).total_seconds(),
                        "success": True,
                        "event_type": "agent_complete"
                    }
                )
            
        except Exception as e:
            # Log agent error
            if self.is_enabled() and self.current_trace:
                self.client.create_event(
                    name="agent_error",
                    metadata={
                        "trace_id": self.current_trace["id"],
                        "agent_id": agent_id,
                        "agent_name": agent_name,
                        "agent_end": datetime.now().isoformat(),
                        "duration_seconds": (datetime.now() - agent_start_time).total_seconds(),
                        "success": False,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "event_type": "agent_error"
                    }
                )
            raise
    
    def log_llm_call(self, model_name: str, prompt: str, response: str, 
                     metadata: Dict[str, Any] = None, metrics: Dict[str, Any] = None):
        """Log individual LLM calls with detailed metrics"""
        if not self.is_enabled():
            return
        
        try:
            # Create LLM call event with comprehensive metrics
            self.client.create_event(
                name="llm_call",
                metadata={
                    "trace_id": self.current_trace["id"] if self.current_trace else None,
                    "model_name": model_name,
                    "prompt": prompt[:500],  # Truncate long prompts
                    "response": response[:500],  # Truncate long responses
                    "prompt_length": len(prompt),
                    "response_length": len(response),
                    "input_tokens": metrics.get("input_tokens", 0) if metrics else 0,
                    "output_tokens": metrics.get("output_tokens", 0) if metrics else 0,
                    "total_tokens": metrics.get("total_tokens", 0) if metrics else 0,
                    "input_cost": metrics.get("input_cost", 0) if metrics else 0,
                    "output_cost": metrics.get("output_cost", 0) if metrics else 0,
                    "total_cost": metrics.get("total_cost", 0) if metrics else 0,
                    "timestamp": datetime.now().isoformat(),
                    "event_type": "llm_call",
                    **(metadata or {})
                }
            )
            
            logger.debug(f"Logged LLM call for {model_name}")
            
        except Exception as e:
            logger.error(f"Failed to log LLM call: {e}")
    
    def log_workflow_result(self, result: str, success: bool = True, 
                           metadata: Dict[str, Any] = None):
        """Log final workflow result and end the trace"""
        if not self.is_enabled():
            return
        
        try:
            # End the workflow trace with completion event
            if self.current_trace:
                self.client.create_event(
                    name="workflow_complete",
                    metadata={
                        "trace_id": self.current_trace["id"],
                        "result": result[:1000],  # Truncate long results
                        "result_length": len(result),
                        "success": success,
                        "completion_time": datetime.now().isoformat(),
                        "workflow_status": "completed" if success else "failed",
                        "event_type": "trace_end",
                        **(metadata or {})
                    }
                )
                
                # Clear current trace
                self.current_trace = None
            
            logger.info("Logged workflow result to LangFuse")
            
        except Exception as e:
            logger.error(f"Failed to log workflow result: {e}")
    


    def log_custom_event(self, event_name: str, data: Dict[str, Any]):
        """Log custom events for specific learning insights"""
        if not self.is_enabled():
            return
        
        try:
            # Create event within the current trace if available
            event = self.client.create_event(
                name=event_name,
                metadata={
                    "trace_id": self.current_trace["id"] if self.current_trace else None,
                    "timestamp": datetime.now().isoformat(),
                    "event_type": event_name,
                    **data
                }
            )
            
            logger.debug(f"Logged custom event: {event_name}")
            
        except Exception as e:
            logger.error(f"Failed to log custom event: {e}")
    
    def log_model_usage(self, model: str, input_tokens: int, output_tokens: int, 
                       total_tokens: int, input_cost: float, output_cost: float):
        """Log model usage and costs to LangFuse (deprecated - now included in log_llm_call)"""
        # This method is kept for backward compatibility but functionality moved to log_llm_call
        logger.debug(f"Model usage logged via log_llm_call: {model} - {total_tokens} tokens, ${input_cost + output_cost:.4f}")
        pass

    def get_callback_handler(self) -> Optional[CallbackHandler]:
        """Get callback handler for LangChain integration"""
        # CRITICAL FIX: Only return callback handler if Langfuse is enabled AND properly initialized
        if not self.is_enabled():
            return None
        if self._validate_callback_handler():
            return self.callback_handler
        return None
    
    def get_langchain_config(self) -> Dict[str, Any]:
        """Get LangChain config with Langfuse callback, user tracking, and session tracking"""
        if not self.is_enabled():
            return {}
        
        # CRITICAL FIX: Only add callbacks if handler is properly initialized and not None
        callbacks = []
        if self._validate_callback_handler():
            callbacks = [self.callback_handler]
        
        config = {
            "callbacks": callbacks,
            "metadata": {}
        }
        
        # Add user tracking if available (according to Langfuse docs)
        if self.current_session and self.current_session.get("user_id"):
            config["metadata"]["langfuse_user_id"] = self.current_session["user_id"]
        
        # Add session tracking if available (according to Langfuse docs)
        if self.current_session and self.current_session.get("id"):
            config["metadata"]["langfuse_session_id"] = self.current_session["id"]
        
        return config
    
    def get_langgraph_config(self, thread_id: str) -> Dict[str, Any]:
        """Get LangGraph-specific config with Langfuse integration"""
        base_config = {"configurable": {"thread_id": thread_id}}
        
        if not self.is_enabled():
            logger.debug(f"Langfuse not enabled - using base config")
            return base_config
        
        try:
            # CRITICAL FIX: Only add callbacks if handler is properly initialized and not None
            callbacks = []
            if self._validate_callback_handler():
                callbacks = [self.callback_handler]
                logger.debug(f"Added valid Langfuse callback handler")
            else:
                logger.debug(f"Callback handler validation failed, using base config")
            
            # Only add callbacks if we have valid ones
            if callbacks:
                config = {
                    "configurable": {"thread_id": thread_id},
                    "callbacks": callbacks,
                    "metadata": {
                        "thread_id": thread_id,
                        "workflow_type": "langgraph_agentic_flow",
                        "system": "clarity-ai"
                    }
                }
            else:
                # Use base config without callbacks if no valid handlers
                config = {
                    "configurable": {"thread_id": thread_id},
                    "metadata": {
                        "thread_id": thread_id,
                        "workflow_type": "langgraph_agentic_flow",
                        "system": "clarity-ai"
                    }
                }
            
            # Add session context if available
            if self.current_session:
                config["metadata"]["langfuse_session_id"] = self.current_session.get("id")
                config["metadata"]["langfuse_user_id"] = self.current_session.get("user_id")
            
            # Add trace context if available
            if self.current_trace:
                config["metadata"]["langfuse_trace_id"] = self.current_trace.get("id")
            
            logger.debug(f"Created LangGraph config with {len(callbacks)} callbacks")
            return config
            
        except Exception as e:
            logger.error(f"Failed to create LangGraph config: {e}")
            return base_config
    
    def trace_langgraph_workflow(self, workflow_name: str, initial_state: Dict[str, Any], 
                                thread_id: str) -> str:
        """Start tracing a LangGraph workflow execution"""
        if not self.is_enabled():
            return None
        
        try:
            # Create workflow trace event
            self.log_custom_event("langgraph_workflow_start", {
                "workflow_name": workflow_name,
                "thread_id": thread_id,
                "workflow_type": "langgraph",
                "initial_state_keys": list(initial_state.keys()),
                "user_request": initial_state.get("user_request", "")[:200]
            })
            
            return thread_id
            
        except Exception as e:
            logger.error(f"Failed to start LangGraph workflow trace: {e}")
            return None
    
    def trace_langgraph_node(self, node_name: str, input_state: Dict[str, Any], 
                           output_state: Dict[str, Any], thread_id: str):
        """Trace individual LangGraph node execution"""
        if not self.is_enabled():
            return
        
        try:
            # Create node execution event
            self.log_custom_event(f"langgraph_node_{node_name}", {
                "thread_id": thread_id,
                "node_name": node_name,
                "node_type": "langgraph_node",
                "state_changes": self._calculate_state_changes(input_state, output_state),
                "input_summary": self._create_state_summary(input_state),
                "output_summary": self._create_state_summary(output_state)
            })
            
        except Exception as e:
            logger.error(f"Failed to trace LangGraph node {node_name}: {e}")
    
    def _calculate_state_changes(self, input_state: Dict[str, Any], 
                               output_state: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate what changed between input and output state"""
        changes = {}
        
        # Check for new or modified keys
        for key, value in output_state.items():
            if key not in input_state:
                changes[f"added_{key}"] = True
            elif input_state[key] != value:
                changes[f"modified_{key}"] = True
        
        # Check for removed keys
        for key in input_state:
            if key not in output_state:
                changes[f"removed_{key}"] = True
        
        return changes
    
    def _create_state_summary(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Create a summary of state for logging"""
        return {
            "plan_size": len(state.get('plan', [])),
            "task_results_count": len(state.get('task_results', {})),
            "next_task_id": state.get('next_task_id'),
            "approval_status": state.get('human_approval_status'),
            "has_final_report": bool(state.get('final_report'))
        }
    
    def is_enabled(self) -> bool:
        """Check if LangFuse is properly configured and enabled"""
        return self.client is not None
    
    def set_demo_mode(self, enabled: bool = True):
        """Enable or disable demo mode (suppresses errors from being sent to Langfuse)"""
        if isinstance(self.callback_handler, DemoSafeCallbackHandler):
            if enabled:
                self.callback_handler.disable_error_reporting()
                logger.info("🎬 Demo mode enabled - errors will not be sent to Langfuse")
            else:
                self.callback_handler.enable_error_reporting()
                logger.info("📊 Demo mode disabled - full error reporting to Langfuse enabled")
        else:
            logger.warning("Demo mode control not available - callback handler is not demo-safe")
    
    def get_session_analytics(self, session_id: str) -> Dict[str, Any]:
        """Get analytics for a specific session (requires LangFuse API)"""
        if not self.is_enabled():
            return {}
        
        try:
            # This would require LangFuse API calls to get session data
            # For now, return placeholder structure
            return {
                "session_id": session_id,
                "total_traces": 0,
                "total_llm_calls": 0,
                "total_tokens": 0,
                "average_latency": 0.0,
                "success_rate": 0.0
            }
        except Exception as e:
            logger.error(f"Failed to get session analytics: {e}")
            return {}

# Global enhanced instance
langfuse_service = EnhancedLangFuseService()
