// Called only inside the approved CUA runtime; reads the visible step editor.
import fs from 'node:fs/promises';
export async function exportStep(tab,folder,step){
 await tab.playwright.locator('#instruction_it_instruct').waitFor({state:'attached',timeoutMs:30000});
 const info=await tab.playwright.evaluate(()=>({languages:[...document.querySelectorAll('textarea[id^="instruction_"]')].map(e=>({language:e.id.split('_')[1],length:e.value.length})),fields:[...document.querySelectorAll('input[name^="instruction["]')].map(e=>({name:e.name,value:e.value})),visibility:{days:document.querySelector('#n_days_before_arrival')?.value}}));
 if(!info.languages.length || !info.languages.some(x=>x.length>0))throw Error('Step editor has no loaded HTML; export stopped');
 const languages=[];
 for(const language of info.languages){
  let html='';
  for(let offset=0;offset<language.length;offset+=80000)html+=await tab.playwright.evaluate(({name,offset})=>document.querySelector('#instruction_'+name+'_instruct').value.slice(offset,offset+80000),{name:language.language,offset});
  if(html.length!==language.length)throw Error('HTML export length mismatch');
  languages.push({language:language.language,html});
  await fs.writeFile(folder+'/'+step+'-'+language.language+'.html',html,{mode:0o600});
 }
 await fs.writeFile(folder+'/'+step+'.json',JSON.stringify({...info,languages}),{mode:0o600});
 return {languages:languages.length,html_bytes:languages.reduce((n,x)=>n+x.html.length,0)};
}
