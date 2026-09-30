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
    readonly property var source: host && host.sourceBar ? host.sourceBar : null
    pluginId: source ? source.pluginId : ""
    moduleName: source ? source.moduleName : ""
    shell: host ? host.widgetShell : null
    foreground: source ? source.foreground : "transparent"
    barForeground: source ? source.barForeground : "transparent"
    background: source ? source.background : "transparent"
    urgent: source ? source.urgent : "transparent"
    fontFamily: source ? source.fontFamily : ""
    position: source ? source.position : "top"
    vertical: source ? source.vertical : false
    barSize: source ? source.barSize : 0
    barMargins: source ? source.barMargins : ({})
    transparent: source ? source.transparent : false
    foregroundAnimationEnabled: source ? source.foregroundAnimationEnabled : false
    centerSectionRevealHeld: source ? source.centerSectionRevealHeld : false
    _centerHoverRevealSuppressed: source ? source.centerHoverRevealSuppressed : false
    activePopout: source ? source.activePopout : null
    clickTargets: source ? source.clickTargets : []
    layoutConfig: source ? source.layoutConfig : ({})
    _showTooltip: source ? source._showTooltip : null
    _hideTooltip: source ? source._hideTooltip : null
    _registerClickTarget: source ? source._registerClickTarget : null
    _unregisterClickTarget: source ? source._unregisterClickTarget : null
    _requestPopout: source ? source._requestPopout : null
    _releasePopout: source ? source._releasePopout : null
    _reportPopoutGeometry: source ? source._reportPopoutGeometry : null
    _popoutTransitionFor: source ? source._popoutTransitionFor : null
    _switchPanelFrom: source ? source._switchPanelFrom : null
    _targetBelongsToWindow: source ? source._targetBelongsToWindow : null
    _moduleWidgets: source ? source._moduleWidgets : null
    _run: source ? source._run : null
    _setCenterHoverRevealSuppressed: source ? source._setCenterHoverRevealSuppressed : null
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
