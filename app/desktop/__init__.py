"""Desktop UI and Window Management."""


def __getattr__(name: str):
    if name == "DesktopPetWindow":
        from app.desktop.pet_window import DesktopPetWindow
        return DesktopPetWindow
    elif name == "SystemTrayManager":
        from app.desktop.tray_icon import SystemTrayManager
        return SystemTrayManager
    elif name == "FloatingControlBar":
        from app.desktop.control_bar import FloatingControlBar
        return FloatingControlBar
    elif name == "FloatingChatWindow":
        from app.desktop.chat_window import FloatingChatWindow
        return FloatingChatWindow
    elif name == "SettingsDialog":
        from app.desktop.settings_dialog import SettingsDialog
        return SettingsDialog
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DesktopPetWindow",
    "SystemTrayManager",
    "FloatingControlBar",
    "FloatingChatWindow",
    "SettingsDialog",
]
