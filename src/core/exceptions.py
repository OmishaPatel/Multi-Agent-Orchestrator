# src/core/exceptions.py
from fastapi import HTTPException, status


class ClarityException(Exception):
    """Base exception for Clarity.ai application."""
    pass


class WorkflowNotFoundException(ClarityException):
    """Exception raised when a workflow thread is not found."""
    pass


class InvalidWorkflowStateException(ClarityException):
    """Exception raised when workflow state is invalid."""
    pass


def workflow_not_found_exception() -> HTTPException:
    """Return a standardized workflow not found exception."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Workflow thread not found",
    )


def invalid_workflow_state_exception() -> HTTPException:
    """Return a standardized invalid workflow state exception."""
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid workflow state",
    )
