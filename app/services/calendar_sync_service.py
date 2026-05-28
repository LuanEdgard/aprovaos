"""Future integration point for external calendar providers.

This MVP keeps all scheduling inside the internal AprovaOS calendar.
When we enable external sync (Google, Outlook, etc.), this module should
host provider-specific adapters and conflict-resolution logic.
"""


def sync_calendar_events(*args, **kwargs):
    """Placeholder for future external calendar synchronization."""
    return {
        "enabled": False,
        "message": "Sincronização externa ainda não habilitada no MVP.",
        "todo": "Implement provider OAuth and bidirectional event sync.",
    }
