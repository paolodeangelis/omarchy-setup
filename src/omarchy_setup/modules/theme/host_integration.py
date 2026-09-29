"""Version-pinned host adapters; applied to staging, never /usr/share/omarchy."""
from pathlib import Path
import hashlib
import shutil


SUPPORTED = {
    "shell.qml": "4a4b7694e5b9e0bd952ce0efa2d6dc2cea44cdfa98cc2f442e40fe41cbc1beab",
    "services/PluginShellApi.qml": "ff0cb5ec5fcdda0b21af447b11f07a24e065a3557796639364109aaa2ce5c763",
    "plugins/notifications/Service.qml": "11665542e70df80ccd3c785a6143dee2daefd2082e4f75c740adc2c9947cf7c2",
}


def validate_sources(shell: Path) -> None:
    for name, expected in SUPPORTED.items():
        source = shell / name
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError(f"unvalidated Omarchy host interface: {name}; keep the working shell")


def _replace(path: Path, old: str, new: str) -> None:
    source = path.read_text()
    if source.count(old) != 1:
        raise ValueError(f"ambiguous Omarchy compatibility marker: {path.name}")
    path.write_text(source.replace(old, new, 1))


def install(shell: Path, templates: Path) -> None:
    validate_sources(shell)
    for name in ("OlioHostedWidgets.js", "OlioHostedBarWidget.qml"):
        shutil.copy2(templates / name, shell / "services" / name)
    _replace(shell / "shell.qml", 'import "services"\n',
             'import "services"\nimport "services/OlioHostedWidgets.js" as OlioHostedWidgets\n')
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
    _replace(shell / "plugins/notifications/Service.qml",
             "      readonly property var popupPlacement: NotificationLogic.popupPlacement(\n"
             "        service.barPosition, service.barClearance, Style.gapsOut)",
             "      readonly property var popupPlacement: service.shell && service.shell.bar\n"
             "        && service.shell.bar.notificationPlacement !== undefined\n"
             "        ? service.shell.bar.notificationPlacement\n"
             "        : NotificationLogic.popupPlacement(\n"
             "            service.barPosition, service.barClearance, Style.gapsOut)")
