import QtQuick
import QtTest
import qs.Ui
import OlioTest
import "../../themes/olio-su-silicio/shell/OlioHostedWidgets.js" as WidgetHost

Item {
  id: testArea
  width: 400
  height: 100

  QtObject { id: archive; property bool loaded: true }
  QtObject {
    id: ownShell
    function serviceFor(id) { return id === "test.widget" ? archive : null }
  }
  QtObject { id: barShell; function serviceFor(id) { return null } }
  QtObject {
    id: registry
    property var installedPlugins: ({"olio.bar": {id:"olio.bar"}, "test.widget": {id:"test.widget"}})
    function resolveEnabledId(id) { return id }
    function isEnabled(id) { return id === "test.widget" }
  }
  QtObject {
    id: shellHost
    property string activeBarId: "olio.bar"
    property var pluginRegistry: registry
    property var barWidgetRegistry: ({widgets: {"test.widget": {component: widget}}})
    function pluginHasBarCapabilities(manifest) { return manifest && manifest.id === activeBarId }
    function barEntryConfigured(id) { return id === "test.widget" }
    function scopedPluginShellForId(id) { return id === "test.widget" ? ownShell : null }
  }
  PluginBarApi {
    id: source
    pluginId: "test.widget"
    moduleName: "test.widget"
    shell: barShell
    barSize: 36
    barMargins: ({top:9, right:14, bottom:0, left:14})
  }
  Component {
    id: widget
    Item {
      property QtObject bar: null
      property string moduleName: ""
      property var settings: ({})
      readonly property var store: bar ? bar.shell.serviceFor(moduleName) : null
      readonly property bool loaded: store ? store.loaded : false
      implicitWidth: 24
      implicitHeight: bar ? bar.barSize : 0
    }
  }
  OlioHostedBarWidget {
    id: host
    sourceBar: source
    widgetShell: ownShell
    sourceComponent: widget
    widgetSettings: ({keepDays:30})
  }
  TestCase {
    name: "HostedWidget"
    when: windowShown
    function test_real_factory() {
      var created = WidgetHost.create(shellHost, "olio.bar", "test.widget", testArea, source)
      verify(created !== null)
      tryCompare(created, "status", Loader.Ready)
      verify(created.item.loaded)
      compare(source.shell.serviceFor("test.widget"), null)
      created.destroy()
    }
    function test_archive_and_live_bar_bindings() {
      tryCompare(host, "status", Loader.Ready)
      verify(host.item.loaded)
      compare(host.item.store, archive)
      compare(source.shell.serviceFor("test.widget"), null)
      compare(host.item.bar.shell.serviceFor("omarchy.lock"), null)
      compare(host.item.settings.keepDays, 30)
      host.widgetSettings = {keepDays:7}
      compare(host.item.settings.keepDays, 7)
      compare(host.item.bar.barMargins.top, 9)
      source.barMargins = {top:0, right:0, bottom:0, left:0}
      compare(host.item.bar.barMargins.top, 0)
      source.barSize = 40
      compare(host.item.implicitHeight, 40)
      host.sourceComponent = null
      compare(host.item, null)
      host.sourceComponent = widget
      tryCompare(host, "status", Loader.Ready)
      verify(host.item.loaded)
    }
  }
}
