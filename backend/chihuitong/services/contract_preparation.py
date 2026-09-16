"""Private resumable preparation and immutable printable bilateral contract versions."""

import hashlib
import io
import json
import re
import uuid
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from django.db import transaction
from django.utils import timezone

from chihuitong.errors import require
from chihuitong.models import ContractPreparation, ContractPrint, ContractTemplate, FileAsset, Product

from . import cooperations, files
from .common import advance, advisory_lock, audit, check_version

FIELDS = {
    "number",
    "platform_name",
    "platform_credit_code",
    "subject_name",
    "subject_credit_code",
    "starts_at",
    "ends_at",
    "payment_mode",
    "settlement_cycle",
    "products",
    "stores",
    "contact_name",
    "contact_phone",
}
PATTERN = re.compile(r"\{\{([a-z_]+)\}\}")


def visible(actor):
    require(
        actor.platform or actor.organization.kind == "channel",
        "forbidden",
        "仅平台和门诊渠道可办理待签合同",
        403,
    )
    qs = ContractPreparation.objects.select_related("owner__organization")
    if actor.platform:
        return qs
    qs = qs.filter(owner__organization=actor.organization)
    return qs if actor.membership.role == "admin" else qs.filter(owner=actor.membership)


def get(actor, pk, lock=False):
    qs = visible(actor)
    if lock:
        qs = qs.select_for_update(of=("self",))
    item = qs.filter(pk=pk).first()
    require(item, "not_found", "草稿不存在或无权访问", 404)
    return item


def editable(item, version):
    check_version(item, version)
    require(item.status == "draft", "invalid_state", "已提交草稿不可修改，请在合同详情处理后续修订")


@transaction.atomic
def template(actor, *, kind, title, body, platform_name, platform_credit_code, confirmed):
    actor.require_platform()
    require(
        confirmed is True, "confirmation_required", "请确认范本已获平台认可，可用于实际签署", 400
    )
    fields = set(PATTERN.findall(body))
    require(
        fields <= FIELDS and {"subject_name", "number", "platform_name"} <= fields,
        "invalid_template",
        "模板必须含合同编号、平台名称及门诊主体占位符，且不能含未知占位符",
        400,
    )
    require(
        "{{" not in PATTERN.sub("", body) and "}}" not in PATTERN.sub("", body),
        "invalid_template",
        "模板占位符格式应为{{字段名}}",
        400,
    )
    advisory_lock("contract_template", kind)
    ContractTemplate.objects.filter(kind=kind, status="active").update(status="retired")
    item = ContractTemplate.objects.create(
        kind=kind,
        title=title,
        body=body,
        platform_name=platform_name,
        platform_credit_code=platform_credit_code,
        created_by=actor.membership,
    )
    audit(actor, item, "contract_template.published")
    return item


def payload_files(payload):
    profile = payload.get("clinic", {}).get("profile", {})
    require(isinstance(profile, dict), "invalid_payload", "门诊资料必须为对象", 400)
    require(
        all(
            isinstance(profile.get(k, []), list)
            for k in ("business_license_ids", "medical_license_ids")
        ),
        "invalid_payload",
        "资质附件必须为列表",
        400,
    )
    ids = (
        profile.get("business_license_ids", [])
        + profile.get("medical_license_ids", [])
        + ([profile["cover_id"]] if profile.get("cover_id") else [])
    )
    require(all(isinstance(x, str) for x in ids), "invalid_attachments", "附件编号必须为文本", 400)
    return list(dict.fromkeys(ids))


@transaction.atomic
def save(actor, *, kind, payload, pk=None, version=None):
    visible(actor)
    require(
        isinstance(payload, dict) and len(json.dumps(payload)) <= 60000,
        "invalid_payload",
        "草稿内容过大或格式不正确",
        400,
    )
    require(
        set(payload)
        <= {"clinic", "agreement", "subject", "clinic_id", "version", "cooperation_id"},
        "invalid_fields",
        "草稿包含未知字段",
        400,
    )
    for key in ("clinic", "agreement", "subject"):
        require(
            isinstance(payload.get(key, {}), dict), "invalid_payload", "草稿字段格式不正确", 400
        )
    for key in ("clinic_id", "cooperation_id"):
        if key in payload:
            from rest_framework import serializers

            payload[key] = str(serializers.UUIDField().run_validation(payload[key]))
    subject = payload.get("subject", {})
    require(all(isinstance(subject.get(k, ""), str) for k in ("name", "credit_code")),
            "invalid_payload", "主体名称及信用代码必须为文本", 400)
    if not actor.platform:
        from .contracts import current_contract

        current_contract(actor.organization.id)
        channel = payload.get("clinic", {}).get("channel_id")
        require(
            not channel or str(channel) == str(actor.organization.id),
            "forbidden",
            "不能代其他渠道保存草稿",
            403,
        )
    ids = payload_files(payload)
    profile = payload.get("clinic", {}).get("profile", {})
    require(all(isinstance(profile.get(k, ""), str) for k in
                ("name", "legal_entity", "province", "city", "district", "address")),
            "invalid_payload", "门诊名称和地址必须为文本", 400)
    if ids:
        files.validate_attachment_ids(actor, ids, purposes={"cover", "license"})
    payload = json.loads(json.dumps(payload, default=str))
    payload.setdefault("agreement", {})["attachment_ids"] = []
    if pk:
        item = get(actor, pk, lock=True)
        editable(item, version)
        require(item.kind == kind, "invalid_kind", "已存草稿不可变更合作类型", 400)
        # Signatures stay as evidence but never silently attach to a changed contract.
        before = contract_input(item.payload)
        item.payload = payload
        if before != contract_input(payload):
            item.signed_generation = 0
        advance(item, "payload", "signed_generation")
    else:
        item = ContractPreparation.objects.create(
            owner=actor.membership,
            kind=kind,
            number="CHT-" + uuid.uuid4().hex.upper(),
            payload=payload,
        )
    files.link_files(ids, item)
    audit(actor, item, "contract_draft.saved")
    return item


def contract_input(payload):
    agreement = {
        k: v
        for k, v in payload.get("agreement", {}).items()
        if k not in {"attachment_ids", "number"}
    }
    profile = payload.get("clinic", {}).get("profile", {})
    subject = payload.get("subject", {})
    return {
        "agreement": agreement,
        "subject": {k: subject.get(k) for k in ("name", "credit_code")},
        "cooperation_id": payload.get("cooperation_id"),
        "store": {
            k: profile.get(k)
            for k in ("name", "legal_entity", "province", "city", "district", "address")
        },
    }


def snapshot(actor, item, tpl):
    from chihuitong.api_cooperations import AgreementInput

    from .clinics import visible_clinics

    data = {**item.payload.get("agreement", {}), "number": item.number, "attachment_ids": []}
    serializer = AgreementInput(data=data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    require(data["ends_at"] > data["starts_at"], "invalid_dates", "合同到期须晚于生效时间", 400)
    cooperation_id = item.payload.get("cooperation_id")
    if item.payload.get("clinic_id"):
        from .clinics import get_clinic

        clinic = get_clinic(actor, item.payload["clinic_id"], edit=True)
        require(clinic.cooperation_id, "subject_required", "门诊尚未绑定签约主体", 400)
        cooperation_id = clinic.cooperation_id
    if cooperation_id:
        subject = cooperations.get_cooperation(actor, cooperation_id)
        cooperations.assert_edit(actor, subject)
        require(subject.kind == item.kind, "invalid_kind", "主体类型不匹配", 400)
        subject_name, credit = subject.organization.name, subject.credit_code
    else:
        subject = item.payload.get("subject", {})
        subject_name, credit = subject.get("name", ""), subject.get("credit_code", "")
    require(
        subject_name and re.fullmatch(r"[0-9A-HJ-NPQRTUWXY]{18}", credit or ""),
        "subject_required",
        "请填写签约主体全称及18位统一社会信用代码",
        400,
    )
    require(
        data["payment_mode"] == ("instant" if item.kind == "single" else "postpaid"),
        "invalid_mode",
        "合作类型与付款方式不匹配",
        400,
    )
    require(
        data["settlement_cycle"] in ([""] if item.kind == "single" else ["weekly", "monthly"]),
        "invalid_cycle",
        "请核对结算周期",
        400,
    )
    product_ids = set(data["product_ids"])
    products = list(Product.objects.filter(pk__in=product_ids, status="active").order_by("id"))
    require(len(products) == len(product_ids), "invalid_products", "产品已变更，请重新选择", 400)
    from .contracts import current_contract

    if not actor.platform:
        for product in products:
            current_contract(actor.organization.id, product_id=product.id)
    if item.kind == "single" and "clinic" in item.payload:
        p = item.payload.get("clinic", {}).get("profile", {})
        stores = (
            p.get("name", "")
            + " "
            + "".join(p.get(k, "") for k in ("province", "city", "district", "address"))
        )
        require(
            p.get("name") and p.get("address"), "store_required", "请填写门诊名称和经营地址", 400
        )
    else:
        clinics = visible_clinics(actor).filter(pk__in=data["clinic_ids"]).order_by("id")
        require(
            clinics.count() == len(set(data["clinic_ids"])), "forbidden", "包含无权签约的门店", 403
        )
        require(item.kind == "chain" or clinics.exists(), "coverage_required", "请选择覆盖门店", 400)
        stores = "；".join(
            c.organization.name + " " + c.profile.get("address", "") for c in clinics
        ) or "尚未绑定门店（待门店审核后逐步接入）"
    values = {
        "number": item.number,
        "platform_name": tpl.platform_name,
        "platform_credit_code": tpl.platform_credit_code,
        "subject_name": subject_name,
        "subject_credit_code": credit,
        "starts_at": timezone.localtime(data["starts_at"]).strftime("%Y-%m-%d %H:%M"),
        "ends_at": timezone.localtime(data["ends_at"]).strftime("%Y-%m-%d %H:%M"),
        "payment_mode": "核销现付" if item.kind == "single" else "账单后付",
        "settlement_cycle": {"": "不适用", "weekly": "周结", "monthly": "月结"}[
            data["settlement_cycle"]
        ],
        "products": "；".join(
            f"{p.internal_name}（单次获客费{Decimal(p.fee_cents) / 100:.2f}元）" for p in products
        ),
        "stores": stores,
        "contact_name": data["contact"]["name"],
        "contact_phone": data["contact"]["phone"],
    }
    body = PATTERN.sub(lambda match: values[match.group(1)], tpl.body)
    return {
        "values": values,
        "body": body,
        "title": tpl.title,
        "template_id": str(tpl.id),
        "input": contract_input(item.payload),
    }


def fingerprint(data):
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def pdf_bytes(data, revision):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    font = Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc")
    require(font.is_file(), "pdf_font_unavailable", "合同生成字体未配置，请联系平台", 503)
    if "ContractCJK" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("ContractCJK", str(font), subfontIndex=0))
    output = io.BytesIO()
    doc = SimpleDocTemplate(
        output, pagesize=A4, rightMargin=48, leftMargin=48, topMargin=58, bottomMargin=54
    )
    normal = ParagraphStyle(
        "contract", fontName="ContractCJK", fontSize=10.5, leading=19, wordWrap="CJK", spaceAfter=10
    )
    title = ParagraphStyle(
        "title", parent=normal, fontSize=17, leading=25, alignment=1, spaceAfter=20
    )
    story = [Paragraph(escape(data["title"]), title)]
    labels = [("合同编号", "number"), ("平台签约主体", "platform_name"),
              ("平台信用代码", "platform_credit_code"), ("门诊签约主体", "subject_name"),
              ("门诊主体信用代码", "subject_credit_code"), ("生效时间", "starts_at"),
              ("到期时间", "ends_at"), ("付款方式", "payment_mode"), ("结算周期", "settlement_cycle"),
              ("推广产品及费用", "products"), ("覆盖门店", "stores"),
              ("业务联系人", "contact_name"), ("联系电话", "contact_phone")]
    for label, key in labels:
        story.append(Paragraph(escape(f"{label}：{data['values'][key]}"), normal))
    story.append(Spacer(1, 12))
    for line in data["body"].splitlines():
        story.append(Paragraph(escape(line), normal) if line.strip() else Spacer(1, 10))

    def footer(canvas, document):
        canvas.setFont("ContractCJK", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(48, 30, f"{data['values']['number']} / 生成版 {revision} / 待线下签署")
        canvas.drawRightString(A4[0] - 48, 30, f"第 {document.page} 页")

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


@transaction.atomic
def generate(actor, pk, *, version):
    item = get(actor, pk, lock=True)
    editable(item, version)
    tpl = (
        ContractTemplate.objects.filter(kind=item.kind, status="active")
        .order_by("-created_at")
        .first()
    )
    require(
        tpl, "template_missing", "平台尚未配置正式合同模板；草稿已保留，请联系平台配置后再生成", 409
    )
    data = snapshot(actor, item, tpl)
    checksum = fingerprint(data)
    old = item.prints.filter(revision=item.generation).first()
    if old and old.fingerprint == checksum:
        return item
    revision = item.generation + 1
    asset = files.upload_file(
        actor,
        data=pdf_bytes(data, revision),
        filename=f"{item.number}-v{revision}.pdf",
        purpose="contract",
    )
    ContractPrint.objects.create(
        preparation=item,
        template=tpl,
        revision=revision,
        snapshot=data,
        fingerprint=checksum,
        asset=asset,
    )
    files.link_files([str(asset.id)], item)
    item.generation, item.signed_generation = revision, 0
    advance(item, "generation", "signed_generation")
    audit(actor, item, "contract_draft.generated", generation=revision)
    return item


def current_print(actor, item):
    printed = item.prints.select_related("template").filter(revision=item.generation).first()
    require(printed, "print_required", "请先生成并下载待签合同", 409)
    require(
        printed.fingerprint == fingerprint(snapshot(actor, item, printed.template)),
        "print_stale",
        "合同内容或产品费用已变化，请重新生成、打印并签署",
        409,
    )
    return printed


@transaction.atomic
def sign(actor, pk, *, version, generation, attachment_ids):
    item = get(actor, pk, lock=True)
    editable(item, version)
    printed = current_print(actor, item)
    require(generation == printed.revision, "print_stale", "生成版本已变化，请刷新核对签署件", 409)
    require(
        str(printed.asset_id) not in attachment_ids,
        "unsigned_file",
        "不能用未签署的系统生成文件代替签署照片",
        400,
    )
    files.validate_attachment_ids(actor, attachment_ids, purposes={"contract"})
    require(not FileAsset.objects.filter(id__in=attachment_ids, sha256=printed.asset.sha256).exists(),
            "unsigned_file", "上传文件与系统未签署版本相同，请上传签署照片或扫描件", 400)
    item.signed_ids, item.signed_generation = attachment_ids, generation
    files.link_files(attachment_ids, item)
    advance(item, "signed_ids", "signed_generation")
    audit(actor, item, "contract_draft.signed_uploaded", generation=generation, attachment_ids=attachment_ids)
    return item


@transaction.atomic
def submit(actor, pk, *, version):
    item = get(actor, pk, lock=True)
    editable(item, version)
    printed = current_print(actor, item)
    require(
        item.signed_ids and item.signed_generation == printed.revision,
        "signature_required",
        "请先上传当前生成版本对应的门诊签署件",
        409,
    )
    payload = {
        **item.payload,
        "agreement": {
            **item.payload["agreement"],
            "number": item.number,
            "attachment_ids": item.signed_ids,
        },
    }
    if item.kind == "single" and "clinic" in payload:
        from chihuitong.api_cooperations import OnboardingInput

        from .onboarding import submit as submit_onboarding

        serializer = OnboardingInput(data=payload)
        serializer.is_valid(raise_exception=True)
        result = submit_onboarding(actor, **serializer.validated_data)
    else:
        from chihuitong.api_cooperations import StartInput

        serializer = StartInput(
            data={
                "data": payload["agreement"],
                **{k: v for k, v in payload.items() if k in {"subject", "cooperation_id"}},
            }
        )
        serializer.is_valid(raise_exception=True)
        result = cooperations.start_agreement(actor, **serializer.validated_data)
        result = cooperations.submit_agreement(actor, result.id, version=result.version)
    item.agreement, item.status = result, "submitted"
    advance(item, "agreement", "status")
    files.link_files([str(printed.asset_id)], result)
    audit(
        actor,
        item,
        "contract_draft.submitted",
        agreement_id=str(result.id),
        generation=printed.revision,
    )
    return item
