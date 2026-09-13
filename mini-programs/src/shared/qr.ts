import qrcode = require('./vendor/qrcode');
export function matrix(value:string):boolean[][] {
  if(!value||value.length>200)throw new Error('核销凭证无效，请刷新预约');
  const code=qrcode(0,'M');code.addData(value,'Byte');code.make();
  return Array.from({length:code.getModuleCount()},(_,row)=>Array.from({length:code.getModuleCount()},(_,col)=>code.isDark(row,col)));
}
Component({
  properties:{credential:{type:String,value:'',observer:'render'}},
  data:{error:''},
  lifetimes:{ready(){this.render();}},
  methods:{render(){
    const credential=this.properties.credential;
    if(!credential)return;
    this.createSelectorQuery().select('#qr').fields({node:true,size:true}).exec((results:any[])=>{
      const item=results[0];if(!item?.node)return;
      try{const cells=matrix(credential),count=cells.length,padding=4,size=(count+padding*2)*8;
        const canvas=item.node;canvas.width=size;canvas.height=size;const context=canvas.getContext('2d');
        context.fillStyle='#ffffff';context.fillRect(0,0,size,size);context.fillStyle='#1d2129';
        cells.forEach((row,y)=>row.forEach((dark,x)=>{if(dark)context.fillRect((x+padding)*8,(y+padding)*8,8,8);}));this.setData({error:''});
      }catch{this.setData({error:'核销码加载失败，请刷新预约详情'});}
    });
  }},
});
