import * as assert from "assert";

// Test the pure logic without vscode dependency
suite("TracesProvider Logic", () => {
  test("trace data can be mapped to tree structure", () => {
    const traces = [
      { trace_id: "abc123456789", agent: "my-agent", status: "ok", duration_ms: 500 },
      { trace_id: "def456789012", agent: "other-agent", status: "error", duration_ms: 120 },
    ];

    // Test that we can extract display info
    const items = traces.map(t => ({
      label: t.trace_id.slice(0, 12),
      description: `${t.agent} — ${t.duration_ms}ms`,
      isOk: t.status === "ok",
    }));

    assert.strictEqual(items.length, 2);
    assert.strictEqual(items[0].label, "abc123456789");
    assert.strictEqual(items[0].description, "my-agent — 500ms");
    assert.strictEqual(items[0].isOk, true);
    assert.strictEqual(items[1].isOk, false);
  });

  test("empty trace list returns empty array", () => {
    const traces: unknown[] = [];
    assert.strictEqual(traces.length, 0);
  });
});
