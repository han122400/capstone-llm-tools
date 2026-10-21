import { test, expect } from "@playwright/test";
import os from "node:os";
import path from "node:path";

for (const width of [1280, 390]) {
  test(`Qwen thinking ON/OFF 저장·새로고침 · ${width}px`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: 900 });
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    // This flow changes only isolated test settings; no model or API requests.
    await page.route("**/api/**", async route => {
      if (route.request().method() !== "GET") {
        expect(new URL(route.request().url()).pathname).toBe("/api/settings");
        expect(route.request().method()).toBe("PUT");
        expect(typeof route.request().postDataJSON().qwen_thinking).toBe("boolean");
      }
      await route.continue();
    });
    expect((await request.put("/api/settings", { data: { qwen_thinking: false } })).ok()).toBeTruthy();
    await page.goto("/#settings");
    await expect(page.getByRole("heading", { name: "실행 환경 및 설정", exact: true })).toBeVisible();
    const toggle = page.getByLabel("Qwen thinking 모드", { exact: true });
    await expect(toggle).toHaveValue("false");
    for (const enabled of [true, false]) {
      await toggle.selectOption(String(enabled));
      await page.getByRole("button", { name: "설정 저장", exact: true }).click();
      await expect(page.getByRole("alert").filter({ hasText: "추론 설정을 저장했습니다" })).toBeVisible();
      expect((await (await request.get("/api/settings")).json()).qwen_thinking).toBe(enabled);
      await page.reload();
      await expect(toggle).toHaveValue(String(enabled));
    }
    const original = await (await request.get('/api/settings')).json();
    await page.getByRole('button', {name:'Thinking 시험 설정 채우기', exact:true}).click();
    await expect(page.getByLabel('컨텍스트 길이', {exact:true})).toHaveValue('8192');
    await expect(page.getByLabel('출력 토큰 제한', {exact:true})).toHaveValue('4096');
    await expect(page.getByLabel('요청 timeout · 초', {exact:true})).toHaveValue('480');
    expect((await (await request.get('/api/settings')).json()).context_length).toBe(original.context_length);
    await page.getByRole('button', {name:'설정 저장', exact:true}).click();
    await expect.poll(async () => (await (await request.get('/api/settings')).json()).max_output_tokens).toBe(4096);
    await page.reload();
    await expect(toggle).toHaveValue('true');
    await expect(page.getByLabel('컨텍스트 길이', {exact:true})).toHaveValue('8192');
    await expect(page.getByLabel('출력 토큰 제한', {exact:true})).toHaveValue('4096');
    await page.getByLabel('컨텍스트 길이', {exact:true}).fill('4096');
    await page.getByRole('button', {name:'설정 저장', exact:true}).click();
    await expect(page.getByRole('alert').filter({hasText:'컨텍스트에 입력 공간이 없습니다'})).toBeVisible();
    expect((await (await request.get('/api/settings')).json()).context_length).toBe(8192);
    // Restore isolated shared test settings; never touch the user's real database.
    await request.put('/api/settings', {data:{context_length:original.context_length,
      max_output_tokens:original.max_output_tokens,timeout_seconds:original.timeout_seconds,qwen_thinking:false}});
    await page.reload();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(errors).toEqual([]);
    await toggle.scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(os.tmpdir(), `mail-qwen-thinking-${width}.png`) });
  });
}
