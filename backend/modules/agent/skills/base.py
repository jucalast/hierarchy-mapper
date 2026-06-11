from abc import ABC, abstractmethod
from typing import List, Dict, Any

class AgentSkill(ABC):
    """
    Abstract base class for all agent skills.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the skill."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what the skill does."""
        pass
    
    @property
    @abstractmethod
    def allowed_tools(self) -> List[str]:
        """List of tools this skill is allowed to use."""
        pass
    
    @property
    @abstractmethod
    def core_tools(self) -> List[str]:
        """List of tools that MUST be executed first to gather context."""
        pass
    
    @abstractmethod
    def get_instructions(self, context: Dict[str, Any]) -> str:
        """
        Get the instructions for the agent based on the provided context.
        
        Args:
            context: Dictionary containing task context and parameters.
            
        Returns:
            String containing the formatted instructions.
        """
        pass

    @abstractmethod
    def get_suggestion_rules(self) -> str:
        """
        Returns specific business rules for generating next actions (suggest_next_actions)
        in the final step of the agent's cycle.
        """
        pass
