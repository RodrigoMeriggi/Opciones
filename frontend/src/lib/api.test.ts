/** @vitest-environment node */
import { describe, expect, it } from "vitest";

describe("api helpers", () => {
  it("builds default API base", async () => {
    const mod = await import("./api");
    expect(mod.API_BASE).toContain("http");
  });
});
