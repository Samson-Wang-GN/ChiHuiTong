import {Entity, Field, View, Row, statuses, dateText, appointmentRow} from './model';
import * as R from './runtime';
export interface Context { params: Entity; form: Entity; status: string; page: number; cache: Entity; }
export interface Screen { admin?: boolean; public?: boolean; load(ctx:Context):Promise<View>; action?(ctx:Context,key:string,id?:string):Promise<void>; submit?(ctx:Context):Promise<void>; }
export const field = (key:string,label:string,type='text',value=''):Field => ({key,label,type,value,required:true});
export const fact = (label:string,value:any) => ({label,value:value===null || value===undefined || value===''?'—':String(value)});
export function tabs(keys:string[], counts:Entity={}): {key:string;label:string}[] {return ['all',...keys].map(key=>({key,label:(statuses[key]||key)+(counts[key]===undefined?'':'（'+counts[key]+'）')}));}
export async function list(ctx:Context,path:string,keys:string[],render:(row:Entity)=>Row,title:string):Promise<View> {
  const data = await R.request(path+(path.includes('?')?'&':'?')+R.query({status:ctx.status,page:ctx.page,page_size:20}));
  ctx.cache.rows=data.results;
  return {title,rows:data.results.map(render),tabs:tabs(keys,data.counts||data.status_counts),total:data.total,page:ctx.page};
}
export function timestamp(form:Entity):string {if (!/^\d{4}-\d{2}-\d{2}$/.test(form.date||'') || !/^\d{2}:\d{2}$/.test(form.time||'')) throw new Error('请选择日期和时间');return form.date+'T'+form.time+':00+08:00';}
export const timeFields = ():Field[] => [field('date','日期','date'),field('time','时间','time')];
export async function detail(ctx:Context,path:string):Promise<Entity> {const obj=await R.request(path);ctx.cache.object=obj;return obj;}
export function required(form:Entity,key:string,label:string):string {const value=String(form[key]||'').trim();if(!value)throw new Error('请填写'+label);return value;}
export function checkTime(form:Entity,expires?:string):string {const value=timestamp(form);if(new Date(value).getTime()<=Date.now()) throw new Error('预约时间须晚于当前时间');if(expires && value.slice(0,10)>dateText(expires).slice(0,10)) throw new Error('预约或改期日期不能超过权益有效期');return value;}
export async function command(path:string,data:Entity,confirmation:string):Promise<boolean> {if(!await R.confirm(confirmation)) return false;await R.request(path,'POST',data,true);return true;}
export function appointmentFacts(a:Entity) {return [fact('推广产品',a.external_name),fact('门诊',a.clinic_name),fact('权益来源',a.source_name),fact('预约状态',statuses[a.status]),fact('预约时间',dateText(a.scheduled_at||a.requested_at)),fact('门诊结算',a.clinic_settled?'已结清':'尚未结清或未产生费用')];}
export function listAppointments(ctx:Context):Promise<View> {return list(ctx,'/appointments',['pending','success','completed','cancelled'],appointmentRow,'我的预约');}
