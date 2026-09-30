"""Behavior tests for the overlay's host boundary (not a desktop/VM test)."""
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which("node"), "Node is required for QML JavaScript behavior tests")
class ThemeHostTests(unittest.TestCase):
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

    def test_bar_commands_preserve_overlay_environment(self):
        source = (ROOT / "themes/olio-su-silicio/plugins/olio.bar/Bar.qml").read_text()
        start = source.index("  function run(command) {")
        end = source.index("\n  function toggleTransparency", start)
        runner = source[start:end]
        self.assertIn('Quickshell.execDetached(["bash", "-c", command])', runner)
        self.assertNotIn("Util.execDetached(command)", runner)

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
const result = context.create(host, 'olio.bar', 'test.widget', {}, bar);
assert.equal(result.props.sourceComponent, component);
assert.equal(result.props.widgetShell.serviceFor('test.widget'), ownService);
assert.equal(result.props.widgetShell.serviceFor('other.widget'), null);
assert.equal(result.props.widgetShell.serviceFor('omarchy.lock'), null);
assert.equal(bar.shell.serviceFor('test.widget'), null); // bar's facade unchanged
host.pluginRegistry.isEnabled = () => false;
assert.equal(context.create(host, 'olio.bar', 'test.widget', {}, bar), null);
assert.equal(calls.length, 1);
"""
        result = subprocess.run(
            ["node", "-e", script, str(ROOT / "themes/olio-su-silicio/shell/OlioHostedWidgets.js")],
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
