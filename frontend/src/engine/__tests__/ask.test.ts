import { describe, expect, it } from "vitest";
import { citations, SUGGESTIONS } from "../../components/AskPanel";

describe("ask the city", () => {
  it("turns [n] in an answer into citation numbers", () => {
    expect(citations("Two babies were born [1] and a theft [3].")).toEqual(["Two babies were born ", 1, " and a theft ", 3, "."]);
    expect(citations("[2][4]")).toEqual([2, 4]);
    expect(citations("No sources here.")).toEqual(["No sources here."]);
  });

  it("offers short suggestions", () => {
    expect(SUGGESTIONS.length).toBeGreaterThan(3);
    for (const s of SUGGESTIONS) expect(s.endsWith("?")).toBe(true);
  });
});
