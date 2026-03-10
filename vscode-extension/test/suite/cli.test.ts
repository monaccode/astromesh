import * as assert from "assert";
import { AstromeshCli } from "../../src/cli";

suite("AstromeshCli", () => {
  test("parseJsonOutput handles valid JSON", () => {
    const cli = new AstromeshCli("astromeshctl");
    const result = cli.parseJsonOutput('{"version":"0.13.0"}');
    assert.deepStrictEqual(result, { version: "0.13.0" });
  });

  test("parseJsonOutput returns null for invalid JSON", () => {
    const cli = new AstromeshCli("astromeshctl");
    const result = cli.parseJsonOutput("not json");
    assert.strictEqual(result, null);
  });

  test("buildArgs constructs correct argument list", () => {
    const cli = new AstromeshCli("astromeshctl");
    const args = cli.buildArgs("run", ["my-agent", "hello"], { json: true, timeout: "30" });
    assert.deepStrictEqual(args, ["run", "my-agent", "hello", "--json", "--timeout", "30"]);
  });

  test("buildArgs omits flags with false values", () => {
    const cli = new AstromeshCli("astromeshctl");
    const args = cli.buildArgs("doctor", [], { json: false });
    assert.deepStrictEqual(args, ["doctor"]);
  });
});
