// Host-owned construction, not a service/facade getter for replacement bars.
// Only an enabled, configured registry component is instantiated. The child's
// facade has the same own-service scope as under the stock bar. QML shares an
// object tree: this preserves API ownership, not a sandbox against hostile QML.
function create(host, ownerId, moduleName, parent, barApi) {
  var owner = String(ownerId || "")
  var id = host.pluginRegistry.resolveEnabledId(String(moduleName || ""))
  var manifest = host.pluginRegistry.installedPlugins[id]
  var entry = host.barWidgetRegistry.widgets[id]
  if (owner !== host.activeBarId
      || !host.pluginHasBarCapabilities(host.pluginRegistry.installedPlugins[owner])
      || !manifest || manifest.__isFirstParty
      || !host.pluginRegistry.isEnabled(id) || !host.barEntryConfigured(id)
      || !entry || !entry.component || !parent || !barApi
      || String(barApi.pluginId) !== id
      || host.pluginRegistry.resolveEnabledId(String(barApi.moduleName)) !== id)
    return null

  var component = Qt.createComponent(Qt.resolvedUrl("OlioHostedBarWidget.qml"))
  if (component.status !== Component.Ready) {
    console.warn("Olio widget host could not load: " + component.errorString())
    return null
  }
  return component.createObject(parent, {
    sourceBar: barApi,
    widgetShell: host.scopedPluginShellForId(id),
    sourceComponent: entry.component
  })
}
