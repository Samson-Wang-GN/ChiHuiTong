window.PROTOTYPE = {
  "role": "channel",
  "title": "门诊渠道后台",
  "org": "启明渠道（演示）",
  "scope": "仅签约门诊 · 负责业务员范围",
  "user": "陈宁",
  "greeting": "门诊服务工作台",
  "description": "跟进入驻、合同、额度申请和账单催收",
  "alertTitle": "1家门诊账单逾期，待催收",
  "alert": "青禾口腔待付账单720元，请联系门诊完成付款。渠道承担催收，不承担担保责任。",
  "cards": [
    {
      "title": "待审核门诊",
      "page": "clinics",
      "status": [
        "待审核"
      ],
      "foot": "跟进入驻审核",
      "note": "检查资质、合同和负责业务员"
    },
    {
      "title": "逾期账单",
      "page": "bills",
      "status": [
        "已逾期"
      ],
      "foot": "查看催收任务",
      "note": "每日查看欠款及付款截止时间"
    },
    {
      "title": "待审额度申请",
      "page": "credit",
      "status": [
        "待审核"
      ],
      "foot": "跟进额度审批",
      "note": "调额和冻结申请由平台审核"
    },
    {
      "title": "即将到期合同",
      "page": "contracts",
      "status": [
        "即将到期"
      ],
      "foot": "跟进续签",
      "note": "到期前30天提醒负责业务员"
    }
  ],
  "sideTitle": "负责门诊提醒",
  "side": [
    [
      "明禾口腔",
      "合同将在2026-09-30到期"
    ],
    [
      "青禾口腔",
      "逾期720元，存量预约继续履约"
    ],
    [
      "业务员手机号",
      "已绑定13800000002，接收催收通知"
    ]
  ],
  "pages": [
    {
      "id": "clinics",
      "prefix": "MZ",
      "title": "门诊管理",
      "description": "按持证经营地址管理门诊，跟进审核和上线条件",
      "columns": [
        [
          "name",
          "门诊名称"
        ],
        [
          "address",
          "经营地址"
        ],
        [
          "rep",
          "负责业务员"
        ],
        [
          "credit",
          "信用额度（元）"
        ],
        [
          "status",
          "服务状态"
        ]
      ],
      "rows": [
        {
          "id": "MZ-001",
          "name": "明禾口腔（演示）",
          "address": "演示市春和路12号",
          "rep": "陈宁（演示）",
          "credit": 3000,
          "status": "正常",
          "note": "营业执照、医疗机构执业许可证齐全；平台及渠道合同有效"
        },
        {
          "id": "MZ-002",
          "name": "青禾口腔（演示）",
          "address": "演示市景明路28号",
          "rep": "陈宁（演示）",
          "credit": 2400,
          "status": "服务中",
          "note": "已逾期720元；继续完成已有预约"
        },
        {
          "id": "MZ-003",
          "name": "映禾口腔（演示）",
          "address": "演示市滨河路36号",
          "rep": "林晓（演示）",
          "credit": 5000,
          "status": "待审核",
          "note": "资料已提交；审核周期2个工作日"
        }
      ],
      "create": {
        "label": "录入签约门诊",
        "create": true,
        "guard": "contract",
        "fields": [
          {
            "key": "name",
            "label": "门诊名称",
            "type": "text"
          },
          {
            "key": "subject",
            "label": "经营主体",
            "type": "text"
          },
          {
            "key": "address",
            "label": "持证经营地址",
            "type": "text"
          },
          {
            "key": "phone",
            "label": "预约联系手机号",
            "type": "text"
          },
          {
            "key": "rep",
            "label": "负责业务员",
            "type": "text",
            "options": [
              "陈宁（演示）",
              "林晓（演示）"
            ]
          },
          {
            "key": "license",
            "label": "营业执照",
            "type": "file"
          },
          {
            "key": "medical",
            "label": "医疗机构执业许可证",
            "type": "file"
          },
          {
            "key": "start",
            "label": "合同生效日期",
            "type": "date"
          },
          {
            "key": "end",
            "label": "合同到期日期",
            "type": "date"
          },
          {
            "key": "credit",
            "label": "合同信用额度（元）",
            "type": "number"
          },
          {
            "key": "cycle",
            "label": "结算周期",
            "type": "text",
            "options": [
              "周结",
              "月结"
            ]
          },
          {
            "key": "attachment",
            "label": "合同附件",
            "type": "file"
          }
        ]
      },
      "actions": [
        {
          "label": "补充资料",
          "when": [
            "待审核",
            "审核不通过"
          ],
          "fields": [
            {
              "key": "name",
              "label": "门诊名称",
              "type": "text"
            },
            {
              "key": "subject",
              "label": "经营主体",
              "type": "text"
            },
            {
              "key": "address",
              "label": "持证经营地址",
              "type": "text"
            },
            {
              "key": "phone",
              "label": "预约联系手机号",
              "type": "text"
            },
            {
              "key": "rep",
              "label": "负责业务员",
              "type": "text",
              "options": [
                "陈宁（演示）",
                "林晓（演示）"
              ]
            },
            {
              "key": "license",
              "label": "营业执照",
              "type": "file"
            },
            {
              "key": "medical",
              "label": "医疗机构执业许可证",
              "type": "file"
            },
            {
              "key": "start",
              "label": "合同生效日期",
              "type": "date"
            },
            {
              "key": "end",
              "label": "合同到期日期",
              "type": "date"
            },
            {
              "key": "credit",
              "label": "合同信用额度（元）",
              "type": "number"
            },
            {
              "key": "cycle",
              "label": "结算周期",
              "type": "text",
              "options": [
                "周结",
                "月结"
              ]
            },
            {
              "key": "attachment",
              "label": "合同附件",
              "type": "file"
            }
          ],
          "next": "待审核"
        }
      ]
    },
    {
      "id": "contracts",
      "prefix": "HT",
      "title": "合同管理",
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
          "id": "HT-2026-001",
          "name": "年度合作服务合同",
          "type": "平台—门诊",
          "party": "明禾口腔（演示）",
          "start": "2026-01-01",
          "end": "2026-09-30",
          "cycle": "周结",
          "credit": 3000,
          "status": "即将到期",
          "note": "26.09 版本，距到期不足30天；存量预约继续履约。"
        },
        {
          "id": "HT-2026-002",
          "name": "年度渠道合作合同",
          "type": "平台—渠道公司",
          "start": "2026-01-01",
          "end": "2026-12-31",
          "cycle": "—",
          "credit": "—",
          "status": "已生效"
        }
      ],
      "detailNote": "合同失效将限制新业务；历史权益、预约和账单继续保留。",
      "create": {
        "label": "录入合作合同",
        "create": true,
        "guard": "contract",
        "fields": [
          {
            "key": "name",
            "label": "合同名称",
            "type": "text"
          },
          {
            "key": "party",
            "label": "门诊",
            "type": "text",
            "options": [
              "明禾口腔（演示）",
              "青禾口腔（演示）",
              "映禾口腔（演示）"
            ]
          },
          {
            "key": "start",
            "label": "生效日期",
            "type": "date"
          },
          {
            "key": "end",
            "label": "到期日期",
            "type": "date"
          },
          {
            "key": "credit",
            "label": "信用额度（门诊合同）",
            "type": "number"
          },
          {
            "key": "cycle",
            "label": "结算周期",
            "type": "text",
            "options": [
              "周结",
              "月结"
            ]
          },
          {
            "key": "contact",
            "label": "结算联系人",
            "type": "text"
          },
          {
            "key": "attachment",
            "label": "合同附件",
            "type": "file"
          }
        ],
        "defaults": {
          "type": "渠道公司—门诊"
        }
      }
    },
    {
      "id": "credit",
      "prefix": "ED",
      "title": "额度申请",
      "description": "负责业务员提交调额或冻结申请，平台审核后生效",
      "columns": [
        [
          "name",
          "门诊"
        ],
        [
          "type",
          "申请类型"
        ],
        [
          "credit",
          "申请额度（元）"
        ],
        [
          "reason",
          "原因"
        ],
        [
          "status",
          "状态"
        ]
      ],
      "rows": [
        {
          "id": "ED-001",
          "name": "明禾口腔（演示）",
          "type": "调整额度",
          "credit": 5000,
          "reason": "合同变更已补充",
          "status": "待审核"
        }
      ],
      "create": {
        "label": "提交额度申请",
        "create": true,
        "fields": [
          {
            "key": "name",
            "label": "负责门诊",
            "type": "text",
            "options": [
              "明禾口腔（演示）",
              "青禾口腔（演示）"
            ]
          },
          {
            "key": "type",
            "label": "申请类型",
            "type": "text",
            "options": [
              "调整额度",
              "冻结业务"
            ]
          },
          {
            "key": "credit",
            "label": "申请额度（元）",
            "type": "number"
          },
          {
            "key": "reason",
            "label": "处理原因",
            "type": "textarea"
          },
          {
            "key": "attachment",
            "label": "合同变更依据",
            "type": "file"
          }
        ]
      },
      "notice": "本页面不直接改变门诊额度。申请人须有后台账号且已绑定手机号。"
    },
    {
      "id": "bills",
      "prefix": "ZD",
      "title": "欠款与催收",
      "description": "查看账期、付款凭证与到账确认结果",
      "columns": [
        [
          "name",
          "门诊"
        ],
        [
          "period",
          "账期"
        ],
        [
          "amount",
          "应付金额（元）"
        ],
        [
          "deadline",
          "付款截止"
        ],
        [
          "status",
          "账单状态"
        ]
      ],
      "rows": [
        {
          "id": "ZD-202609-001",
          "name": "明禾口腔（演示）",
          "period": "2026-08-31 至 09-06",
          "amount": 1260,
          "issueDate": "2026-09-07",
          "deadline": "2026-09-10",
          "status": "待付款",
          "note": "周结，出账次日起3个自然日；单次60元×21笔"
        },
        {
          "id": "ZD-202608-002",
          "name": "青禾口腔（演示）",
          "period": "2026-08-24 至 08-30",
          "amount": 720,
          "issueDate": "2026-08-31",
          "deadline": "2026-09-03",
          "status": "已逾期",
          "note": "账单逾期仅提醒；上下线由平台人工处理"
        }
      ],
      "notice": "款项在线下支付；整张账单全额到账后统一冲销，不支持部分冲销。",
      "export": true,
      "actions": [
        {
          "label": "记录催收",
          "when": [
            "待付款",
            "已逾期",
            "付款待确认"
          ],
          "fields": [
            {
              "key": "contactTime",
              "label": "联系日期",
              "type": "date"
            },
            {
              "key": "reason",
              "label": "跟进记录",
              "type": "textarea"
            }
          ],
          "success": "已保存催收记录，账单状态不变"
        }
      ]
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
          "phone": "138****0011",
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
          "phone": "138****0012",
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
          "phone": "138****0013",
          "expiry": "2027-03-05",
          "note": "已核销1份，获客费60元"
        }
      ],
      "notice": "仅查看签约门诊预约；不提供确认、取消、改期或核销操作。",
      "export": true
    },
    {
      "id": "offers",
      "prefix": "YH",
      "title": "门诊优惠",
      "description": "为签约门诊选择是否承接平台优惠",
      "columns": [
        [
          "name",
          "门诊"
        ],
        [
          "scheme",
          "平台方案"
        ],
        [
          "fee",
          "获客费（元）"
        ],
        [
          "status",
          "状态"
        ]
      ],
      "rows": [
        {
          "id": "YH-001",
          "name": "明禾口腔（演示）",
          "scheme": "舒适洁牙权益",
          "fee": 60,
          "status": "已上线"
        },
        {
          "id": "YH-002",
          "name": "明禾口腔（演示）",
          "scheme": "种植牙抵用权益",
          "fee": 180,
          "status": "已下线"
        }
      ],
      "actions": [
        {
          "label": "上线优惠",
          "when": [
            "已下线"
          ],
          "next": "已上线",
          "fields": [
            {
              "key": "reason",
              "label": "处理原因",
              "type": "textarea"
            }
          ]
        },
        {
          "label": "下线优惠",
          "when": [
            "已上线"
          ],
          "next": "已下线",
          "danger": true,
          "fields": [
            {
              "key": "reason",
              "label": "处理原因",
              "type": "textarea"
            }
          ],
          "hint": "立即停止此优惠的新预约，已有确认预约继续履约。"
        }
      ],
      "notice": "方案规则由平台统一配置；门诊或所属渠道的上下线操作无需平台审核。"
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
      "id": "accounts",
      "prefix": "USER",
      "title": "业务员账号",
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

// 渠道只查看自身合同分配，不包含客户资源方合同。
window.PROTOTYPE.schemeCatalog=[{name:'舒适洁牙权益',fee:60,status:'已启用'},{name:'种植牙抵用权益',fee:180,status:'草稿'}];
(() => {
  const pages=window.PROTOTYPE.pages,contracts=pages.find(p=>p.id==='contracts');
  contracts.rows.find(r=>r.id==='HT-2026-002').party=window.PROTOTYPE.org;
  const clinicContracts=JSON.parse(JSON.stringify(contracts));
  clinicContracts.id='clinicContracts';
  clinicContracts.title='平台与门诊合同';
  clinicContracts.description='查看平台与本渠道负责门诊签订的服务及结算合同';
  clinicContracts.recordType='平台—门诊';
  clinicContracts.legacyPage='contracts';
  clinicContracts.rows=contracts.rows.filter(r=>r.type==='平台—门诊');
  clinicContracts.columns.splice(1,0,['party','签约门诊']);
  clinicContracts.notice='签约双方为平台与门诊；仅展示本渠道负责门诊。渠道可查看合同、信用额度及账期，无权审核生效或直接修改额度。';
  clinicContracts.actions=[];
  clinicContracts.statuses=['草稿','待审核','已审核待生效','已生效','即将到期','已到期','审核不通过','已终止'];
  delete clinicContracts.create;
  contracts.title='与平台合作合同';
  contracts.description='本渠道与平台的合作合同及合同授权权益';
  contracts.recordType='平台—渠道公司';
  contracts.rows=contracts.rows.filter(r=>r.type==='平台—渠道公司');
  contracts.columns=contracts.columns.filter(c=>!['credit','cycle'].includes(c[0]));
  contracts.columns.splice(1,0,['party','签约渠道']);
  contracts.notice='只展示本渠道与平台的合同；平台与负责门诊的合同请进入“平台与门诊合同”。合同可关联多个推广产品。';
  delete contracts.create;
  pages.splice(pages.indexOf(contracts)+1,0,clinicContracts);
  contracts.actions=[{label:'查看授权方案',link:'contractSchemes',filterKey:'contract',filterFrom:'id',types:['平台—渠道公司']}];
  pages.splice(pages.indexOf(contracts)+1,0,{id:'contractSchemes',title:'合同授权产品',prefix:'SQ',description:'本渠道及所属门诊仅可承接合同已授权方案',
    columns:[['contract','合同编号'],['scheme','推广产品'],['fee','获客费（元）'],['mode','本方分配方式'],['value','分配值'],['payout','本方元/次'],['access','新业务授权'],['status','配置状态']],
    rows:[{id:'SQ-QM-001',contract:'HT-2026-002',scheme:'舒适洁牙权益',mode:'按金额',value:18,status:'已启用',version:1}],notice:'平台维护合同授权与分配；渠道不能自行新增授权、修改获客费或分配。所属门诊还需满足自身合同及信用条件。'});
  const offers=pages.find(p=>p.id==='offers');
  offers.columns.splice(3,0,['authorization','合同授权']);
  offers.rows[0].authorization='启明渠道合同已授权';offers.rows[1].authorization='渠道未授权 / 方案未启用';
  offers.notice='上线无需再次平台审核，但必须在当前渠道有效合同授权范围内。未授权方案仅展示限制原因，不能上线；历史预约继续履约。';
})();
