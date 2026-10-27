const labels=['positive','negative','neutral','mixed','uncertain','empty'],names=['积极','消极','中立','混合','不确定','空白'];
export const textCSV=rows=>'\uFEFF'+rows.map(row=>row.map(x=>'"'+String(typeof x==='string'&&/^[\s]*[=+@-]/.test(x)?"'"+x:x??'').replaceAll('"','""')+'"').join(',')).join('\r\n');
const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
const md=s=>String(s).replace(/[\r\n|`<>]/g,' '),short=(s,n)=>Array.from(s).slice(0,n).join('')+(Array.from(s).length>n?'…':'');
export function sentimentArtifacts(result){
 const groups=result.cohorts,summary=[['source','unit','total','classified','needs_review','truncated',...labels],...groups.map(g=>[g.source,g.unit,g.total,g.classified,g.needs_review,g.truncated,...labels.map(k=>g.counts[k])])];
 const report=['# 文本情感基线分析','',`方法：${result.method}。共 ${result.total} 条输入记录，按来源与分析单位分别统计。`,'','| 来源 | 单位 | 全部记录 | 可分类 | 需复核 | 积极 | 消极 | 中立 | 混合 | 不确定 | 空白 |','|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|',...groups.map(g=>'| '+[md(g.source),md(g.unit),g.total,g.classified,g.needs_review,...labels.map(k=>g.counts[k])].join(' | ')+' |'),'','各类别比例的分母是同一来源与单位的全部记录；不确定与空白不计入可分类数。需复核是独立标记，可与各类别重叠。','',`词典指纹：${result.dictionary_sha256}。分数不是校准概率；准确率未验证。来源是输入材料的声明，未据此推断现实总体。`,groups.some(g=>g.truncated)?'存在截断文本，逐条结果已标记需复核。':'','图表仅表达上述实际计数；原文和来源在逐条JSON中回查。'].filter(x=>x!==null).join('\n')+'\n';
 let svg=null;
 if(groups.length&&groups.length<=12){
  const height=100+groups.length*248,body=[],max=Math.max(1,...groups.flatMap(g=>Object.values(g.counts)));
  groups.forEach((g,i)=>{const y=72+i*248;body.push(`<text x="24" y="${y}" font-size="17" font-weight="600">${escape(short(g.source,22))} / ${escape(short(g.unit,10))} · n=${g.total}</text>`);labels.forEach((label,j)=>{const yy=y+16+j*29,value=g.counts[label],width=480*value/max;body.push(`<text x="28" y="${yy+16}" font-size="14">${names[j]}</text><rect x="112" y="${yy}" width="${width.toFixed(2)}" height="19" rx="3" fill="${['#197c69','#bd514b','#748399','#a1772b','#7866a3','#aab2bf'][j]}"/><text x="${(122+width).toFixed(2)}" y="${yy+15}" font-size="14">${value}</text>`);});});
  svg=`<svg xmlns="http://www.w3.org/2000/svg" width="760" height="${height}" viewBox="0 0 760 ${height}"><title>按来源和分析单位分别统计的文本情感基线</title><metadata>${escape(JSON.stringify({method:result.method,dictionary_sha256:result.dictionary_sha256,cohorts:groups,scale:'shared_count_scale',maximum:max}))}</metadata><rect width="760" height="${height}" fill="#fff"/><g font-family="Noto Sans CJK SC,Microsoft YaHei,Arial,sans-serif" fill="#202833"><text x="24" y="32" font-size="21" font-weight="600">文本情感基线 · 各来源独立计数</text>${body.join('')}<text x="24" y="${height-18}" font-size="12">共用计数刻度；各来源分母见 n。词典方法，准确率未验证。</text></g></svg>`;
 }
 return{summary_csv:textCSV(summary),report_md:report,chart_svg:svg,chart_status:svg?'created':groups.length?'too_many_cohorts_use_summary_csv':'empty_no_chart'};
}
