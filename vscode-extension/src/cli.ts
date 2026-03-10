import { spawn } from "child_process";

export interface CliResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}

export class AstromeshCli {
  constructor(private readonly cliPath: string) {}

  parseJsonOutput(output: string): unknown | null {
    try {
      return JSON.parse(output);
    } catch {
      return null;
    }
  }

  buildArgs(
    command: string,
    positional: string[],
    flags: Record<string, string | boolean> = {}
  ): string[] {
    const args = [command, ...positional];
    for (const [key, value] of Object.entries(flags)) {
      if (value === false) continue;
      args.push(`--${key}`);
      if (typeof value === "string") {
        args.push(value);
      }
    }
    return args;
  }

  exec(
    command: string,
    positional: string[] = [],
    flags: Record<string, string | boolean> = {}
  ): Promise<CliResult> {
    const args = this.buildArgs(command, positional, flags);
    return new Promise((resolve) => {
      const proc = spawn(this.cliPath, args, { shell: true });
      let stdout = "";
      let stderr = "";
      proc.stdout.on("data", (data) => (stdout += data.toString()));
      proc.stderr.on("data", (data) => (stderr += data.toString()));
      proc.on("close", (code) => {
        resolve({ stdout, stderr, exitCode: code ?? 1 });
      });
      proc.on("error", () => {
        resolve({ stdout, stderr, exitCode: 1 });
      });
    });
  }

  async execJson(
    command: string,
    positional: string[] = [],
    flags: Record<string, string | boolean> = {}
  ): Promise<{ data: unknown | null; error: string | null }> {
    const result = await this.exec(command, positional, { ...flags, json: true });
    if (result.exitCode !== 0) {
      return { data: null, error: result.stderr || `Exit code ${result.exitCode}` };
    }
    const data = this.parseJsonOutput(result.stdout);
    return { data, error: data === null ? "Failed to parse JSON output" : null };
  }
}
