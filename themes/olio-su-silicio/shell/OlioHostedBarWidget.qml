import QtQuick
import qs.Ui

// The shell creates this loader from its registry, never a caller-supplied URL.
// Its private adapter leaves the replacement bar's service-less facade intact.
Loader {
  id: host
  required property QtObject sourceBar
  required property QtObject widgetShell
  property var widgetSettings: ({})
  anchors.fill: parent

  PluginBarApi {
    id: widgetBar
    pluginId: host.sourceBar.pluginId
    moduleName: host.sourceBar.moduleName
    shell: host.widgetShell
    foreground: host.sourceBar.foreground
    barForeground: host.sourceBar.barForeground
    background: host.sourceBar.background
    urgent: host.sourceBar.urgent
    fontFamily: host.sourceBar.fontFamily
    position: host.sourceBar.position
    vertical: host.sourceBar.vertical
    barSize: host.sourceBar.barSize
    barMargins: host.sourceBar.barMargins
    transparent: host.sourceBar.transparent
    foregroundAnimationEnabled: host.sourceBar.foregroundAnimationEnabled
    centerSectionRevealHeld: host.sourceBar.centerSectionRevealHeld
    _centerHoverRevealSuppressed: host.sourceBar.centerHoverRevealSuppressed
    activePopout: host.sourceBar.activePopout
    clickTargets: host.sourceBar.clickTargets
    layoutConfig: host.sourceBar.layoutConfig
    _showTooltip: host.sourceBar._showTooltip
    _hideTooltip: host.sourceBar._hideTooltip
    _registerClickTarget: host.sourceBar._registerClickTarget
    _unregisterClickTarget: host.sourceBar._unregisterClickTarget
    _requestPopout: host.sourceBar._requestPopout
    _releasePopout: host.sourceBar._releasePopout
    _reportPopoutGeometry: host.sourceBar._reportPopoutGeometry
    _popoutTransitionFor: host.sourceBar._popoutTransitionFor
    _switchPanelFrom: host.sourceBar._switchPanelFrom
    _targetBelongsToWindow: host.sourceBar._targetBelongsToWindow
    _moduleWidgets: host.sourceBar._moduleWidgets
    _run: host.sourceBar._run
    _setCenterHoverRevealSuppressed: host.sourceBar._setCenterHoverRevealSuppressed
  }

  function inject() {
    if (!item) return
    if ("moduleName" in item) item.moduleName = widgetBar.moduleName
    if ("settings" in item) item.settings = host.widgetSettings
    if ("bar" in item) item.bar = widgetBar
  }
  onLoaded: inject()
  onWidgetSettingsChanged: inject()
}
