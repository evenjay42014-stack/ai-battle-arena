"""NEXUS — AI Battle Arena engine.

Models do not update weights here. They update a shared playbook:
lesson cards mined from losses, injected into the next fight,
audited on replay. Every AI is on one event bus.
"""

__version__ = "1.0.0"
__arena__ = "NEXUS"
