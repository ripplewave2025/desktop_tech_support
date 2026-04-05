"""
Specialist agent implementations for the multi-agent stack.
"""

from .browser_support_agent import BrowserSupportAgent
from .concierge import ConciergeAgent
from .desktop_navigation_agent import DesktopNavigationAgent
from .files_agent import FilesAgent
from .oem_agent import DellAgent, GenericOEMAgent, HPAgent, LenovoAgent, OEMAgent
from .smart_home_agent import SmartHomeAgent
from .support_case_agent import SupportCaseAgent
from .windows_agent import WindowsAgent

__all__ = [
    "BrowserSupportAgent",
    "ConciergeAgent",
    "DellAgent",
    "DesktopNavigationAgent",
    "FilesAgent",
    "GenericOEMAgent",
    "HPAgent",
    "LenovoAgent",
    "OEMAgent",
    "SmartHomeAgent",
    "SupportCaseAgent",
    "WindowsAgent",
]
