window.PROTOTYPE = {
  "role": "platform",
  "title": "平台管理后台",
  "org": "齿慧通运营平台",
  "scope": "全平台 · 受控业务范围",
  "user": "平台管理员",
  "greeting": "今日工作台",
  "description": "集中处理审核、收款与履约事项",
  "alertTitle": "有待处理的门诊逾期账单",
  "alert": "青禾口腔账单逾期，请核对到账及催收情况；上下线由平台人工操作。",
  "cards": [
    {
      "title": "待审核门诊",
      "page": "clinics",
      "status": [
        "待审核"
      ],
      "foot": "查看审核队列",
      "note": "完整资料提交后2个工作日内审核"
    },
    {
      "title": "待审核投放",
      "page": "imports",
      "status": [
        "待审核"
      ],
      "foot": "审核导入批次",
      "note": "核对来源展示名及领取后有效期"
    },
    {
      "title": "待处理开卡",
      "page": "orders",
      "status": [
        "待审核",
        "待收款",
        "取消待审核"
      ],
      "foot": "处理开卡订单",
      "note": "本单定价、线下收款及取消审核"
    },
    {
      "title": "待确认账单",
      "page": "bills",
      "status": [
        "待付款",
        "已逾期"
      ],
      "foot": "核对门诊账单",
      "note": "全额到账后整体冲销"
    }
  ],
  "sideTitle": "运营提醒",
  "side": [
    [
      "合同到期提醒",
      "明禾口腔合同将于2026-09-30到期"
    ],
    [
      "短信责任",
      "付款期内每日提醒，逾期首日提醒一次"
    ],
    [
      "异常履约",
      "保留反馈事实，暂停自动释放权益"
    ]
  ],
  "pages": [
    {
      "id": "institutions",
      "prefix": "JG",
      "title": "机构管理",
      "description": "管理保险、银行、经纪代理及渠道机构",
      "columns": [
        [
          "name",
          "机构名称"
        ],
        [
          "type",
          "机构类型"
        ],
        [
          "contact",
          "联系人"
        ],
        [
          "status",
          "状态"
        ]
      ],
      "rows": [
        {
          "id": "JG-001",
          "name": "安和经纪（演示）",
          "type": "经纪代理公司",
          "contact": "林晓",
          "status": "正常"
        },
        {
          "id": "JG-002",
          "name": "星海银行（演示）",
          "type": "银行",
          "contact": "顾言",
          "status": "正常"
        },
        {
          "id": "JG-003",
          "name": "启明渠道（演示）",
          "type": "门诊渠道公司",
          "contact": "陈宁",
          "status": "正常"
        }
      ],
      "create": {
        "label": "新增机构",
        "create": true,
        "fields": [
          {
            "key": "name",
            "label": "机构名称",
            "type": "text"
          },
          {
            "key": "type",
            "label": "机构类型",
            "type": "text",
            "options": [
              "保险公司",
              "银行",
              "经纪代理公司",
              "门诊渠道公司"
            ]
          },
          {
            "key": "contact",
            "label": "联系人",
            "type": "text"
          },
          {
            "key": "phone",
            "label": "联系手机号",
            "type": "text"
          }
        ]
      },
      "actions": [
        {
          "label": "审核通过",
          "when": [
            "待审核"
          ],
          "next": "审核通过",
          "fields": [
            {
              "key": "reason",
              "label": "处理原因",
              "type": "textarea"
            }
          ]
        },
        {
          "label": "退回修改",
          "when": [
            "待审核"
          ],
          "next": "审核不通过",
          "danger": true,
          "fields": [
            {
              "key": "reason",
              "label": "处理原因",
              "type": "textarea"
            }
          ]
        }
      ]
    },
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
      "actions": [
        {
          "label": "审核通过",
          "when": [
            "待审核"
          ],
          "next": "审核通过",
          "fields": [
            {
              "key": "reason",
              "label": "处理原因",
              "type": "textarea"
            }
          ]
        },
        {
          "label": "退回修改",
          "when": [
            "待审核"
          ],
          "next": "审核不通过",
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
          "label": "冻结业务",
          "when": [
            "正常"
          ],
          "next": "已冻结",
          "danger": true,
          "fields": [
            {
              "key": "reason",
              "label": "处理原因",
              "type": "textarea"
            }
          ],
          "hint": "冻结后暂停新预约。已有预约继续履约，历史记录保留。"
        },
        {
          "label": "解除冻结",
          "when": [
            "已冻结"
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
        "label": "登记合同",
        "create": true,
        "guard": "contract",
        "fields": [
          {
            "key": "name",
            "label": "合同名称",
            "type": "text"
          },
          {
            "key": "type",
            "label": "合同类型",
            "type": "text",
            "options": [
              "平台—资源方",
              "平台—渠道公司",
              "渠道公司—门诊",
              "平台—门诊"
            ]
          },
          {
            "key": "party",
            "label": "签约主体",
            "type": "text",
            "options": [
              "安和经纪（演示）",
              "启明渠道（演示）",
              "明禾口腔（演示）"
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
        ]
      },
      "actions": [
        {
          "label": "审核生效",
          "when": [
            "待审核"
          ],
          "next": "已生效",
          "fields": [
            {
              "key": "reason",
              "label": "处理原因",
              "type": "textarea"
            }
          ]
        }
      ]
    },
    {
      "id": "schemes",
      "prefix": "FA",
      "title": "推广产品",
      "description": "统一配置权益、单次核销数量与获客费；授权和分配在合作方合同中维护",
      "columns": [
        [
          "name",
          "内部展示名称"
        ],
        [
          "quantity",
          "单次份数"
        ],
        [
          "fee",
          "获客费（元）"
        ],
        [
          "days",
          "有效期（天）"
        ],
        [
          "status",
          "状态"
        ]
      ],
      "rows": [
        {
          "id": "FA-001",
          "name": "舒适洁牙权益",
          "quantity": 1,
          "fee": 60,
          "days": 180,
          "status": "已启用"
        },
        {
          "id": "FA-002",
          "name": "种植牙抵用权益",
          "quantity": 1,
          "fee": 180,
          "days": 180,
          "status": "草稿"
        },
        {
          "id": "FA-003",
          "name": "正畸抵用权益",
          "quantity": 1,
          "fee": 150,
          "days": 180,
          "status": "草稿"
        }
      ],
      "create": {
        "label": "创建推广产品",
        "create": true,
        "next": "草稿",
        "defaults": {
          "quantity": 1,
          "days": 180
        },
        "fields": [
          {
            "key": "name",
            "label": "内部展示名称",
            "type": "text"
          },
          {
            "key": "type",
            "label": "权益类型",
            "type": "text",
            "options": [
              "洁牙券",
              "种植牙抵用券",
              "正畸抵用券"
            ]
          },
          {
            "key": "quantity",
            "label": "单次核销份数",
            "type": "number",
            "min": 1,
            "integer": true
          },
          {
            "key": "fee",
            "label": "单次获客费（元）",
            "type": "number"
          },
          {
            "key": "days",
            "label": "默认有效期（天）",
            "type": "number",
            "min": 1,
            "integer": true
          },
          {
            "key": "terms",
            "label": "使用条件",
            "type": "textarea"
          }
        ]
      },
      "actions": [
        {
          "label": "启用推广产品",
          "when": [
            "草稿",
            "已停用"
          ],
          "next": "已启用",
          "fields": [
            {
              "key": "reason",
              "label": "处理原因",
              "type": "textarea"
            }
          ]
        },
        {
          "label": "停用推广产品",
          "when": [
            "已启用"
          ],
          "next": "已停用",
          "danger": true,
          "fields": [
            {
              "key": "reason",
              "label": "处理原因",
              "type": "textarea"
            }
          ],
          "hint": "停用影响新增投放；已有权益及确认预约仍按历史规则履约。"
        },
        {
          "label": "编辑规则",
          "fields": [
            {
              "key": "name",
              "label": "内部展示名称",
              "type": "text"
            },
            {
              "key": "type",
              "label": "权益类型",
              "type": "text",
              "options": [
                "洁牙券",
                "种植牙抵用券",
                "正畸抵用券"
              ]
            },
            {
              "key": "quantity",
              "label": "单次核销份数",
              "type": "number",
              "min": 1,
              "integer": true
            },
            {
              "key": "fee",
              "label": "单次获客费（元）",
              "type": "number"
            },
            {
              "key": "days",
              "label": "默认有效期（天）",
              "type": "number",
              "min": 1,
              "integer": true
            },
            {
              "key": "terms",
              "label": "使用条件",
              "type": "textarea"
            }
          ]
        }
      ]
    },
    {
      "id": "sources",
      "prefix": "LY",
      "title": "来源展示名",
      "description": "分别配置每个资源方可选择的客户侧品牌名称",
      "columns": [
        [
          "name",
          "展示名称"
        ],
        [
          "owner",
          "所属资源方"
        ],
        [
          "status",
          "状态"
        ]
      ],
      "rows": [
        {
          "id": "LY-001",
          "name": "安和保险客户福利",
          "owner": "安和经纪（演示）",
          "status": "已启用"
        },
        {
          "id": "LY-002",
          "name": "星海银行信用卡礼遇",
          "owner": "星海银行（演示）",
          "status": "已启用"
        }
      ],
      "create": {
        "label": "新增展示名",
        "create": true,
        "next": "已启用",
        "fields": [
          {
            "key": "name",
            "label": "客户侧展示名称",
            "type": "text"
          },
          {
            "key": "owner",
            "label": "所属资源方",
            "type": "text",
            "options": [
              "安和经纪（演示）",
              "星海银行（演示）"
            ]
          }
        ]
      },
      "actions": [
        {
          "label": "停用",
          "when": [
            "已启用"
          ],
          "next": "已停用",
          "fields": [
            {
              "key": "reason",
              "label": "处理原因",
              "type": "textarea"
            }
          ]
        }
      ],
      "notice": "同一展示名按资源方单独授权，资源方无法查看其他机构的可选列表。"
    },
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
      "actions": [
        {
          "label": "审核入账",
          "when": [
            "待审核"
          ],
          "next": "已入账",
          "defaults": {
            "days": 180
          },
          "fields": [
            {
              "key": "days",
              "label": "领取后有效期（天）",
              "type": "number",
              "min": 1,
              "integer": true
            },
            {
              "key": "reason",
              "label": "处理原因",
              "type": "textarea"
            }
          ],
          "hint": "审核通过后匹配客户并创建待领取权益；手机号与姓名不一致的明细不入账。"
        },
        {
          "label": "退回修改",
          "when": [
            "待审核"
          ],
          "next": "审核不通过",
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
          "label": "停止剩余权益",
          "when": [
            "已入账"
          ],
          "next": "已停止",
          "stop": true,
          "danger": true,
          "fields": [
            {
              "key": "reason",
              "label": "处理原因",
              "type": "textarea"
            }
          ],
          "hint": "只停止尚未领取部分，已领取权益不受影响。"
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
        },
        {
          "id": "KC-0830-004",
          "name": "待取消开卡订单",
          "scheme": "舒适洁牙权益",
          "quantity": 20,
          "price": 20,
          "amount": 400,
          "activated": 0,
          "status": "取消待审核",
          "source": "安和保险客户福利",
          "days": 180
        }
      ],
      "notice": "卡片没有激活截止日期，激活后默认有效180天。单价由平台审核时确定。",
      "export": true,
      "actions": [
        {
          "label": "审核定价",
          "when": [
            "待审核"
          ],
          "next": "待收款",
          "computePrice": true,
          "defaults": {
            "days": 180
          },
          "fields": [
            {
              "key": "price",
              "label": "本单卡单价（元）",
              "type": "number",
              "min": 0.01
            },
            {
              "key": "days",
              "label": "激活后有效期（天）",
              "type": "number",
              "min": 1,
              "integer": true
            }
          ],
          "hint": "单价乘以申请数量为本单应付金额。确认收款后才可开卡。"
        },
        {
          "label": "确认收款",
          "when": [
            "待收款"
          ],
          "next": "已收款待开卡",
          "guard": "paid",
          "fields": [
            {
              "key": "amount",
              "label": "实际到账金额（元）",
              "type": "number"
            },
            {
              "key": "voucher",
              "label": "收款凭证",
              "type": "file"
            },
            {
              "key": "confirmed",
              "label": "已核对线下全额到账",
              "type": "checkbox"
            }
          ]
        },
        {
          "label": "完成开卡",
          "when": [
            "已收款待开卡"
          ],
          "next": "制作中",
          "fields": [
            {
              "key": "confirmed",
              "label": "确认按订单数量生成卡片",
              "type": "checkbox"
            }
          ],
          "hint": "生成固定数量卡片并进入实体卡制作。"
        },
        {
          "label": "登记寄送",
          "when": [
            "制作中"
          ],
          "next": "已寄送",
          "fields": [
            {
              "key": "courier",
              "label": "物流公司",
              "type": "text"
            },
            {
              "key": "tracking",
              "label": "物流单号",
              "type": "text"
            },
            {
              "key": "address",
              "label": "收件地址",
              "type": "text"
            }
          ]
        },
        {
          "label": "批准取消",
          "when": [
            "取消待审核"
          ],
          "next": "待线下退款",
          "guard": "unactivated",
          "danger": true,
          "fields": [
            {
              "key": "reason",
              "label": "处理原因",
              "type": "textarea"
            }
          ],
          "hint": "检查所有卡片未激活后作废整批卡片，退款在线下完成。"
        },
        {
          "label": "登记退款",
          "when": [
            "待线下退款"
          ],
          "next": "已取消",
          "fields": [
            {
              "key": "refund",
              "label": "退款金额（元）",
              "type": "number"
            },
            {
              "key": "refundDate",
              "label": "退款日期",
              "type": "date"
            },
            {
              "key": "voucher",
              "label": "退款凭证",
              "type": "file"
            }
          ]
        }
      ]
    },
    {
      "id": "appointments",
      "prefix": "YY",
      "title": "履约查询",
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
      "notice": "平台查看履约事实；门诊负责预约确认和核销。冲突裁决暂未纳入。"
    },
    {
      "id": "credit",
      "prefix": "ED",
      "title": "额度申请",
      "description": "审核渠道业务员的调额或冻结申请",
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
          "rep",
          "申请人"
        ],
        [
          "reason",
          "申请原因"
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
          "rep": "陈宁（演示）",
          "reason": "已补充合同变更版本",
          "status": "待审核"
        },
        {
          "id": "ED-002",
          "name": "映禾口腔（演示）",
          "type": "冻结业务",
          "credit": 5000,
          "rep": "林晓（演示）",
          "reason": "临时暂停合作",
          "status": "待审核"
        }
      ],
      "actions": [
        {
          "label": "审核通过",
          "when": [
            "待审核"
          ],
          "next": "审核通过",
          "fields": [
            {
              "key": "reason",
              "label": "处理原因",
              "type": "textarea"
            }
          ]
        },
        {
          "label": "退回修改",
          "when": [
            "待审核"
          ],
          "next": "审核不通过",
          "danger": true,
          "fields": [
            {
              "key": "reason",
              "label": "处理原因",
              "type": "textarea"
            }
          ]
        }
      ]
    },
    {
      "id": "bills",
      "prefix": "ZD",
      "title": "门诊账单",
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
          "label": "确认全额到账",
          "when": [
            "待付款",
            "付款待确认",
            "已逾期"
          ],
          "next": "已结清",
          "guard": "receipt",
          "fields": [
            {
              "key": "amount",
              "label": "确认到账金额（元）",
              "type": "number"
            },
            {
              "key": "voucher",
              "label": "到账凭证",
              "type": "file"
            },
            {
              "key": "confirmed",
              "label": "已核对整张账单全额到账",
              "type": "checkbox"
            }
          ],
          "hint": "全额到账才整体冲销账单。确认后解除本账单造成的逾期限制。"
        }
      ]
    },
    {
      "id": "earnings",
      "prefix": "DZ",
      "title": "平台收益对账",
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
      "id": "sms",
      "prefix": "SMS",
      "title": "短信模板",
      "description": "维护平台预配置的通知模板及报备信息",
      "columns": [
        [
          "name",
          "通知场景"
        ],
        [
          "template",
          "服务商模板编号"
        ],
        [
          "receiver",
          "接收人"
        ],
        [
          "status",
          "状态"
        ]
      ],
      "rows": [
        {
          "id": "SMS-001",
          "name": "新预约通知",
          "template": "DEMO_APPOINTMENT",
          "receiver": "门诊预约联系手机号",
          "status": "已启用",
          "content": "有新的预约待确认，请登录门诊后台处理。"
        },
        {
          "id": "SMS-002",
          "name": "付款提醒",
          "template": "DEMO_BILL",
          "receiver": "门诊联系人、渠道业务员",
          "status": "已启用",
          "content": "账单待付款，请于约定截止日前完成付款。"
        }
      ],
      "actions": [
        {
          "label": "修改模板",
          "fields": [
            {
              "key": "template",
              "label": "服务商模板编号",
              "type": "text"
            },
            {
              "key": "content",
              "label": "模板内容",
              "type": "textarea"
            }
          ]
        }
      ],
      "notice": "短信费用、失败重试及服务商模板报备由平台负责。"
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
