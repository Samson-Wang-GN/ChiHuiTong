window.PROTOTYPE = {
  "role": "clinic",
  "title": "口腔门诊后台",
  "org": "明禾口腔（演示）",
  "scope": "仅本门诊 · 独立合同和额度",
  "user": "门诊管理员",
  "greeting": "预约接待工作台",
  "description": "及时确认预约，跟进改期，完成到诊服务",
  "alertTitle": "本期账单1,260元，请在9月9日前付款",
  "alert": "合同将在9月30日到期，请联系渠道业务员续签。预约确认不记账，核销时才产生获客费。",
  "cards": [
    {
      "title": "待确认预约",
      "page": "appointments",
      "status": [
        "待确认"
      ],
      "foot": "处理客户预约",
      "note": "默认24小时内确认，填写最终日期和时间"
    },
    {
      "title": "成功预约",
      "page": "appointments",
      "status": [
        "成功"
      ],
      "foot": "查看履约安排",
      "note": "门诊改期需确认已与患者协商一致"
    },
    {
      "title": "过期预约待办",
      "page": "followups",
      "status": [
        "待确认",
        "异常搁置"
      ],
      "foot": "核实服务结果",
      "note": "到诊反馈存在时不自动释放权益"
    },
    {
      "title": "待付账单",
      "page": "bills",
      "status": [
        "待付款"
      ],
      "foot": "提交付款凭证",
      "note": "全额到账由平台确认后整体冲销"
    }
  ],
  "sideTitle": "信用与合同",
  "side": [
    [
      "合同信用额度 · ¥3,000",
      "已用额度 ¥1,260 / 可用额度 ¥1,740"
    ],
    [
      "待履约风险 · ¥120",
      "风险余额 ¥1,620，正常接收新预约"
    ],
    [
      "门诊服务合同",
      "2026-09-30到期；周结，出账次日起3个自然日付款"
    ]
  ],
  "pages": [
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
          "phone",
          "手机号"
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
          "note": "意向时间 2026-09-08 10:00；待确认剩余18小时",
          "contact": "13800000011"
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
          "note": "客户申请改至2026-09-10 15:00，等待门诊确认，原时间仍有效",
          "contact": "13800000012"
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
          "note": "已核销1份，获客费60元",
          "contact": "13800000013"
        }
      ],
      "actions": [
        {
          "label": "确认预约",
          "when": [
            "待确认"
          ],
          "next": "成功",
          "fields": [
            {
              "key": "date",
              "label": "最终预约日期",
              "type": "date"
            },
            {
              "key": "time",
              "label": "最终预约时间",
              "type": "time"
            }
          ],
          "hint": "与患者沟通后填写最终时间，不得超过权益到期日。确认预约不占用信用额度。"
        },
        {
          "label": "改期",
          "when": [
            "成功"
          ],
          "fields": [
            {
              "key": "date",
              "label": "新的预约日期",
              "type": "date"
            },
            {
              "key": "time",
              "label": "新的预约时间",
              "type": "time"
            },
            {
              "key": "agreed",
              "label": "已与患者协商一致",
              "type": "checkbox"
            }
          ],
          "hint": "门诊发起改期需先与患者协商，保存后新时间直接生效。"
        },
        {
          "label": "无法接诊",
          "when": [
            "待确认",
            "成功"
          ],
          "next": "取消",
          "danger": true,
          "fields": [
            {
              "key": "reason",
              "label": "处理原因",
              "type": "textarea"
            }
          ],
          "hint": "预约时间前取消释放权益；时间已过须通过过期预约待办处理，不直接释放。"
        },
        {
          "label": "同意客户改期",
          "when": [
            "成功"
          ],
          "fields": [
            {
              "key": "date",
              "label": "确认日期",
              "type": "date"
            },
            {
              "key": "time",
              "label": "确认时间",
              "type": "time"
            }
          ],
          "hint": "请根据详情中客户改期意向确认；所有时间不得超过权益到期日。"
        }
      ],
      "notice": "通过预约详情查看完整联系手机号。核销使用独立门诊端小程序扫码操作。"
    },
    {
      "id": "followups",
      "prefix": "LY",
      "title": "过期预约待办",
      "description": "核实过预约时间仍未核销的记录",
      "columns": [
        [
          "name",
          "客户"
        ],
        [
          "date",
          "原预约日期"
        ],
        [
          "feedback",
          "客户反馈"
        ],
        [
          "note",
          "处理提示"
        ],
        [
          "status",
          "待办状态"
        ]
      ],
      "rows": [
        {
          "id": "LY-001",
          "name": "客户丁（演示）",
          "date": "2026-09-05",
          "feedback": "未反馈",
          "note": "已超过24小时，需核实",
          "status": "待确认"
        },
        {
          "id": "LY-002",
          "name": "客户戊（演示）",
          "date": "2026-09-04",
          "feedback": "已到诊",
          "note": "与门诊反馈不一致，暂停自动释放",
          "status": "异常搁置"
        }
      ],
      "actions": [
        {
          "label": "记录核实结果",
          "when": [
            "待确认"
          ],
          "fields": [
            {
              "key": "feedback",
              "label": "核实结果",
              "type": "text",
              "options": [
                "客户未到",
                "已到诊漏核销",
                "线下已协商改期"
              ]
            },
            {
              "key": "reason",
              "label": "处理原因",
              "type": "textarea"
            }
          ]
        }
      ],
      "notice": "24小时生成待办；72小时无反馈且无待改期或冲突时系统自动完成，保留权益，不核销、不计费。"
    },
    {
      "id": "redemptions",
      "prefix": "HX",
      "title": "核销记录",
      "description": "查看门诊端小程序产生的核销和撤销明细",
      "columns": [
        [
          "name",
          "客户"
        ],
        [
          "scheme",
          "推广产品"
        ],
        [
          "quantity",
          "核销份数"
        ],
        [
          "fee",
          "获客费（元）"
        ],
        [
          "time",
          "核销时间"
        ],
        [
          "status",
          "状态"
        ]
      ],
      "rows": [
        {
          "id": "HX-001",
          "name": "客户丙（演示）",
          "scheme": "舒适洁牙权益",
          "quantity": 1,
          "fee": 60,
          "time": "2026-09-06 11:40",
          "status": "已核销"
        },
        {
          "id": "HX-002",
          "name": "客户己（演示）",
          "scheme": "舒适洁牙权益",
          "quantity": 1,
          "fee": 60,
          "time": "2026-09-05 15:20",
          "status": "已撤销",
          "note": "错误核销已由门诊端撤销；原记录保留"
        }
      ],
      "export": true,
      "notice": "现场核销和错误核销撤销由获授权员工在门诊端小程序完成。"
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
      "id": "bills",
      "prefix": "ZD",
      "title": "信用与账单",
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
        }
      ],
      "notice": "款项在线下支付；整张账单全额到账后统一冲销，不支持部分冲销。",
      "export": true,
      "actions": [
        {
          "label": "提交付款凭证",
          "when": [
            "待付款",
            "已逾期"
          ],
          "next": "付款待确认",
          "fields": [
            {
              "key": "paid",
              "label": "本次付款金额（元）",
              "type": "number",
              "min": 0.01
            },
            {
              "key": "date",
              "label": "付款日期",
              "type": "date"
            },
            {
              "key": "voucher",
              "label": "付款凭证",
              "type": "file"
            }
          ],
          "hint": "提交仅登记付款情况，不代表到账确认。账单全部付清后由平台整体冲销。"
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
        }
      ],
      "detailNote": "合同失效将限制新业务；历史权益、预约和账单继续保留。"
    },
    {
      "id": "profile",
      "prefix": "MZ",
      "title": "门诊资料",
      "description": "维护地址、联系信息及预约处理时限",
      "columns": [
        [
          "name",
          "门诊"
        ],
        [
          "address",
          "经营地址"
        ],
        [
          "phone",
          "预约联系手机号"
        ],
        [
          "timeout",
          "待确认时限（小时）"
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
          "phone": "13800000021",
          "timeout": 24,
          "status": "正常",
          "note": "营业执照、医疗机构执业许可证已审核"
        }
      ],
      "actions": [
        {
          "label": "维护联系信息",
          "fields": [
            {
              "key": "phone",
              "label": "预约联系手机号",
              "type": "text"
            },
            {
              "key": "timeout",
              "label": "待确认时限（小时）",
              "type": "number",
              "min": 1,
              "integer": true
            },
            {
              "key": "hours",
              "label": "营业时间",
              "type": "text"
            }
          ]
        }
      ]
    },
    {
      "id": "accounts",
      "prefix": "USER",
      "title": "员工与小程序",
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
          "role": "管理员",
          "status": "正常"
        },
        {
          "id": "USER-002",
          "name": "陈宁（演示）",
          "phone": "13800000002",
          "role": "员工",
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
              "管理员",
              "员工"
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
      "notice": "先在此开通员工并绑定门诊，再由员工进入独立门诊端小程序授权同一手机号完成绑定。不会变更其客户身份。"
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

// 仅下发门诊所需的可用方案，不包含任何合作方分配费率。
window.PROTOTYPE.schemeCatalog=[{name:'舒适洁牙权益',fee:60,status:'已启用'},{name:'种植牙抵用权益',fee:180,status:'草稿'}];
window.PROTOTYPE.authorizations=[{scheme:'舒适洁牙权益',status:'已启用',contractStatus:'已生效',start:'2026-01-01',end:'2026-12-31'}];
(() => {
  const offers=window.PROTOTYPE.pages.find(p=>p.id==='offers');
  offers.columns.splice(3,0,['authorization','渠道合同授权']);
  offers.rows[0].authorization='所属启明渠道已授权';offers.rows[1].authorization='所属渠道未授权 / 方案未启用';
  offers.notice='仅可上线所属渠道有效合同已授权方案，同时满足本门诊合同、信用及营业条件。无权修改方案或合作方分配。历史预约不受授权停用影响。';
})();
