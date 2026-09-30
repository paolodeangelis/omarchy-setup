"""Offscreen Qt proof; no desktop session, services, packages, or user data."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
RUNNER = Path("/usr/lib/qt6/bin/qmltestrunner")
STOCK_API = Path("/usr/share/omarchy/shell/Ui/PluginBarApi.qml")


@unittest.skipUnless(RUNNER.is_file() and STOCK_API.is_file(), "requires Qt Quick Test and installed Omarchy UI API")
class ThemeQmlTests(unittest.TestCase):
    def test_hosted_widget_loads_archive_without_exposing_service_to_bar(self):
        with tempfile.TemporaryDirectory(prefix="olio-qml-test-") as temporary:
            root = Path(temporary)
            imports = root / "imports"
            ui = imports / "qs" / "Ui"
            ui.mkdir(parents=True)
            # Stock API plus exactly the compatibility extensions installed by
            # the overlay builder.
            api = STOCK_API.read_text().replace("  property int barSize: 0\n",
                "  property int barSize: 0\n  property var barMargins: ({})\n", 1)
            api = api.replace(
                "  property var _releasePopout: null\n",
                "  property var _releasePopout: null\n"
                "  property var _reportPopoutGeometry: null\n"
                "  property var _popoutTransitionFor: null\n",
                1,
            )
            (ui / "PluginBarApi.qml").write_text(api)
            (ui / "qmldir").write_text("module qs.Ui\nPluginBarApi 1.0 PluginBarApi.qml\n")
            module = imports / "OlioTest"
            module.mkdir()
            shutil.copy2(ROOT / "themes/olio-su-silicio/shell/OlioHostedBarWidget.qml", module)
            (module / "qmldir").write_text("module OlioTest\nOlioHostedBarWidget 1.0 OlioHostedBarWidget.qml\n")
            environment = os.environ.copy()
            environment.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                               QT_QPA_PLATFORMTHEME="", QT_QUICK_CONTROLS_STYLE="Basic",
                               HOME=str(root), XDG_RUNTIME_DIR=str(root), XDG_CACHE_HOME=str(root / "cache"))
            result = subprocess.run([str(RUNNER), "-input", str(ROOT / "tests/qml"), "-import", str(imports)],
                                    env=environment, text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("QWARN", result.stdout + result.stderr)
