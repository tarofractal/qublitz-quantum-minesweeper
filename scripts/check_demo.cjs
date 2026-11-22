/* Optional UI check. Install Playwright separately: npm install playwright.
   This is artifact validation, not part of the Python quantum-test count. */
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const assert=require('node:assert/strict');

(async()=>{
  const root=path.resolve(__dirname,'..');
  const executablePath=process.env.CHROMIUM_PATH||(fs.existsSync('/usr/bin/chromium')?'/usr/bin/chromium':undefined);
  const browser=await chromium.launch({headless:true,executablePath,args:['--no-sandbox']});
  const page=await browser.newPage({viewport:{width:1250,height:1050}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(pathToFileURL(path.join(root,'docs/live-demo.html')).href);
  await page.getByRole('button',{name:'Inject the test error',exact:true}).click();
  assert.match(await page.locator('#terms').innerText(),/010/);
  assert.match(await page.locator('#terms').innerText(),/101/);
  assert.match(await page.locator('#terms').innerText(),/0\.7071i/);
  await page.getByRole('button',{name:'Measure ancillas only',exact:true}).click();
  assert.deepEqual(await page.locator('#syndrome .bit').allTextContents(),['1','1']);
  await page.selectOption('#location','0');
  await page.getByRole('button',{name:'Measure ancillas only',exact:true}).click();
  assert.deepEqual(await page.locator('#syndrome .bit').allTextContents(),['1','0']);
  let cases=0;
  for(const level of ['1','2','3']) for(const input of ['0','1','+','-','+i','-i']) for(const location of ['none','0','1','2']){
    await page.selectOption('#level',level);await page.selectOption('#input',input);await page.selectOption('#location',location);
    await page.getByRole('button',{name:'Decode to one qubit',exact:true}).click();
    assert.match(await page.locator('#verified').innerText(),/fidelity 1\.0000000000/);
    assert(await page.locator('#terms tr').count()>0);
    const expected={none:['0','0'],'0':['1','0'],'1':['1','1'],'2':['0','1']}[location];
    assert.deepEqual(await page.locator('#syndrome .bit').allTextContents(),expected);
    cases++;
  }
  await page.click('#inter-minus');
  assert.equal(await page.locator('#inter-one-label').innerText(),'1: 100%');
  await page.click('#inter-plus');
  assert.equal(await page.locator('#inter-zero-label').innerText(),'0: 100%');
  let classifications=0;
  for(const input of ['0','1','+','-','+i','-i']) for(const error of ['I','X','Z','Y']){
    await page.selectOption('#l4input',input);await page.selectOption('#l4error',error);
    for(const location of (error==='I'?['0']:['0','1','2','3'])){
      if(error!=='I') await page.selectOption('#l4location',location);
      assert.match(await page.locator('#l4result').innerText(),new RegExp('classified type '+error+'\\.'));
      const raw={I:'00',X:'01',Z:'10',Y:'11'}[error];
      assert.match(await page.locator('#l4result').innerText(),new RegExp('Measurement string '+raw+':'));
      classifications++;
    }
  }
  await page.selectOption('#level','1');await page.selectOption('#input','+i');await page.selectOption('#location','1');
  await page.getByRole('button',{name:'Measure ancillas only',exact:true}).click();
  assert(await page.locator('#circuit').evaluate(e=>e.complete&&e.naturalWidth>0));
  const screenshotDir=process.env.MINESWEEPER_SCREENSHOT_DIR;
  if(screenshotDir){fs.mkdirSync(screenshotDir,{recursive:true});await page.screenshot({path:path.join(screenshotDir,'live-demo-desktop.png')});}
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
  if(screenshotDir) await page.screenshot({path:path.join(screenshotDir,'live-demo-mobile.png')});
  assert.deepEqual(errors,[]);
  assert.equal(await page.locator('html').getAttribute('lang'),'en');
  assert.equal(/[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]/u.test(await page.locator('body').textContent()),false);
  const result={source:'Local Chromium/Playwright artifact validation',interface_language:'English',repetition_ui_cases:cases,classification_ui_cases:classifications,
    interference_identities:'passed',complex_phase_display:'passed',asymmetric_bit_order:'passed',mobile_overflow:'none',javascript_errors:errors};
  fs.writeFileSync(path.join(root,'results/demo-ui-validation.json'),JSON.stringify(result,null,2)+'\n');
  console.log(result);
  await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
