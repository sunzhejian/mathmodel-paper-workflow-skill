const invalid=message=>{throw Object.assign(Error(message),{code:'csv_extract_error',retryable:false,stage:'csv_extract'});};
export function csvOptions(input){
 const named=input.csv_text_column,indexed=input.csv_text_column_index;
 if(named!==undefined&&(typeof named!=='string'||!named.length||named.length>200))invalid('CSV文本列名称须为1到200字');
 if(indexed!==undefined&&(!Number.isSafeInteger(indexed)||indexed<0||indexed>255))invalid('CSV文本列序号为0到255的整数，从0开始');
 if(named!==undefined&&indexed!==undefined)invalid('CSV列名和列序号二选一');
 if(input.csv_has_header!==undefined&&typeof input.csv_has_header!=='boolean')invalid('CSV表头开关须为布尔值');
 if(input.csv_delimiter!==undefined&&![',',';','\t'].includes(input.csv_delimiter))invalid('CSV分隔符仅支持逗号、分号或制表符');
 const selected=named!==undefined||indexed!==undefined,has_header=input.csv_has_header??true;
 if(!selected&&(input.csv_delimiter!==undefined||input.csv_has_header!==undefined))invalid('请先明确CSV文本列，再指定表头或分隔符');
 if(named!==undefined&&!has_header)invalid('无表头CSV须使用文本列序号');
 return{selected,name:named,index:indexed,has_header,delimiter:input.csv_delimiter??','};
}
export function parseCSVText(text,options){
 if(typeof text!=='string')invalid('CSV响应不是文本');text=text.replace(/^\uFEFF/,'');
 const rows=[];let row=[],field='',mode='start',started=false,blank=0;
 const pushField=()=>{row.push(field);if(row.length>256)invalid('CSV列数超过256，请缩小来源范围');field='';mode='start';};
 const pushRow=()=>{if(!started&&!row.length&&!field){blank++;return;}pushField();rows.push(row);if(rows.length>10001)invalid('CSV记录超过10000条，请分页或缩小来源范围');row=[];started=false;};
 for(let i=0;i<text.length;i++){const c=text[i];
  if(mode==='quoted'){if(c==='"'){if(text[i+1]==='"'){field+='"';i++;}else mode='closed';}else field+=c;continue;}
  if(c===options.delimiter){started=true;pushField();continue;}
  if(c==='\r'||c==='\n'){pushRow();if(c==='\r'&&text[i+1]==='\n')i++;continue;}
  if(mode==='closed')invalid('CSV引号闭合后出现非分隔符内容');
  started=true;if(c==='"'){if(mode!=='start')invalid('CSV非引号字段含未转义引号');mode='quoted';}else{field+=c;mode='plain';}
 }
 if(mode==='quoted')invalid('CSV引号未闭合，本页未纳入记录');
 if(started||row.length||field)pushRow();
 const columns=options.has_header?(rows.shift()??[]):null,width=columns?.length??rows[0]?.length??0;
 let index=options.index;if(options.name!==undefined){const matches=columns.map((c,i)=>c===options.name?i:-1).filter(i=>i>=0);if(matches.length!==1)invalid('CSV中未找到唯一文本列：'+options.name+'；请核对表头或指定列序号');index=matches[0];}
 if(!Number.isSafeInteger(index)||index<0||index>=width)invalid('CSV文本列序号超出实际列数');
 if(rows.length>10000)invalid('CSV记录超过10000条，请分页或缩小来源范围');
 for(let i=0;i<rows.length;i++)if(rows[i].length!==width)invalid('CSV第'+(i+1)+'条数据的列数与表结构不一致，本页未纳入记录');
 return{rows,columns,index,metadata:{kind:'csv_records',delimiter:options.delimiter,has_header:options.has_header,columns,text_column_index:index,text_column:columns?.[index]??null,records:rows.length,skipped_blank_lines:blank}};
}
