import { HttpResponse, http } from "msw";
import { expect, it } from "vitest";

import { api, setBusinessIdResolver } from "../../web/api/client";
import { expectCsrf, server } from "./setup";


it("sends JSON PUT requests with the CSRF token", async () => {
  server.use(
    http.put("/api/v1/settings/runner", async ({ request }) => {
      expectCsrf(request);
      expect(request.headers.get("Content-Type")).toBe("application/json");
      expect(await request.json()).toEqual({ mode: "mock" });
      return HttpResponse.json({ mode: "mock" });
    }),
  );

  await expect(api.put<{ mode: string }>("/settings/runner", { mode: "mock" })).resolves.toEqual({
    mode: "mock",
  });
});

it("adds the current business id header when configured", async () => {
  setBusinessIdResolver(() => "biz_search");
  try {
    server.use(
      http.get("/api/v1/cases", ({ request }) => {
        expect(request.headers.get("X-Business-Id")).toBe("biz_search");
        return HttpResponse.json({ items: [], total: 0, page: 1, page_size: 10 });
      }),
    );

    await expect(api.get("/cases")).resolves.toEqual({
      items: [],
      total: 0,
      page: 1,
      page_size: 10,
    });
  } finally {
    setBusinessIdResolver(null);
  }
});
