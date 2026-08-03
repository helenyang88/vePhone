import { HttpResponse, http } from "msw";
import { expect, it } from "vitest";

import { api } from "../../web/api/client";
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
