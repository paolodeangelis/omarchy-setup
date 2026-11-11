"""Behavior tests for the overlay's host boundary (not a desktop/VM test)."""
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which("node"), "Node is required for QML JavaScript behavior tests")
class ThemeHostTests(unittest.TestCase):
    def test_shell_config_loads_before_plugin_discovery_without_replacing_stock_persistence(self):
        host = (ROOT / "src/omarchy_setup/modules/theme/host_integration.py").read_text()
        self.assertNotIn('"ShellConfigStore.qml"', host)
        self.assertNotIn("shellConfigStore", host)
        self.assertEqual(host.count('"    blockLoading: true\\n"'), 2)
        self.assertIn("shell.loadDefaults(defaultsFile.text())", host)

    def test_plugin_facades_guard_owner_destruction(self):
        bar = (ROOT / "themes/olio-su-silicio/plugins/olio.bar/Bar.qml").read_text()
        self.assertIn("function(target) { if (root) root.hideTooltip(target) }", bar)
        self.assertIn("if (!target || !root) return", bar)
        self.assertIn("if (!root || !slot) return", bar)
        self.assertIn('if (!root.shell || typeof root.shell.createBarWidget !== "function") return', bar)
        self.assertEqual(bar.count('typeof hostedLoader.reload === "function"'), 3)
        self.assertNotIn("Qt.callLater(hostedLoader.reload)", bar)
        self.assertIn("onBarConfigChanged: applyBarConfig()", bar)
        self.assertIn("Component.onCompleted: applyBarConfig()", bar)
        self.assertNotIn("shellConfigReady", bar)
        self.assertIn("api, slot.moduleSettings)", bar)
        self.assertIn("if (!slot.firstParty)", bar)
        hosted = (ROOT / "themes/olio-su-silicio/shell/OlioHostedBarWidget.qml").read_text()
        self.assertIn("readonly property var source: host && host.sourceBar", hosted)
        self.assertNotIn("pluginId: host.sourceBar.pluginId", hosted)

    def test_registry_loader_never_receives_an_undefined_component(self):
        bar = (ROOT / "themes/olio-su-silicio/plugins/olio.bar/Bar.qml").read_text()
        self.assertIn("w[registryName] && w[registryName].component ? w[registryName].component : null", bar)
        self.assertIn("sourceComponent: active ? ((slot.commandCustom ? customCommandModuleComponent : emptyModuleComponent) || null) : null", bar)

    def test_fixed_popups_share_numeric_transition_geometry(self):
        source = (ROOT / "themes/olio-su-silicio/plugins/olio.bar/Bar.qml").read_text()
        self.assertIn("function reportPopoutGeometry(owner, geometry)", source)
        self.assertIn("activePopout !== owner", source)
        self.assertIn("function popoutTransitionFor(screenName)", source)
        panel = (ROOT / "themes/olio-su-silicio/shell/KeyboardPanel.qml").read_text()
        self.assertIn("visualWidth = Number(previous.width)", panel)
        self.assertIn('visualY = barPos === "top" ? gap : cardOrigin.y', panel)
        self.assertIn("Behavior on width", panel)
        self.assertIn("Behavior on height", panel)
        self.assertIn("typeof bar.popoutTransitionFor", panel)

    def test_45_bar_sections_fold_into_the_accepted_three_section_layout(self):
        bar = (ROOT / "themes/olio-su-silicio/plugins/olio.bar/Bar.qml").read_text()
        self.assertIn("normalized.centerBegin || []", bar)
        self.assertIn("normalized.centerEnd || []", bar)
        self.assertIn("normalized.tray || []", bar)
        self.assertIn("function barSizeFor(screenName)", bar)

    def test_bar_commands_preserve_overlay_environment(self):
        source = (ROOT / "themes/olio-su-silicio/plugins/olio.bar/Bar.qml").read_text()
        start = source.index("  function run(command) {")
        end = source.index("\n  function toggleTransparency", start)
        runner = source[start:end]
        self.assertIn('Quickshell.execDetached(["bash", "-c", command])', runner)
        self.assertNotIn("Util.execDetached(command)", runner)

    def test_tray_double_click_does_not_reach_bar_background_gesture(self):
        tray = (ROOT / "themes/olio-su-silicio/plugins/olio.bar/widgets/Tray.qml").read_text()
        self.assertIn("onDoubleClicked: function(mouse) { mouse.accepted = true }", tray)

    def test_supported_trays_are_pinned_to_the_inner_bar_edge(self):
        model = (ROOT / "themes/olio-su-silicio/plugins/olio.bar/BarModel.js").read_text()
        self.assertIn('"omarchy.tray", "io.github.tyrichards.tray"', model)

    def test_plugin_bar_api_uses_the_configured_olio_transparency(self):
        bar = (ROOT / "themes/olio-su-silicio/plugins/olio.bar/Bar.qml").read_text()
        self.assertIn('api.transparent = Qt.binding(function() { return root.transparent })', bar)
        self.assertNotIn('api.pluginId === "io.github.tyrichards.tray"', bar)

    def test_module_double_clicks_do_not_reach_bar_background_gesture(self):
        bar = (ROOT / "themes/olio-su-silicio/plugins/olio.bar/Bar.qml").read_text()
        self.assertIn('onDoubleClicked: function(mouse) { mouse.accepted = true }', bar)

    def test_toasts_match_existing_popup_offset_in_both_modes(self):
        script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const text = fs.readFileSync(process.argv[1], 'utf8');
const start = text.indexOf('  readonly property int popupClearance:');
assert.ok(start >= 0);
const end = text.indexOf('\n  function normalizePosition', start);
const source = text.slice(start, end).replace(/readonly property (int|var) (\w+):/g, 'var $2 =');
for (const floating of [true, false]) {
  const context = {barSize:36, islandEdgeMargin:floating?9:0,
    floatingPopupGap:1, floatingStyle:floating, Style:{gapsOut:5}, position:'top'};
  vm.createContext(context); vm.runInContext(source, context);
  const expected = 36 + context.islandEdgeMargin + (floating ? 1 : 6);
  assert.equal(context.notificationPlacement.margins.top, expected);
  assert.equal(context.notificationPlacement.margins.right, 5);
}
"""
        result = subprocess.run(["node", "-e", script, str(ROOT / "themes/olio-su-silicio/plugins/olio.bar/Bar.qml")], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_host_owns_widget_creation_and_keeps_service_scope(self):
        script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const calls = [];
const context = {Qt: {
  resolvedUrl: value => value,
  createComponent: () => ({status: 1, createObject: (parent, props) => {
    calls.push(props); return {parent, props};
  }})
}, Component: {Ready: 1}};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
const ownService = {};
const component = {};
const host = {
  activeBarId: 'olio.bar',
  pluginHasBarCapabilities: m => m && m.id === 'olio.bar',
  barEntryConfigured: id => id === 'test.widget',
  pluginRegistry: {
    installedPlugins: {'olio.bar': {id:'olio.bar'}, 'test.widget': {id:'test.widget'}},
    resolveEnabledId: id => id,
    isEnabled: id => id === 'test.widget'
  },
  barWidgetRegistry: {widgets: {'test.widget': {component}}},
  scopedPluginShellForId: id => ({serviceFor: requested => requested === id ? ownService : null})
};
const bar = {pluginId:'test.widget', moduleName:'test.widget', shell:{serviceFor:()=>null}};
assert.equal(context.create(host, 'other.bar', 'test.widget', {}, bar), null);
assert.equal(context.create(host, 'olio.bar', 'other.widget', {}, bar), null);
assert.equal(context.create(host, 'olio.bar', 'test.widget', {}, {pluginId:'forged'}), null);
assert.equal(calls.length, 0);
const settings = {value: 1};
const result = context.create(host, 'olio.bar', 'test.widget', {}, bar, settings);
assert.equal(result.props.sourceComponent, component);
assert.equal(result.props.widgetShell.serviceFor('test.widget'), ownService);
assert.equal(result.props.widgetShell.serviceFor('other.widget'), null);
assert.equal(result.props.widgetShell.serviceFor('omarchy.lock'), null);
assert.equal(bar.shell.serviceFor('test.widget'), null); // bar's facade unchanged
host.pluginRegistry.isEnabled = () => false;
assert.equal(context.create(host, 'olio.bar', 'test.widget', {}, bar), null);
assert.equal(calls.length, 1);

host.pluginRegistry.isEnabled = id => id === 'first.widget';
host.pluginRegistry.installedPlugins['first.widget'] = {id:'first.widget', __isFirstParty:true};
host.barWidgetRegistry.widgets['first.widget'] = {component: {createObject:(parent, props)=>({parent, props})}};
host.barEntryConfigured = id => id === 'first.widget';
const firstBar = {barSize: 32};
const first = context.create(host, 'olio.bar', 'first.widget', {}, firstBar, settings);
assert.equal(first.props.settings, settings);
assert.equal(first.props.moduleName, 'first.widget');
assert.equal(first.props.bar, firstBar);
"""
        result = subprocess.run(
            ["node", "-e", script, str(ROOT / "themes/olio-su-silicio/shell/OlioHostedWidgets.js")],
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
