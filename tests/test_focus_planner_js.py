import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "webapp" / "templates" / "index.html"

BROWSER_SIMULATION = r"""
let fakeNow = 1000000;
Date.now = () => fakeNow;

const elements = {};

class FakeElement {
    constructor(id) {
        this.id = id;
        this.value = id === "focus-duration" ? "25" : "25";
        this.textContent = "";
        this.disabled = false;
        this.hidden = false;
        this.listeners = {};
    }

    addEventListener(type, callback) {
        (this.listeners[type] ||= []).push(callback);
    }

    async fire(type) {
        for (const callback of this.listeners[type] || []) {
            await callback({type, target: this});
        }
    }

    async click() {
        await this.fire("click");
    }

    focus() {}
}

for (const id of [
    "focus-duration",
    "focus-custom-duration",
    "focus-custom-minutes",
    "focus-countdown",
    "focus-status",
    "focus-start",
    "focus-pause",
    "focus-cancel",
    "logout-button"
]) {
    elements[id] = new FakeElement(id);
}

const storage = new Map();

globalThis.sessionStorage = {
    getItem(key) {
        return storage.has(key) ? storage.get(key) : null;
    },
    setItem(key, value) {
        storage.set(key, String(value));
    },
    removeItem(key) {
        storage.delete(key);
    }
};

const intervals = new Map();
let nextIntervalId = 1;

globalThis.setInterval = (callback, milliseconds) => {
    const id = nextIntervalId++;
    intervals.set(id, {callback, milliseconds});
    return id;
};

globalThis.clearInterval = id => intervals.delete(id);

const documentListeners = {};
const windowListeners = {};

globalThis.document = {
    hidden: false,

    getElementById(id) {
        return elements[id] || null;
    },

    addEventListener(type, callback) {
        (documentListeners[type] ||= []).push(callback);
    },

    async fire(type) {
        for (const callback of documentListeners[type] || []) {
            await callback({type});
        }
    }
};

globalThis.fakeWindow = {
    addEventListener(type, callback) {
        (windowListeners[type] ||= []).push(callback);
    },

    async fire(type) {
        for (const callback of windowListeners[type] || []) {
            await callback({type});
        }
    }
};

function assert(condition, message) {
    if (!condition) {
        throw new Error("ASSERTION FAILED: " + message);
    }
}

function equal(actual, expected, message) {
    assert(
        actual === expected,
        `${message}; expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`
    );
}

async function advance(milliseconds) {
    fakeNow += milliseconds;

    // Execute the normal countdown tick, not browser-event handlers.
    for (const timer of intervals.values()) {
        if (timer.milliseconds === 250) {
            await timer.callback();
        }
    }
}

async function startTimer() {
    await elements["focus-start"].click();
}

function savedState() {
    return JSON.parse(storage.get("codetime_focus_timer_v1") || "null");
}
"""


class TestFocusPlannerJavaScript(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("gjs"):
            raise unittest.SkipTest("GJS is not installed.")

        html = TEMPLATE.read_text(encoding="utf-8")

        match = re.search(
            r'<script>\s*\(\(\) => \{\s*const KEY = '
            r'"codetime_focus_timer_v1";.*?</script>',
            html,
            re.DOTALL,
        )

        if not match:
            raise AssertionError(
                "Could not find the actual Focus Planner JavaScript in index.html"
            )

        cls.timer_script = match.group(0)
        cls.timer_script = re.sub(
            r"^<script>\s*|\s*</script>$",
            "",
            cls.timer_script,
        )

    def run_javascript(self, scenario, initial_state=None):
        setup = ""

        if initial_state is not None:
            setup = (
                'storage.set("codetime_focus_timer_v1", '
                + json.dumps(json.dumps(initial_state))
                + ");\n"
            )

        script = (
            BROWSER_SIMULATION
            + setup
            + self.timer_script.replace("window.", "fakeWindow.")
            + "\n;(async () => {\n"
            + scenario
              + '\nprint("PASS");\n})().catch(error => {'
              + 'printerr(String(error) + "\\n" + (error.stack || ""));'
              + '\nimports.system.exit(1);'
              + '\n});\n'
          )

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".js",
            encoding="utf-8",
        ) as temporary:
            temporary.write(script)
            temporary.flush()

            result = subprocess.run(
                ["gjs", temporary.name],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

        self.assertEqual(
            result.returncode,
            0,
            msg=f"GJS test failed:\n{result.stdout}\n{result.stderr}",
        )
        self.assertIn("PASS", result.stdout)

    def test_start_displays_countdown_and_saves_state(self):
        self.run_javascript(r"""
            equal(elements["focus-countdown"].textContent, "25:00",
                  "Initial duration should be displayed");

            await startTimer();

            equal(elements["focus-countdown"].textContent, "25:00",
                  "Starting should display the full duration");
            equal(elements["focus-status"].textContent,
                  "Focus session in progress",
                  "Running status should be displayed");
            equal(savedState().mode, "running",
                  "Running state should be saved");
            assert(elements["focus-start"].disabled,
                   "Start should be disabled while running");

            await advance(60000);

            equal(elements["focus-countdown"].textContent, "24:00",
                  "Countdown should decrease after one minute");
        """)

    def test_pause_and_resume_preserve_remaining_time(self):
        self.run_javascript(r"""
            await startTimer();
            await advance(60000);
            await elements["focus-pause"].click();

            equal(savedState().mode, "paused",
                  "Pausing should save paused state");
            equal(elements["focus-countdown"].textContent, "24:00",
                  "Pause should preserve the remaining time");
            equal(elements["focus-pause"].textContent, "Resume",
                  "Pause button should become Resume");

            await advance(120000);

            equal(elements["focus-countdown"].textContent, "24:00",
                  "A paused countdown should not decrease");

            await elements["focus-pause"].click();

            equal(savedState().mode, "running",
                  "Resuming should restore running state");

            await advance(60000);

            equal(elements["focus-countdown"].textContent, "23:00",
                  "Countdown should continue after resuming");
        """)

    def test_expired_timer_finishes_on_visibility_change(self):
        self.run_javascript(r"""
            await startTimer();
            await advance(25 * 60 * 1000);

            document.hidden = false;
            await document.fire("visibilitychange");

            equal(savedState().mode, "finished",
                  "Returning to the visible page should finish an expired timer");
            equal(elements["focus-countdown"].textContent, "00:00",
                  "Finished countdown should show zero");
            assert(elements["focus-status"].textContent.includes("time is up"),
                   "Completion message should be displayed");
            assert(!elements["focus-start"].disabled,
                   "Starting another session should be allowed");
        """)

    def test_expired_timer_finishes_on_pageshow(self):
        self.run_javascript(r"""
            await startTimer();
            fakeNow += 25 * 60 * 1000;

            await fakeWindow.fire("pageshow");

            equal(savedState().mode, "finished",
                  "pageshow should finish an expired timer");
            equal(elements["focus-countdown"].textContent, "00:00",
                  "pageshow should reconcile the countdown");
        """)

    def test_cancel_clears_timer_state(self):
        self.run_javascript(r"""
            await startTimer();

            assert(savedState() !== null,
                   "Starting should save the timer state");

            await elements["focus-cancel"].click();

            equal(savedState(), null,
                  "Cancel should remove saved timer state");
            equal(elements["focus-countdown"].textContent, "25:00",
                  "Cancel should restore the selected duration");
            equal(elements["focus-status"].textContent, "Ready to focus",
                  "Cancel should restore the ready status");
            assert(elements["focus-start"].disabled === false,
                   "Start should be enabled after cancellation");
            assert(elements["focus-cancel"].disabled,
                   "Cancel should be disabled when no timer exists");
        """)


if __name__ == "__main__":
    unittest.main(verbosity=2)
