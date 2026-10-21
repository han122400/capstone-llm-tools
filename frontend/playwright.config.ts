import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
const frontend=process.cwd();
const project=path.resolve(frontend,"..");
const python=process.env.EVALUATOR_PYTHON || path.join(project,process.platform==="win32"?".venv/Scripts/python.exe":".venv/bin/python");
export default defineConfig({
  testDir:"./tests", fullyParallel:false, workers:1, timeout:60_000,
  expect:{timeout:15_000}, reporter:[["list"],["html",{open:"never"}]],
  use:{baseURL:"http://127.0.0.1:3101",trace:"retain-on-failure",screenshot:"only-on-failure",channel:process.env.PLAYWRIGHT_CHANNEL||"msedge"},
  projects:[{name:"desktop",use:{...devices["Desktop Chrome"],viewport:{width:1280,height:900}}},{name:"mobile",use:{viewport:{width:390,height:844},isMobile:true,hasTouch:true},testMatch:/mobile\.spec\.ts/}],
  webServer:[
    {command:`"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8101`,cwd:path.join(project,"backend"),url:"http://127.0.0.1:8101/api/health",timeout:30_000,reuseExistingServer:false,
      env:{EVALUATOR_DATA_DIR:path.join(frontend,`test-results/e2e-data-${Date.now()}`),OPENROUTER_API_KEY:""}},
    {command:"node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3101",cwd:frontend,url:"http://127.0.0.1:3101",timeout:90_000,reuseExistingServer:false,
      env:{EVALUATOR_BACKEND_URL:"http://127.0.0.1:8101",EVALUATOR_NEXT_DIST_DIR:".next-e2e",NEXT_TELEMETRY_DISABLED:"1"}}
  ]
});
