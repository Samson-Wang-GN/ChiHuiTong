/* 平台合同配置页；仅平台入口加载，不向合作方暴露其他机构合同。 */
(() => {
  const pages = window.PROTOTYPE.pages;
  const page = id => pages.find(p => p.id === id);
  const reason = {key:'reason',label:'变更原因',type:'textarea'};
  const contracts = page('contracts');
  contracts.rows.find(r=>r.id==='HT-2026-002').party='启明渠道（演示）';
  contracts.rows.push({id:'HT-AH-001',name:'安和客户福利合作合同',type:'平台—资源方',party:'安和经纪（演示）',start:'2026-01-01',end:'2026-12-31',status:'已生效'},
    {id:'HT-XH-001',name:'星海客户福利合作合同',type:'平台—资源方',party:'星海银行（演示）',start:'2026-01-01',end:'2026-12-31',status:'已生效'});
  contracts.columns.splice(2,0,['party','签约主体']);
  contracts.actions.unshift({label:'推广产品配置',link:'contractSchemes',filterKey:'contract',filterFrom:'id',types:['平台—资源方','平台—渠道公司']});
  contracts.notice='每个资源方仅一份平台主合同，可绑定多个推广产品；已有合同请维护原合同。选择“推广产品配置”配置方案，门诊合同继续管理额度和账期。';
  contracts.create.fields.find(f=>f.key==='party').options.push('星海银行（演示）');
  for(const key of ['credit','cycle'])contracts.create.fields.find(f=>f.key===key).optional=true;
  const schemes=page('schemes');
  schemes.description='统一维护核销规则及单次获客费；合作方授权和分配在合同中配置';
  schemes.notice='启用推广产品不代表合作方可使用。请进入对应合作方合同添加授权；卡单价仍由开卡订单单独定价。';
  const fields=[{key:'contract',label:'合作方合同',options:[],dynamic:'partnerContracts'},
    {key:'scheme',label:'推广产品',options:[],dynamic:'schemes'},
    {key:'mode',label:'分配方式',options:['按比例','按金额']},
    {key:'value',label:'分配值（比例填%，金额填元/次）',type:'number'},reason];
  pages.splice(pages.indexOf(contracts)+1,0,{
    id:'contractSchemes',prefix:'SQ',title:'推广产品配置',description:'按合作方合同管理可用方案与单次核销分配',
    columns:[['contract','合同编号'],['party','签约主体'],['scheme','推广产品'],['fee','获客费（元）'],['mode','分配方式'],['value','分配值'],['payout','本方元/次'],['access','新业务授权'],['status','配置状态']],width:1400,
    rows:[{id:'SQ-001',contract:'HT-AH-001',scheme:'舒适洁牙权益',mode:'按比例',value:20,status:'已启用',version:1},
      {id:'SQ-002',contract:'HT-2026-002',scheme:'舒适洁牙权益',mode:'按金额',value:18,status:'已启用',version:1},
      {id:'SQ-003',contract:'HT-XH-001',scheme:'舒适洁牙权益',mode:'按金额',value:10,status:'已启用',version:1}],
    notice:'仅已生效合同 + 已启用授权 + 已启用推广产品允许新业务。比例基数是单次获客费，不是卡单价。两方分配四舍五入至分，平台取剩余收益；历史履约不受停用影响。',
    create:{label:'添加推广产品',create:true,next:'已启用',fields,guard:'allocation',defaults:{mode:'按比例'}},
    actions:[{label:'编辑分配',fields,guard:'allocation'},
      {label:'停用授权',when:['已启用'],next:'已停用',danger:true,fields:[reason],hint:'仅限制后续新业务，已发权益、已开卡和已有预约不作废。'},
      {label:'启用授权',when:['已停用'],next:'已启用',guard:'allocation',fields:[reason]}],
    detailNote:'合同期限决定授权期限。明细版本与变更前后记录保留在操作记录；历史核销仍按核销时锁定快照结算。'
  });
  const sources=page('sources');
  sources.title='来源展示名配置';
  sources.create.fields.find(f=>f.key==='owner').dynamic='resourceParties';
  sources.actions.unshift({label:'编辑展示名',fields:[{key:'name',label:'客户侧展示名称',type:'text'},reason]});
  sources.actions.push({label:'启用',when:['已停用'],next:'已启用',fields:[reason]});
  sources.notice='平台按资源方维护专属名称列表；编辑/停用仅影响后续投放，历史展示快照和实际来源归属不变。';
  page('institutions').actions.unshift({label:'来源展示名',link:'sources',filterKey:'owner',filterFrom:'name',types:['保险公司','银行','经纪代理公司']},
    {label:'合作合同',link:'contracts',filterKey:'party',filterFrom:'name'});
  for(const r of page('imports').rows){r.owner='安和经纪（演示）';r.scheme='舒适洁牙权益';}
  for(const r of page('orders').rows)r.owner='安和经纪（演示）';
})();
