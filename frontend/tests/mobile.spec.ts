import {test,expect} from "@playwright/test";
import {mkdir} from "node:fs/promises";
import path from "node:path";
test("작은 화면의 탐색·빈 비교표·데이터셋 접근",async({page})=>{
  await page.goto("/");await expect(page.getByRole("heading",{name:"모델 비교 대시보드"})).toBeVisible();
  await expect(page.getByText("5개 구성 비교",{exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  if(test.info().project.name==="mobile"){await mkdir(path.resolve("../docs/qa"),{recursive:true});await page.screenshot({path:path.resolve("../docs/qa/dashboard-mobile.png"),fullPage:true});}
  await page.getByRole("button",{name:"데이터셋",exact:true}).click();await expect(page.getByRole("heading",{name:"이메일 데이터셋"})).toBeVisible();await expect(page.getByRole("button",{name:"데이터셋 생성"})).toBeVisible();
});
