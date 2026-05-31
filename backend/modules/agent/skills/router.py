from typing import Any
from .base import AgentSkill

from .skill_prospecting import ProspectingSkill
from .skill_outreach import OutreachSkill
from .skill_followup import FollowUpSkill


def route_task_to_skill(task_type: str, task_subject: str) -> AgentSkill:
    """
    Examines task_type and task_subject to return the appropriate AgentSkill.
    """
    subject_lower = task_subject.lower()
    
    # ProspectingSkill routing rules
    if any(keyword in subject_lower for keyword in ["encontrar contato", "decisor", "mapear"]):
        return ProspectingSkill()
        
    # OutreachSkill routing rules
    if any(keyword in subject_lower for keyword in ["apresentação", "apresentar"]):
        return OutreachSkill()
        
    # FollowUpSkill routing rules
    if any(keyword in subject_lower for keyword in ["follow-up", "follow up", "cobrar", "ligar"]):
        return FollowUpSkill()
        
    # Default
    return FollowUpSkill()
