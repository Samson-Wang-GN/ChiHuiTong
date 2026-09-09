/* Small, dependency-free XLSX export for flat prototype tables. No formulas/macros. */
window.PrototypeExcel = (() => {
  const enc = new TextEncoder();
  const xml = value => String(value ?? '').replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
  const crc = bytes => {let n=0xffffffff;for(const b of bytes){n^=b;for(let j=0;j<8;j++)n=(n>>>1)^((n&1)?0xedb88320:0)}return (n^0xffffffff)>>>0};
  function zip(files) {
    const parts=[],central=[];let offset=0,size=0;
    for(const [path,text] of Object.entries(files)) {
      const name=enc.encode(path),data=enc.encode(text),sum=crc(data),local=new Uint8Array(30+name.length),v=new DataView(local.buffer);
      v.setUint32(0,0x04034b50,true);v.setUint16(4,20,true);v.setUint16(6,0x800,true);v.setUint16(12,33,true);v.setUint32(14,sum,true);v.setUint32(18,data.length,true);v.setUint32(22,data.length,true);v.setUint16(26,name.length,true);local.set(name,30);
      const c=new Uint8Array(46+name.length),d=new DataView(c.buffer);d.setUint32(0,0x02014b50,true);d.setUint16(4,20,true);d.setUint16(6,20,true);d.setUint16(8,0x800,true);d.setUint16(14,33,true);d.setUint32(16,sum,true);d.setUint32(20,data.length,true);d.setUint32(24,data.length,true);d.setUint16(28,name.length,true);d.setUint32(42,offset,true);c.set(name,46);
      parts.push(local,data);central.push(c);offset+=local.length+data.length;size+=c.length;
    }
    const end=new Uint8Array(22),v=new DataView(end.buffer);v.setUint32(0,0x06054b50,true);v.setUint16(8,central.length,true);v.setUint16(10,central.length,true);v.setUint32(12,size,true);v.setUint32(16,offset,true);
    return new Blob([...parts,...central,end],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
  }
  function workbook(sheets) {
    const main='http://schemas.openxmlformats.org/spreadsheetml/2006/main',rel='http://schemas.openxmlformats.org/officeDocument/2006/relationships',pkg='http://schemas.openxmlformats.org/package/2006/relationships';
    const pre='<?xml version="1.0" encoding="UTF-8" standalone="yes"?>';
    const files={'[Content_Types].xml':pre+'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+sheets.map((s,i)=>'<Override PartName="/xl/worksheets/sheet'+(i+1)+'.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>').join('')+'</Types>',
      '_rels/.rels':pre+'<Relationships xmlns="'+pkg+'"><Relationship Id="rId1" Type="'+rel+'/officeDocument" Target="xl/workbook.xml"/></Relationships>',
      'xl/workbook.xml':pre+'<workbook xmlns="'+main+'" xmlns:r="'+rel+'"><sheets>'+sheets.map((s,i)=>'<sheet name="'+xml(s.name)+'" sheetId="'+(i+1)+'" r:id="rId'+(i+1)+'"/>').join('')+'</sheets></workbook>',
      'xl/_rels/workbook.xml.rels':pre+'<Relationships xmlns="'+pkg+'">'+sheets.map((s,i)=>'<Relationship Id="rId'+(i+1)+'" Type="'+rel+'/worksheet" Target="worksheets/sheet'+(i+1)+'.xml"/>').join('')+'</Relationships>'};
    const col=n=>{let s='';for(n++;n;n=Math.floor((n-1)/26))s=String.fromCharCode(65+(n-1)%26)+s;return s};
    sheets.forEach((sheet,i)=>{files['xl/worksheets/sheet'+(i+1)+'.xml']=pre+'<worksheet xmlns="'+main+'"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="20"/><cols>'+sheet.rows[0].map((_,j)=>'<col min="'+(j+1)+'" max="'+(j+1)+'" width="24" customWidth="1"/>').join('')+'</cols><sheetData>'+sheet.rows.map((row,r)=>'<row r="'+(r+1)+'">'+row.map((value,c)=>{const at=col(c)+(r+1);return typeof value==='number'&&Number.isFinite(value)?'<c r="'+at+'" t="n"><v>'+value+'</v></c>':'<c r="'+at+'" t="inlineStr"><is><t xml:space="preserve">'+xml(value)+'</t></is></c>'}).join('')+'</row>').join('')+'</sheetData></worksheet>'});
    return zip(files);
  }
  function download(name,sheets){const url=URL.createObjectURL(workbook(sheets)),a=document.createElement('a');a.href=url;a.download=name.replace(/[\\/:*?"<>|]/g,'-')+'.xlsx';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
  return {workbook,download};
})();
