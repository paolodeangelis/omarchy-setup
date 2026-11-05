"""Version-pinned host adapters; applied to staging, never /usr/share/omarchy."""
from pathlib import Path
import hashlib
import shutil


SUPPORTED = {
    "shell.qml": {
        "4a4b7694e5b9e0bd952ce0efa2d6dc2cea44cdfa98cc2f442e40fe41cbc1beab",
        "1c390bb1703a8372a7d3a614bc44513b6cc91eee21f4bd507198e8601310e617",
        "d6d99af10ca020ca2c578bc7f67bf674d954efc206012a71af6769c662c37c37",
    },
    "services/PluginShellApi.qml": {
        "ff0cb5ec5fcdda0b21af447b11f07a24e065a3557796639364109aaa2ce5c763",
        "640f250d49a20e69548e93a589e6f11840e1551e5a1af1d968fe11d6ade22558",
    },
    "Commons/Util.qml": {
        "6894c63190973b5dbe50b13b3f7a99dd5770e143699f3aae1650fb65ca3ebe9b",
        "f252d02a43c9ae10d394e1a2e9349a74a81e1c83021314299b182d58c21f3cf6",
    },
    "plugins/notifications/Service.qml": {
        "11665542e70df80ccd3c785a6143dee2daefd2082e4f75c740adc2c9947cf7c2",
        "35a5dfcad2687af5201bf9ec52faadad9b4a5000fb74e43756ed02299385c6b6",
    },
}


def validate_sources(shell: Path) -> None:
    for name, expected in SUPPORTED.items():
        source = shell / name
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() not in expected:
            raise ValueError(f"unvalidated Omarchy host interface: {name}; keep the working shell")


def _replace(path: Path, old: str, new: str) -> None:
    source = path.read_text()
    if source.count(old) != 1:
        raise ValueError(f"ambiguous Omarchy compatibility marker: {path.name}")
    path.write_text(source.replace(old, new, 1))


def install(shell: Path, templates: Path) -> None:
    validate_sources(shell)
    for name in (
        "OlioHostedWidgets.js", "OlioHostedBarWidget.qml", "ArtworkInfo.qml",
        "ArtworkInfoIcon.svg",
    ):
        shutil.copy2(templates / name, shell / "services" / name)
    legacy_source_dir_filter = "    delete copy.__sourceDir\n"
    if legacy_source_dir_filter in (shell / "shell.qml").read_text():
        _replace(shell / "shell.qml", legacy_source_dir_filter,
                 "    // Preserve bundled script discovery for third-party plugins.\n")
    _replace(shell / "shell.qml", 'import "services"\n',
             'import "services"\nimport "services/OlioHostedWidgets.js" as OlioHostedWidgets\n')
    _replace(shell / "shell.qml", "ShellRoot {\n  id: shell\n",
             "ShellRoot {\n  id: shell\n\n  ArtworkInfo { }\n")
    marker = "      _barEntryShellLookup: function(ownerId, moduleName) {\n"
    _replace(shell / "shell.qml", marker,
             "      _createBarWidget: function(moduleName, parent, barApi) {\n"
             "        return hasCurrentBarCapabilities()\n"
             "          ? OlioHostedWidgets.create(shell, key, moduleName, parent, barApi) : null\n"
             "      },\n" + marker)
    api = shell / "services" / "PluginShellApi.qml"
    _replace(api, "  property var _barEntryShellLookup: null\n",
             "  property var _barEntryShellLookup: null\n  property var _createBarWidget: null\n")
    _replace(api, "  function serviceFor(id) {\n",
             "  function createBarWidget(moduleName, parent, barApi) {\n"
             "    return _createBarWidget ? _createBarWidget(moduleName, parent, barApi) : null\n"
             "  }\n\n  function serviceFor(id) {\n")
    util = shell / "Commons" / "Util.qml"
    _replace(util, '["bash", "-lc", command]', '["bash", "-c", command]')
    _replace(util, '["bash", "-lc", \'exec "$@"\', "bash"]',
             '["bash", "-c", \'exec "$@"\', "bash"]')
    notification_service = shell / "plugins/notifications/Service.qml"
    legacy_notification_marker = (
        "      readonly property var popupPlacement: NotificationLogic.popupPlacement(\n"
        "        service.barPosition, service.barClearance, Style.gapsOut)"
    )
    if legacy_notification_marker in notification_service.read_text():
        _replace(notification_service,
             legacy_notification_marker,
             "      readonly property var popupPlacement: service.shell && service.shell.bar\n"
             "        && service.shell.bar.notificationPlacement !== undefined\n"
             "        ? service.shell.bar.notificationPlacement\n"
             "        : NotificationLogic.popupPlacement(\n"
             "            service.barPosition, service.barClearance, Style.gapsOut)")
