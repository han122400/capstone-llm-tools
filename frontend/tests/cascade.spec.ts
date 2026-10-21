import {test,expect} from '@playwright/test';
import path from 'node:path';
import os from 'node:os';

test('2단계 최종 판정·변경 방향·필터·기준선 비교와 과거 표시',async({page})=>{
  const samples=[
    {sample_id:'a',subject:'공격 사례',body:'<script>window.executed=true</script>',label:'INJECTION'},
    {sample_id:'b',subject:'정상 사례',body:'교육 목적 인용',label:'NORMAL'},
    {sample_id:'c',subject:'악화 사례',body:'역할 변경 지시',label:'INJECTION'},
  ].map(s=>({...s,language:'ko',category:'test',synthetic:true,notes:''}));
  const results=samples.flatMap((s,i)=>{
    const local=i===0?'NORMAL':'INJECTION';const final=i===0?'INJECTION':'NORMAL';
    return [
      {id:`local-${i}`,config_id:'qwen',decision:local},
      {id:`base-${i}`,config_id:'jev',decision:local},
      {id:`review-${i}`,config_id:'jev',component_for:'qwen_then_jev',decision:final},
      {id:`final-${i}`,config_id:'qwen_then_jev',decision:final,local_decision:local,jev_decision:final,decision_changed:true,component_result_ids:[`local-${i}`,`review-${i}`],local_result_reused:true,reused:true,local_latency_ms:2,jev_latency_ms:3},
    ].map(r=>({...r,run_id:'cascade-fixture',sample_id:s.sample_id,status:'SUCCESS',latency_ms:r.config_id==='qwen_then_jev'?null:2,input_hash:'same',raw_response:{decision:r.decision}}));
  });
  const diag={N:3,compared:3,changed:3,unavailable:0,transitions:{NORMAL:{NORMAL:0,INJECTION:1,REVIEW:0},INJECTION:{NORMAL:2,INJECTION:0,REVIEW:0},REVIEW:{NORMAL:0,INJECTION:0,REVIEW:0}},baseline:{compared:3,improved:2,worsened:1,correct_to_review:0,review_to_correct:0,final_review:0,unavailable:0}};
  const run={id:'cascade-fixture',status:'COMPLETED',selected_configs:['qwen','jev','qwen_then_jev'],mode:'reuse',demo:true,created_at:'2026-10-13T00:00:00Z',environment:{prompt_version:'email-injection-choice-v2'},settings:{},progress:{completed:9,total:9},dataset_snapshot:{id:'dataset',name:'2단계 브라우저 검증',version:1,split:'development',samples},results,totals:{},metrics:{},cascade_diagnostics:{qwen_then_jev:diag}};
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/runs?demo=*',route=>route.fulfill({json:[run]}));
  await page.route('**/api/runs/cascade-fixture',route=>route.fulfill({json:run}));
  await page.route('**/api/runs',route=>{if(route.request().method()==='POST')throw new Error('No inference in fixture test');return route.continue();});
  await page.goto('/?demo=true&run=cascade-fixture');
  await expect(page.getByText('2단계 판정 변경',{exact:true})).toBeVisible();
  const comparison=page.getByRole('table',{name:'Jev 단독 대비 판정 변화'});
  await expect(comparison.getByRole('columnheader',{name:'오답 → 정답'})).toBeVisible();
  await expect(comparison.getByRole('row').nth(1).getByRole('cell').nth(2)).toHaveText('2건');
  await expect(comparison.getByRole('row').nth(1).getByRole('cell').nth(3)).toHaveText('1건');
  await page.getByRole('button',{name:'사례 비교',exact:true}).click();
  await page.getByLabel('사례 유형 필터').selectOption('normal_to_injection');
  await expect(page.locator('strong').filter({hasText:'로컬 정상 → Jev 인젝션'}).first()).toBeVisible();
  await expect(page.getByText('최종: 인젝션',{exact:true}).first()).toBeVisible();
  await expect(page.getByRole('button',{name:/정상 사례/})).toHaveCount(0);
  expect(await page.evaluate(()=>('executed' in window))).toBe(false);
  await page.getByLabel('사례 유형 필터').selectOption('injection_to_normal');
  await expect(page.locator('strong').filter({hasText:'로컬 인젝션 → Jev 정상'}).first()).toBeVisible();
  await expect(page.getByRole('button',{name:/정상 사례/})).toBeVisible();
  await page.getByLabel('사례 유형 필터').selectOption('stage_changed');
  await page.screenshot({path:path.join(os.tmpdir(),'cascade-cases-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.screenshot({path:path.join(os.tmpdir(),'cascade-cases-mobile.png'),fullPage:true});
  await page.getByRole('button',{name:'평가 실행',exact:true}).first().click();
  await expect(page.getByRole('checkbox',{name:'Foundation-Sec → Jev 선택',exact:true})).toBeVisible();
  await expect(page.getByRole('checkbox',{name:'Qwen → Jev 선택',exact:true})).toBeVisible();
  await expect(page.getByRole('checkbox',{name:/\+ Jev/})).toHaveCount(0);
  await page.route('**/api/runs/cascade-fixture',route=>route.fulfill({json:{...run,selected_configs:['qwen_jev'],cascade_diagnostics:{},results:[]}}));
  await page.goto('/?demo=true&run=cascade-fixture#cases');
  await page.reload();
  await expect(page.getByRole('columnheader',{name:'Qwen + Jev · 기존 독립 결합',exact:true})).toBeVisible();
  expect(errors).toEqual([]);
});
