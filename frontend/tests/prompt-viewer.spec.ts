import { test, expect } from "@playwright/test";
import os from "node:os";
import path from "node:path";

for (const width of [1280, 390]) {
  test(`설정에서 실제 요청과 같은 프롬프트 조회 · ${width}px`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: 900 });
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    // Viewing prompts must never write settings, preflight models, or start inference.
    await page.route("**/api/**", async route => {
      expect(route.request().method()).toBe("GET");
      await route.continue();
    });
    const response = await request.get("/api/settings");
    expect(response.ok()).toBeTruthy();
    const prompt = (await response.json()).classification_prompt;
    expect(prompt.version).toBe("email-injection-choice-v3");
    expect(prompt.cascade_question_version).toBe("email-injection-jev-review-v2");
    await page.goto("/#settings");
    await expect(page.getByText("모델 판정 프롬프트", { exact: true })).toBeVisible();
    await expect(page.getByTestId("prompt-instructions")).toHaveText(prompt.instructions);
    for (const decision of ["NORMAL", "INJECTION", "REVIEW"]) {
      await expect(page.getByTestId(`prompt-criterion-${decision}`)).toHaveText(prompt.criteria[decision]);
    }
    await expect(page.getByTestId("prompt-local")).not.toBeVisible();
    await page.getByText("Foundation-Sec / Qwen 시스템 프롬프트 전체", { exact: true }).click();
    await expect(page.getByTestId("prompt-local")).toHaveText(prompt.local_system_prompt);
    await page.getByText("Jev Decisions 질문 원문", { exact: true }).click();
    await expect(page.getByTestId("prompt-jev")).toHaveText(JSON.stringify(prompt.jev_question, null, 2));
    await page.getByText("Foundation-Sec / Qwen 시스템 프롬프트 전체", { exact: true }).click();
    await expect(page.getByTestId("prompt-local")).not.toBeVisible();
    await page.reload();
    await expect(page.getByTestId("prompt-instructions")).toHaveText(prompt.instructions);
    await expect(page.getByTestId("prompt-local")).not.toBeVisible();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(errors).toEqual([]);
    await page.getByText("모델 판정 프롬프트", { exact: true }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(os.tmpdir(), `mail-prompt-viewer-${width}.png`) });
  });
}
