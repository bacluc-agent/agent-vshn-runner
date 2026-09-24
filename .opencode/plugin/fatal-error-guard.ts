import type { Plugin } from "@opencode-ai/plugin";
import type { Event } from "@opencode-ai/sdk";
import { writeFileSync } from "node:fs";
import { classifyEvent } from "../classify.ts"; // .ts extension REQUIRED for Node type stripping

const plugin: Plugin = () => ({
  async event({ event }: { event: Event }) {
    const hit = classifyEvent(event, { model: process.env.MODEL });
    if (!hit) return;

    const marker = {
      reason: hit.reason,
      model: process.env.MODEL ?? "unknown",
      provider: hit.provider ?? "unknown",
      sessionID:
        (event as { properties?: { sessionID?: string } }).properties
          ?.sessionID ?? "unknown",
      error: hit.error ?? null,
      stage: process.env.OPENCODE_FATAL_STAGE ?? "unknown",
      at: new Date().toISOString(),
    };

    const path = `${process.env.RUNNER_TEMP ?? "/tmp"}/opencode-fatal.json`;
    try {
      writeFileSync(path, JSON.stringify(marker));
    } finally {
      process.exit(1); // abort always happens even if the write throws
    }
  },
});

export default plugin;
