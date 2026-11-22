/* Executes the offline demo in jsdom; checks interactions, not browser layout. */
const {JSDOM,VirtualConsole}=require(process.env.MINESWEEPER_JSDOM_MODULE||'jsdom');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const errors=[];
const virtualConsole=new VirtualConsole();
virtualConsole.on('jsdomError',e=>errors.push(e.message));
const dom=new JSDOM(fs.readFileSync(path.join(root,'docs/live-demo.html'),'utf8'),{
  runScripts:'dangerously',url:pathToFileURL(path.join(root,'docs/live-demo.html')).href,
  virtualConsole,pretendToBeVisual:true,
  beforeParse(window){window.HTMLElement.prototype.scrollIntoView=function(){};}
});
const doc=dom.window.document;
const $=id=>doc.getElementById(id);
function choose(id,value){$(id).value=value;$(id).dispatchEvent(new dom.window.Event('change',{bubbles:true}));}
function stage(name){const button=[...doc.querySelectorAll('#stages button')].find(b=>b.textContent===name);assert(button);button.click();}
function bits(){return [...doc.querySelectorAll('#syndrome .bit')].map(e=>e.textContent)}
stage('試験係が誤りを注入');
assert.match($('terms').textContent,/010/);assert.match($('terms').textContent,/101/);
assert.match($('terms').textContent,/0\.7071i/);
let repCases=0;
for(const level of ['1','2','3']) for(const input of ['0','1','+','-','+i','-i']) for(const location of ['none','0','1','2']){
  choose('level',level);choose('input',input);choose('location',location);
  stage('元の1個に復号');
  assert.match($('verified').textContent,/忠実度 1\.0000000000/);
  assert(doc.querySelectorAll('#terms tr').length>0);
  assert.deepEqual(bits(),{none:['0','0'],'0':['1','0'],'1':['1','1'],'2':['0','1']}[location]);
  repCases++;
}
choose('level','3');choose('input','+');choose('location','1');stage('試験係が誤りを注入');
assert.match($('terms').textContent,/-0\.7071i/);
stage('シンドロームに応じて訂正');
assert(!$('terms').textContent.includes('i'));
$('inter-minus').click();assert.equal($('inter-one-label').textContent,'1：100%');
$('inter-plus').click();assert.equal($('inter-zero-label').textContent,'0：100%');
let l4Cases=0;
for(const input of ['0','1','+','-','+i','-i']) for(const error of ['I','X','Z','Y']){
  choose('l4input',input);choose('l4error',error);
  for(const location of (error==='I'?['0']:['0','1','2','3'])){
    if(error!=='I')choose('l4location',location);
    assert.match($('l4result').textContent,new RegExp('分類 '+error+'。'));
    assert.match($('l4result').textContent,new RegExp('測定文字列「'+{I:'00',X:'01',Z:'10',Y:'11'}[error]+'」'));
    l4Cases++;
  }
}
assert.match($('circuit').getAttribute('src'),/^data:image\/png;base64,/);
assert.deepEqual(errors,[]);
const hardware=doc.getElementById('hardware-results');
if(hardware){
  assert.match(hardware.textContent,/74\.12% → 89\.94%/);
  assert.match(hardware.textContent,/\+15\.82ポイント/);
  assert.match(hardware.textContent,/再構成/);
  assert.match(hardware.textContent,/忠実度ではありません/);
  assert.equal(hardware.querySelectorAll('tbody tr').length,4);
}
const result={source:'jsdom JavaScript/DOM execution; not a rendered browser test',
  repetition_ui_cases:repCases,classification_ui_cases:l4Cases,complex_phase_and_recovery:'passed',
  interference_buttons:'passed',asymmetric_syndrome_order:'passed',javascript_errors:errors,
  hardware_counts_panel:hardware?'passed; supplied export and protocol reconstruction labeled':'not present in this version',
  browser_rendering:'Not run: Chromium launch blocked by execution-environment socket restrictions. PDF renderings inspected separately.'};
fs.writeFileSync(path.join(root,'results/demo-dom-validation.json'),JSON.stringify(result,null,2)+'\n');
console.log(result);
dom.window.close();
