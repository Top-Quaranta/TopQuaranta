import { describe, it, expect } from "vitest";

import { indexaStats } from "./mapaStats";

// Shape copied from GET /api/v1/mapa/stats/?level=municipi (2026-11-20).
const FILA = { codi: "CAT", comarca: "Barcelonès", municipi: "Barcelona", n_artistes: 700 };

describe("indexaStats", () => {
  it("troba un municipi amb la clau que fa servir el mapa", () => {
    expect(indexaStats([FILA], "municipi")["CAT::Barcelonès::Barcelona"].n_artistes).toBe(700);
  });
  it("troba un territori pel seu codi", () => {
    expect(indexaStats([{ codi: "VAL", n_artistes: 307 }], "territori").VAL.n_artistes).toBe(307);
  });
});
