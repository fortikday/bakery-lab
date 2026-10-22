// Run with Node.js 18+; uses built-ins and fictional data only.
// This isolated DOM stand-in checks state behavior, not visual layout.
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const assert = require('node:assert/strict');
const source = fs.readFileSync(path.join(__dirname,'..','log.html'),'utf8').match(/<script>([\s\S]*?)<\/script>/)[1].replace(/\s*initialize\(\);\s*$/, '');
const elements = new Map();
let downloads = 0;
function element(tag='div') {
  return {tag,textContent:'',hidden:false,value:'',checked:false,children:[],style:{},attributes:{},
    classList:{toggle(){}},append(...children){this.children.push(...children);},
    replaceChildren(...children){this.children=children;},setAttribute(name,value){this.attributes[name]=value;},
    addEventListener(){},remove(){},click(){if(this.download) downloads++;}};
}
const context = vm.createContext({console,Blob,TextDecoder,URLSearchParams,
  setTimeout(){return 0;},URL:{createObjectURL(){return 'blob:fictional-test';},revokeObjectURL(){}},
  document:{getElementById(id){if(!elements.has(id)) elements.set(id,element());return elements.get(id);},createElement:element,body:element()},
});
vm.runInContext(source,context);
const read = id => elements.get(id).textContent;
function report(entries) {return {week_start:'2026-10-12',week_end:'2026-10-18',entry_count:entries.length,entries,
  totals:{finished_sold:0,finished_discarded:0,production_waste_kg:'1.250',early_sellout_entries:0},costs:[],reasons:[],sellouts:[]};}
function backup(revision,overrides={}) {return {automatic:true,latest_date:'2026-10-22',last_error:null,has_records:true,
  download_url:'/api/backup.sqlite3',revision,instance_id:'11111111-1111-4111-8111-111111111111',...overrides};}

(async()=>{
  context.sample = report([{kind:'production_waste',record_date:'2026-10-12',store:'Fictional bakery',product:'Dough',waste_kg:'1.250'}]);
  vm.runInContext('renderReport(sample)',context);
  assert.equal(read('sold-total'),'No records');
  assert.equal(read('discarded-total'),'No records');
  assert.equal(read('early-sellout-total'),'Unknown');
  assert.equal(read('coverage-heading'),'1 of 7 calendar dates have records');
  assert.match(read('coverage-note'),/6 dates have no records/);
  assert.match(read('coverage-note'),/not measured zero waste/);
  assert.equal(elements.get('review-focus').hidden,true);

  context.sample = report([{kind:'finished_product',record_date:'2026-10-12',store:'Fictional bakery',product:'Bread',discarded:0,sold:0}]);
  context.sample.totals.production_waste_kg='0.000';
  vm.runInContext('renderReport(sample)',context);
  assert.equal(read('discarded-total'),'0');
  assert.equal(read('production-total'),'No records');

  context.backupStatus=backup(0,{latest_date:null,has_records:false});
  vm.runInContext("state.online=true;state.today='2026-10-22';renderBackupStatus(backupStatus)",context);
  assert.match(read('backup-state'),/first saved entry/);
  context.fetch = async()=>({ok:false,json:async()=>({error:'Backup unavailable; saved records are unchanged.'})});
  await vm.runInContext('downloadBackup({preventDefault(){}})',context);
  assert.match(read('backup-error'),/records are unchanged/);
  assert.equal(downloads,0);
  context.fetch = async()=>({ok:true,blob:async()=>new Blob(['<html>wrong response</html>'])});
  await vm.runInContext('downloadBackup({preventDefault(){}})',context);
  assert.match(read('backup-error'),/valid backup file/);
  assert.equal(downloads,0);
  context.fetch = async()=>({ok:true,blob:async()=>new Blob(['SQLite format 3\0fictional test bytes']),headers:{get(){return 'attachment; filename="bakery-test.sqlite3"';}}});
  await vm.runInContext('downloadBackup({preventDefault(){}})',context);
  assert.equal(downloads,1);
  assert.match(read('backup-success'),/Check your browser/);

  context.fetch = async()=>({ok:true,json:async()=>({entry:{id:'fictional'},backup:backup(1,{last_error:'Recovery copy unavailable.'}),backup_warning:'Recovery copy unavailable.'})});
  const saved = await vm.runInContext("api('/api/entries','POST',{})",context);
  assert.equal(saved.entry.id,'fictional');
  assert.match(read('backup-state'),/Your records are saved/);
  assert.match(read('backup-state'),/Recovery copy unavailable/);

  // A slow older save must not clear the warning for a newer failed snapshot.
  let releaseOldSuccess;
  context.fetch = ()=>new Promise(resolve=>releaseOldSuccess=resolve);
  const delayedOldSuccess=vm.runInContext("api('/api/entries','POST',{})",context);
  context.fetch = async()=>({ok:true,json:async()=>({entry:{id:'newer'},backup:backup(3,{last_error:'Newer copy failed.'}),backup_warning:'Newer copy failed.'})});
  await vm.runInContext("api('/api/entries','POST',{})",context);
  assert.match(read('backup-state'),/Newer copy failed/);
  releaseOldSuccess({ok:true,json:async()=>({entry:{id:'older'},backup:backup(2)})});
  await delayedOldSuccess;
  assert.match(read('backup-state'),/Newer copy failed/);
  context.backupStatus={automatic:true,latest_date:'2026-10-22',last_error:null,has_records:true,download_url:'/api/backup.sqlite3'};
  vm.runInContext('renderBackupStatus(backupStatus)',context);
  assert.match(read('backup-state'),/Newer copy failed/);
  context.backupStatus=backup(999,{download_url:'/unsupported-route'});
  vm.runInContext('renderBackupStatus(backupStatus)',context);
  assert.match(read('backup-state'),/Newer copy failed/);
  context.fetch = async()=>({ok:true,json:async()=>({entry:{id:'recovered'},backup:backup(4)})});
  await vm.runInContext("api('/api/entries','POST',{})",context);
  assert.match(read('backup-state'),/Recovery copy updated/);
  assert.doesNotMatch(read('backup-state'),/failed/);

  // A transient GET status read error may share the same snapshot revision.
  let releaseOldStatus;
  context.fetch=()=>new Promise(resolve=>releaseOldStatus=resolve);
  const delayedStatus=vm.runInContext("api('/api/config')",context);
  context.fetch=async()=>({ok:true,json:async()=>({backup:backup(4,{has_records:null,last_error:'Status could not be checked.'})})});
  await vm.runInContext("api('/api/config')",context);
  assert.match(read('backup-state'),/Status could not be checked/);
  releaseOldStatus({ok:true,json:async()=>({backup:backup(4)})});
  await delayedStatus;
  assert.match(read('backup-state'),/Status could not be checked/);
  context.fetch=async()=>({ok:true,json:async()=>({backup:backup(4)})});
  await vm.runInContext("api('/api/config')",context);
  assert.match(read('backup-state'),/Recovery copy updated/);

  // Restarted servers can reset their revision; a retired instance stays retired.
  context.fetch = async()=>({ok:true,json:async()=>({backup:backup(0,{instance_id:'22222222-2222-4222-8222-222222222222',last_error:'Restarted server copy failed.'})})});
  await vm.runInContext("api('/api/config')",context);
  assert.match(read('backup-state'),/Restarted server copy failed/);
  context.fetch = async()=>({ok:true,json:async()=>({backup:backup(999)})});
  await vm.runInContext("api('/api/config')",context);
  assert.match(read('backup-state'),/Restarted server copy failed/);

  let releaseResponse;
  context.fetch = ()=>new Promise(resolve=>releaseResponse=resolve);
  context.document.getElementById('report-store').value='Fictional store A';
  context.document.getElementById('report-week').value='2026-10-12';
  const pending = vm.runInContext('refreshReport()',context);
  elements.get('report-store').value='Half-typed store B';
  releaseResponse({ok:true,json:async()=>report([])});
  await pending;
  assert.match(read('report-range'),/Fictional store A/);
  assert.match(read('coverage-scope'),/Fictional store A/);
  assert.match(elements.get('export-csv').href,/Fictional\+store\+A/);
  console.log('UI behavior checks passed: coverage, unknown vs zero, backup download/error validity, delayed backup-status ordering and recovery, restart/retired-instance guards, malformed-status rejection, and captured report-filter scope.');
})().catch(error=>{console.error(error);process.exitCode=1;});
