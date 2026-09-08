"""Execute the embedded JavaScript with a small DOM/Plotly contract harness."""

import json
import re
import shutil
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from visualizations.report import SessionReport


@pytest.mark.parametrize("axis_range,values", [([94.5, 79.5], [80, 90, 120]),
                                                ([60, 0], [0, 5, 120]),
                                                ([60, 0], [0, 5, 20]),
                                                ([1, 4], [1, 2, 4])])
def test_slider_initialization_relayout_and_portable_image(tmp_path, axis_range, values):
    if shutil.which("node") is None:
        pytest.skip("Node.js is required for the embedded JavaScript test")
    with patch("visualizations.report._plotly_js", return_value=""):
        html = SessionReport(SimpleNamespace(name="Sprint"), tmp_path).write().read_text()
    script = re.findall(r"<script>(.*?)</script>", html, re.S)[-1]
    fixture = json.dumps({"data": [{"type": "scatter", "mode": "lines", "y": values}],
                          "layout": {"yaxis": {"range": axis_range}}})
    harness = r'''
const assert = require("node:assert/strict");
const figure = FIXTURE;
const descending = figure.layout.yaxis.range[0] > figure.layout.yaxis.range[1];
const events = {};
let controls, imageHandler, opened;
const node = {
  dataset: {plotlySource: "source", reportSection: "Race"},
  parentNode: {insertBefore(value) { controls = value; }},
  on(name, handler) { (events[name] ||= []).push(handler); },
};
const image = {src: "data:image/png;base64,aGVsbG8=", addEventListener(name, fn) {imageHandler = fn;}};
global.document = {
  getElementById() {return {textContent: JSON.stringify(figure)};},
  querySelectorAll(selector) {return selector === ".zoomable-image" ? [image] : [node];},
  createElement() {
    const output = {};
    let inputs;
    return {
      set innerHTML(html) {
        inputs = [...html.matchAll(/<input ([^>]+)>/g)].map(match => {
          const input = Object.fromEntries([...match[1].matchAll(/([\w-]+)="([^"]*)"/g)].map(m => [m[1],m[2]]));
          input.addEventListener = (name, fn) => input.handler = fn;
          return input;
        });
      },
      querySelectorAll() {return inputs;},
      querySelector() {return output;},
    };
  },
};
global.window = {
  open(url, target, features) {opened = {url, target, features};},
  Plotly: {
    newPlot(node, data, layout) {
      node._fullLayout = layout;
      return Promise.resolve();
    },
    relayout(node, update) {
      if (update["yaxis.range"]) node._fullLayout.yaxis.range = update["yaxis.range"];
      for (const callback of events.plotly_relayout || []) callback(update);
      return Promise.resolve();
    },
  },
};
const realSetTimeout = global.setTimeout;
global.setTimeout = () => 1;
SCRIPT
Promise.resolve().then(async () => {
  const inputs = controls.querySelectorAll();
  assert.deepEqual(inputs.map(input => Number(input.value)), [...figure.layout.yaxis.range].sort((a,b)=>a-b));
  inputs[0].value = "10";
  inputs[1].value = "30";
  inputs[0].handler();
  assert.deepEqual(node._fullLayout.yaxis.range, descending ? [30,10] : [10,30]);
  window.Plotly.relayout(node, {"yaxis.range": [22,11]});
  assert.deepEqual(inputs.map(input => Number(input.value)), [11,22]);
  imageHandler();
  assert.ok(opened.url.startsWith("blob:"));
  assert.equal(await (await fetch(opened.url)).text(), "hello");
  assert.equal(opened.features, "noopener,noreferrer");
  URL.revokeObjectURL(opened.url);
}).catch(error => { console.error(error); process.exitCode = 1; });
'''.replace("FIXTURE", fixture).replace("SCRIPT", script)
    result = subprocess.run(["node", "-"], input=harness, text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
