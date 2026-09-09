window.PROTOTYPE = {
  "role": "resource",
  "title": "客户资源方后台",
  "org": "安和经纪（演示）",
  "scope": "仅本机构客户关系和来源权益",
  "user": "资源方管理员",
  "greeting": "客户福利工作台",
  "description": "管理名单投放、购卡申请和本机构权益履约",
  "alertTitle": "1个导入批次需要修正",
  "alert": "资料修正名单存在手机号与姓名不一致的明细，未产生权益。请修正后重新导入。",
  "cards": [
    {
      "title": "待审核批次",
      "page": "imports",
      "status": [
        "待审核"
      ],
      "foot": "查看导入进度",
      "note": "平台审核后，客户可在小程序领取"
    },
    {
      "title": "待处理开卡",
      "page": "orders",
      "status": [
        "待审核",
        "待收款"
      ],
      "foot": "查看购卡订单",
      "note": "平台逐单定价，线下付款后开卡"
    },
    {
      "title": "异常批次",
      "page": "imports",
      "status": [
        "数据异常"
      ],
      "foot": "查看错误明细",
      "note": "修正手机号与姓名后重新导入"
    },
    {
      "title": "待核对收益",
      "page": "earnings",
      "status": [
        "待核对"
      ],
      "foot": "查看本方对账",
      "note": "仅查看本机构收益和明细"
    }
  ],
  "sideTitle": "本机构投放规则",
  "side": [
    [
      "可用来源",
      "安和保险客户福利"
    ],
    [
      "权益有效期",
      "领取或激活后起算，默认180天"
    ],
    [
      "合作合同",
      "2026-01-01 至 2026-12-31"
    ]
  ],
  "pages": [
    {
      "id": "imports",
      "prefix": "PL",
      "title": "Excel 批次",
      "description": "查看批次审核、匹配异常和领取结果",
      "columns": [
        [
          "name",
          "导入批次"
        ],
        [
          "source",
          "来源展示名"
        ],
        [
          "quantity",
          "总权益数"
        ],
        [
          "claimed",
          "已领取"
        ],
        [
          "remaining",
          "未领取"
        ],
        [
          "status",
          "批次状态"
        ]
      ],
      "rows": [
        {
          "id": "PL-0907-001",
          "name": "9月客户关怀名单",
          "source": "安和保险客户福利",
          "quantity": 100,
          "claimed": 0,
          "remaining": 100,
          "status": "待审核",
          "days": 180,
          "note": "100条格式校验通过；审核后匹配并分配权益"
        },
        {
          "id": "PL-0906-002",
          "name": "周末福利名单",
          "source": "安和保险客户福利",
          "quantity": 80,
          "claimed": 12,
          "remaining": 68,
          "status": "已入账",
          "days": 180,
          "note": "手机号匹配成功；该来源仅保留本机构权益"
        },
        {
          "id": "PL-0905-003",
          "name": "信用客户福利名单",
          "source": "安和保险客户福利",
          "quantity": 30,
          "claimed": 0,
          "remaining": 30,
          "status": "已入账",
          "days": 180,
          "note": "全部未领取，允许整批回滚"
        },
        {
          "id": "PL-0904-004",
          "name": "资料修正名单",
          "source": "安和保险客户福利",
          "quantity": 10,
          "claimed": 0,
          "remaining": 0,
          "status": "数据异常",
          "note": "第8行手机号与姓名不一致，未匹配或发放；请修正文件重新导入"
        }
      ],
      "export": true,
      "detailNote": "权益从客户领取日起算有效期；已领取的批次不能回滚。跨批重复上传暂不业务去重。",
      "create": {
        "label": "新建导入批次",
        "create": true,
        "defaults": {
          "source": "安和保险客户福利"
        },
        "fields": [
          {
            "key": "name",
            "label": "批次名称",
            "type": "text"
          },
          {
            "key": "source",
            "label": "来源展示名",
            "type": "text",
            "options": [
              "安和保险客户福利"
            ]
          },
          {
            "key": "file",
            "label": "客户权益 Excel",
            "type": "excel"
          }
        ],
        "hint": "选择本机构来源展示名，再上传标准模板。演示仅记录文件名，不读取或上传客户资料。"
      },
      "actions": [
        {
          "label": "整批回滚",
          "when": [
            "已入账"
          ],
          "next": "已回滚",
          "guard": "unclaimed",
          "danger": true,
          "fields": [
            {
              "key": "reason",
              "label": "处理原因",
              "type": "textarea"
            }
          ],
          "hint": "只有全部权益未领取时允许回滚；已领取批次会被拒绝。"
        },
        {
          "label": "申请停止剩余",
          "when": [
            "已入账"
          ],
          "next": "停止待审核",
          "fields": [
            {
              "key": "reason",
              "label": "处理原因",
              "type": "textarea"
            }
          ],
          "hint": "仅申请停止剩余未领取权益，已领取权益继续保留。"
        }
      ]
    },
    {
      "id": "orders",
      "prefix": "KC",
      "title": "开卡订单",
      "description": "跟踪申请、定价、收款、开卡和实体卡寄送",
      "columns": [
        [
          "name",
          "购卡申请"
        ],
        [
          "scheme",
          "推广产品"
        ],
        [
          "quantity",
          "卡片数量"
        ],
        [
          "price",
          "单价（元）"
        ],
        [
          "amount",
          "总金额（元）"
        ],
        [
          "activated",
          "已激活"
        ],
        [
          "status",
          "订单状态"
        ]
      ],
      "rows": [
        {
          "id": "KC-0907-001",
          "name": "9月客户礼遇开卡",
          "scheme": "舒适洁牙权益",
          "quantity": 100,
          "price": "待定价",
          "amount": "待定价",
          "activated": 0,
          "status": "待审核",
          "source": "安和保险客户福利",
          "days": 180
        },
        {
          "id": "KC-0906-002",
          "name": "秋季关怀开卡",
          "scheme": "舒适洁牙权益",
          "quantity": 50,
          "price": 20,
          "amount": 1000,
          "activated": 0,
          "status": "待收款",
          "source": "安和保险客户福利",
          "days": 180
        },
        {
          "id": "KC-0901-003",
          "name": "信用卡客户礼遇",
          "scheme": "舒适洁牙权益",
          "quantity": 80,
          "price": 18,
          "amount": 1440,
          "activated": 8,
          "status": "已寄送",
          "source": "安和保险客户福利",
          "days": 180
        }
      ],
      "notice": "卡片没有激活截止日期，激活后默认有效180天。单价由平台审核时确定。",
      "export": true,
      "create": {
        "label": "申请开卡",
        "create": true,
        "defaults": {
          "quantity": 100,
          "perCard": 1
        },
        "fields": [
          {
            "key": "name",
            "label": "申请名称",
            "type": "text"
          },
          {
            "key": "scheme",
            "label": "推广产品",
            "type": "text",
            "options": [
              "舒适洁牙权益",
              "种植牙抵用权益",
              "正畸抵用权益"
            ]
          },
          {
            "key": "source",
            "label": "来源展示名",
            "type": "text",
            "options": [
              "安和保险客户福利"
            ]
          },
          {
            "key": "quantity",
            "label": "卡片数量",
            "type": "number",
            "min": 1,
            "integer": true
          },
          {
            "key": "perCard",
            "label": "每卡权益份数",
            "type": "number",
            "min": 1,
            "integer": true
          },
          {
            "key": "address",
            "label": "实体卡收件地址",
            "type": "text"
          }
        ],
        "hint": "提交方案和数量，平台审核时确定单价。无需在此线上付款。"
      },
      "actions": [
        {
          "label": "申请取消",
          "when": [
            "待审核",
            "待收款",
            "已寄送",
            "制作中"
          ],
          "next": "取消待审核",
          "guard": "unactivated",
          "danger": true,
          "fields": [
            {
              "key": "reason",
              "label": "处理原因",
              "type": "textarea"
            }
          ],
          "hint": "订单任一卡片已激活则不能取消；已付款订单的退款由平台在线下完成。"
        }
      ]
    },
    {
      "id": "cards",
      "prefix": "CARD",
      "title": "卡片批次",
      "description": "查看本机构实体卡寄送和激活结果",
      "columns": [
        [
          "name",
          "批次名称"
        ],
        [
          "quantity",
          "总张数"
        ],
        [
          "activated",
          "已激活"
        ],
        [
          "remaining",
          "未激活"
        ],
        [
          "status",
          "状态"
        ]
      ],
      "rows": [
        {
          "id": "CARD-0901",
          "name": "信用卡客户礼遇",
          "quantity": 80,
          "activated": 8,
          "remaining": 72,
          "status": "已寄送",
          "note": "物流凭据 DEMO-SHIP-001；激活后有效180天"
        }
      ],
      "export": true,
      "detailNote": "本原型仅导出状态清单，不生成可用于真实激活的卡片凭证。"
    },
    {
      "id": "customers",
      "prefix": "KH",
      "title": "客户与权益",
      "description": "查看与本机构关联的客户及本方权益",
      "columns": [
        [
          "name",
          "客户姓名"
        ],
        [
          "phone",
          "手机号"
        ],
        [
          "external",
          "本方客户编号"
        ],
        [
          "mode",
          "权益来源"
        ],
        [
          "quantity",
          "权益份数"
        ],
        [
          "status",
          "权益状态"
        ]
      ],
      "rows": [
        {
          "id": "KH-001",
          "name": "客户甲（演示）",
          "phone": "13800000011",
          "external": "AH-001",
          "mode": "Excel 名单",
          "quantity": 1,
          "status": "待领取"
        },
        {
          "id": "KH-002",
          "name": "客户乙（演示）",
          "phone": "13800000012",
          "external": "AH-002",
          "mode": "不记名卡激活",
          "quantity": 1,
          "status": "可使用"
        },
        {
          "id": "KH-003",
          "name": "客户丙（演示）",
          "phone": "13800000013",
          "external": "AH-003",
          "mode": "Excel 名单",
          "quantity": 1,
          "status": "已核销"
        }
      ],
      "export": true,
      "notice": "仅显示本机构关系及权益，客户其他来源关系不可见。手机号均为虚构测试数据。"
    },
    {
      "id": "appointments",
      "prefix": "YY",
      "title": "预约记录",
      "description": "查看预约、改期请求及履约结果",
      "columns": [
        [
          "name",
          "客户"
        ],
        [
          "clinic",
          "门诊"
        ],
        [
          "scheme",
          "推广产品"
        ],
        [
          "date",
          "预约日期"
        ],
        [
          "time",
          "预约时间"
        ],
        [
          "status",
          "预约状态"
        ]
      ],
      "rows": [
        {
          "id": "YY-0907-001",
          "name": "客户甲（演示）",
          "clinic": "明禾口腔（演示）",
          "scheme": "舒适洁牙权益",
          "date": "2026-09-08",
          "time": "10:00",
          "status": "待确认",
          "phone": "13800000011",
          "expiry": "2027-03-05",
          "note": "意向时间 2026-09-08 10:00；待确认剩余18小时"
        },
        {
          "id": "YY-0907-002",
          "name": "客户乙（演示）",
          "clinic": "明禾口腔（演示）",
          "scheme": "舒适洁牙权益",
          "date": "2026-09-09",
          "time": "14:30",
          "status": "成功",
          "phone": "13800000012",
          "expiry": "2027-03-05",
          "note": "客户申请改至2026-09-10 15:00，等待门诊确认，原时间仍有效"
        },
        {
          "id": "YY-0906-003",
          "name": "客户丙（演示）",
          "clinic": "明禾口腔（演示）",
          "scheme": "舒适洁牙权益",
          "date": "2026-09-06",
          "time": "11:00",
          "status": "完成",
          "phone": "13800000013",
          "expiry": "2027-03-05",
          "note": "已核销1份，获客费60元"
        }
      ],
      "notice": "本方来源权益的预约履约查询。预约确认、改期和核销由门诊操作。",
      "export": true
    },
    {
      "id": "earnings",
      "prefix": "DZ",
      "title": "收益对账",
      "description": "核对本机构月度收益与核销来源明细",
      "columns": [
        [
          "name",
          "对账月份"
        ],
        [
          "count",
          "核销笔数"
        ],
        [
          "amount",
          "本方收益（元）"
        ],
        [
          "adjustment",
          "调整金额（元）"
        ],
        [
          "status",
          "状态"
        ]
      ],
      "rows": [
        {
          "id": "DZ-202608",
          "name": "2026年08月",
          "count": 40,
          "amount": 480,
          "adjustment": 0,
          "status": "待核对"
        },
        {
          "id": "DZ-202607",
          "name": "2026年07月",
          "count": 25,
          "amount": 300,
          "adjustment": 0,
          "status": "已结账"
        }
      ],
      "actions": [
        {
          "label": "确认结账",
          "when": [
            "待核对"
          ],
          "next": "已结账",
          "fields": [
            {
              "key": "confirmed",
              "label": "已核对明细及线下结算情况",
              "type": "checkbox"
            }
          ]
        },
        {
          "label": "提出异议",
          "when": [
            "待核对"
          ],
          "next": "有异议",
          "fields": [
            {
              "key": "reason",
              "label": "处理原因",
              "type": "textarea"
            }
          ]
        }
      ],
      "export": true,
      "notice": "仅显示本机构收益。结账用于登记处理结果，不执行线上资金划转。"
    },
    {
      "id": "contracts",
      "prefix": "HT",
      "title": "合作合同",
      "description": "按合同主体、期限和版本查看业务授权",
      "columns": [
        [
          "name",
          "合同名称"
        ],
        [
          "type",
          "合同类型"
        ],
        [
          "start",
          "生效日期"
        ],
        [
          "end",
          "到期日期"
        ],
        [
          "cycle",
          "结算周期"
        ],
        [
          "credit",
          "信用额度（元）"
        ],
        [
          "status",
          "状态"
        ]
      ],
      "rows": [
        {
          "id": "HT-AH-001",
          "name": "资源方年度合作合同",
          "type": "平台—资源方",
          "start": "2026-01-01",
          "end": "2026-12-31",
          "cycle": "—",
          "credit": "—",
          "status": "已生效",
          "note": "可提交Excel名单、开卡申请，使用安和保险客户福利展示名"
        }
      ],
      "detailNote": "合同失效将限制新业务；历史权益、预约和账单继续保留。"
    },
    {
      "id": "accounts",
      "prefix": "USER",
      "title": "账号管理",
      "description": "维护本机构账号和手机号绑定状态",
      "columns": [
        [
          "name",
          "员工姓名"
        ],
        [
          "phone",
          "绑定手机号"
        ],
        [
          "role",
          "基础角色"
        ],
        [
          "status",
          "账号状态"
        ]
      ],
      "rows": [
        {
          "id": "USER-001",
          "name": "林晓（演示）",
          "phone": "13800000001",
          "role": "机构管理员",
          "status": "正常"
        },
        {
          "id": "USER-002",
          "name": "陈宁（演示）",
          "phone": "13800000002",
          "role": "业务操作员",
          "status": "待绑定"
        }
      ],
      "create": {
        "label": "开通账号",
        "create": true,
        "next": "待绑定",
        "fields": [
          {
            "key": "name",
            "label": "员工姓名",
            "type": "text"
          },
          {
            "key": "phone",
            "label": "手机号",
            "type": "text"
          },
          {
            "key": "role",
            "label": "基础角色",
            "type": "text",
            "options": [
              "机构管理员",
              "业务操作员"
            ]
          }
        ]
      },
      "actions": [
        {
          "label": "停用账号",
          "when": [
            "正常",
            "待绑定"
          ],
          "next": "已停用",
          "danger": true,
          "fields": [
            {
              "key": "reason",
              "label": "处理原因",
              "type": "textarea"
            }
          ]
        },
        {
          "label": "启用账号",
          "when": [
            "已停用"
          ],
          "next": "正常",
          "fields": [
            {
              "key": "reason",
              "label": "处理原因",
              "type": "textarea"
            }
          ]
        }
      ],
      "notice": "员工按预留手机号完成绑定。详细岗位权限在后续权限评审中确定。"
    },
    {
      "id": "audit",
      "prefix": "LOG",
      "title": "操作记录",
      "description": "查看本机构业务变更及操作原因",
      "columns": [
        [
          "name",
          "操作"
        ],
        [
          "subject",
          "业务编号"
        ],
        [
          "operator",
          "操作人"
        ],
        [
          "time",
          "操作时间"
        ],
        [
          "status",
          "状态"
        ]
      ],
      "rows": [
        {
          "id": "LOG-001",
          "name": "提交业务审核",
          "subject": "DEMO-0907",
          "operator": "演示管理员",
          "time": "2026-09-07 09:10",
          "status": "已记录"
        }
      ],
      "export": true
    }
  ]
};

// 仅本机构合同授权，不加载其他资源方及渠道方分配信息。
window.PROTOTYPE.schemeCatalog=[{name:'舒适洁牙权益',fee:60,status:'已启用'},{name:'种植牙抵用权益',fee:180,status:'草稿'},{name:'正畸抵用权益',fee:150,status:'草稿'}];
(() => {
  const pages=window.PROTOTYPE.pages,contracts=pages.find(p=>p.id==='contracts');
  contracts.rows[0].party=window.PROTOTYPE.org;
  contracts.title='平台合作合同';
  contracts.description='本机构与平台的唯一主合同，可绑定多个推广产品';
  contracts.columns=contracts.columns.filter(c=>!['credit','cycle'].includes(c[0]));
  contracts.notice='本机构只设一份平台主合同。新增推广产品在该合同内授权，续签或变更保留历史版本，不另建平行合同。';
  contracts.actions=[{label:'查看授权方案',link:'contractSchemes',filterKey:'contract',filterFrom:'id'}];
  pages.splice(pages.indexOf(contracts)+1,0,{id:'contractSchemes',title:'合同授权产品',prefix:'SQ',description:'仅展示本机构合同的方案使用权与本方收益规则',
    columns:[['contract','合同编号'],['scheme','推广产品'],['fee','获客费（元）'],['mode','本方分配方式'],['value','分配值'],['payout','本方元/次'],['access','新业务授权'],['status','配置状态']],
    rows:[{id:'SQ-AH-001',contract:'HT-AH-001',scheme:'舒适洁牙权益',mode:'按比例',value:20,status:'已启用',version:1}],notice:'授权由平台在合同中维护；本方只能查看。无有效授权不能新建开卡申请或导入该方案。'});
  for(const id of ['orders','imports']){
    const p=pages.find(p=>p.id===id);
    const field=p.create.fields.find(f=>f.key==='scheme');
    if(field)field.dynamic='authorizedSchemes';
    else p.create.fields.splice(1,0,{key:'scheme',label:'本次校验方案（演示）',dynamic:'authorizedSchemes'});
  }
  pages.find(p=>p.id==='imports').create.hint='原型用单项方案演示合同授权校验；正式 Excel 仍允许多方案，每行分别校验。仅记录文件名，不解析或上传客户资料。';
})();
