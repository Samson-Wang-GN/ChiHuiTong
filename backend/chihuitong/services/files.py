import hashlib
import io
import re
import secrets
import warnings
import zipfile
from pathlib import Path

from django.conf import settings
from django.db import transaction
from cryptography.fernet import InvalidToken
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject

from chihuitong.crypto import cipher
from chihuitong.errors import BusinessError, require
from chihuitong.models import AttachmentLink, FileAsset

from .common import audit

MAX_FILE = 10 * 1024 * 1024
PURPOSES = {"cover", "license", "contract", "payment", "sales_excel"}


def checked_xlsx(data):
    require(data.startswith(b"PK"), "invalid_excel", "请上传有效的xlsx文件", 400)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            require(len(infos) <= 1000 and sum(i.file_size for i in infos) <= 50 * 1024 * 1024, "excel_limit", "Excel展开量超限，请拆分文件", 400)
            require("[Content_Types].xml" in archive.namelist() and "xl/workbook.xml" in archive.namelist(), "invalid_excel", "文件不是标准xlsx工作簿", 400)
            for info in infos:
                name = info.filename.lower()
                require(not info.flag_bits & 1 and not name.startswith("/") and ".." not in Path(name).parts, "invalid_excel", "不支持加密或异常路径工作簿", 400)
                require("vbaproject" not in name and "externallinks" not in name and "embeddings" not in name, "unsafe_excel", "Excel包含宏、外部链接或嵌入对象，请移除后上传", 400)
                content = archive.read(info)
                if name.endswith((".xml", ".rels")):
                    lower = content.lower()
                    require(b"<!doctype" not in lower and b"<!entity" not in lower, "unsafe_excel", "Excel包含不允许的XML实体", 400)
                    require(not re.search(rb'targetmode\s*=\s*[\x22\x27]external', lower), "unsafe_excel", "Excel包含外部关系，请移除后上传", 400)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise BusinessError("invalid_excel", "Excel损坏或压缩格式不受支持", 400) from exc
    return data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def validate_pdf(data):
    require(data.startswith(b"%PDF-"), "invalid_pdf", "PDF文件内容不合法", 400)
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        require(not reader.is_encrypted, "encrypted_pdf", "请上传未加密的PDF", 400)
        require(0 < len(reader.pages) <= 200, "pdf_limit", "PDF页数超限，请分文件上传", 400)
        seen, stack = set(), [reader.trailer]
        count = 0
        blocked = {"/JS", "/JavaScript", "/OpenAction", "/AA", "/Launch", "/EmbeddedFiles", "/RichMedia", "/XFA", "/URI", "/SubmitForm", "/ImportData"}
        while stack:
            item = stack.pop()
            count += 1
            require(count <= 50000, "pdf_limit", "PDF结构过于复杂，请重新导出", 400)
            if isinstance(item, IndirectObject):
                marker = (item.idnum, item.generation)
                if marker in seen:
                    continue
                seen.add(marker)
                item = item.get_object()
            if isinstance(item, DictionaryObject):
                require(not blocked.intersection(item.keys()), "unsafe_pdf", "PDF包含脚本、外链或交互附件，请导出静态PDF", 400)
                require(str(item.get("/S", "")) not in blocked, "unsafe_pdf", "PDF包含不允许的动作", 400)
                stack.extend(item.values())
            elif isinstance(item, ArrayObject):
                stack.extend(item)
    except (PdfReadError, ValueError, TypeError, RecursionError) as exc:
        raise BusinessError("invalid_pdf", "PDF损坏或无法安全解析，请重新导出", 400) from exc
    return data, "application/pdf"


def validate_file(data, filename, purpose):
    require(purpose in PURPOSES, "invalid_purpose", "附件用途不合法", 400)
    require(isinstance(data, bytes) and 0 < len(data) <= MAX_FILE, "file_limit", "附件为空或超过10MB，请分文件上传", 400)
    suffix = Path(filename).suffix.lower()
    if purpose == "sales_excel":
        require(suffix == ".xlsx", "invalid_type", "客户名单仅支持xlsx", 400)
        return checked_xlsx(data)
    if suffix == ".pdf" and purpose != "cover":
        return validate_pdf(data)
    require(suffix in {".jpg", ".jpeg", ".png"}, "invalid_type", "请上传PNG/JPG图片或静态PDF", 400)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                require(image.format in {"PNG", "JPEG"}, "invalid_image", "图片格式不合法", 400)
                require(image.width * image.height <= 20000000, "image_limit", "图片像素过大，请压缩后上传", 400)
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                converted = image.convert("RGB")
                output = io.BytesIO()
                converted.save(output, format="JPEG", quality=90)
                # Re-encoding strips EXIF, comments, trailing polyglot content and GPS metadata.
                return output.getvalue(), "image/jpeg"
    except (UnidentifiedImageError, OSError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise BusinessError("invalid_image", "图片无法安全读取，请重新上传", 400) from exc


@transaction.atomic
def upload_file(actor, *, data, filename, purpose):
    if actor.organization.kind == "clinic":
        actor.require_admin()
    safe_data, content_type = validate_file(data, filename, purpose)
    root = settings.PRIVATE_STORAGE
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    key = secrets.token_hex(24) + ".enc"
    path = root / key
    with path.open("xb") as output:
        output.write(cipher().encrypt(safe_data))
    path.chmod(0o600)
    # If the DB transaction fails, an unreachable encrypted blob is retained for audited cleanup.
    asset = FileAsset.objects.create(
        organization=actor.organization, uploaded_by=actor.account, original_name=Path(filename).name[:200],
        storage_key=key, content_type=content_type, size=len(safe_data),
        sha256=hashlib.sha256(safe_data).hexdigest(), purpose=purpose,
    )
    audit(actor, asset, "file.uploaded", purpose=purpose, size=asset.size)
    return asset


def can_read_file(actor, asset):
    if actor.platform:
        return True
    if actor.organization.kind == "clinic" and actor.membership.role != "admin":
        return False
    if asset.organization_id == actor.organization.id and (actor.membership.role == "admin" or asset.uploaded_by_id == actor.account.id):
        return True
    from .clinics import visible_clinics
    from .contracts import accessible_contracts
    contract_ids = accessible_contracts(actor).values_list("id", flat=True)
    clinic_ids = visible_clinics(actor).values_list("id", flat=True)
    return asset.links.filter(object_type="contract", object_id__in=contract_ids).exists() or asset.links.filter(object_type="clinic", object_id__in=clinic_ids).exists()


def file_bytes(asset):
    path = (settings.PRIVATE_STORAGE / asset.storage_key).resolve()
    require(path.parent == settings.PRIVATE_STORAGE and path.is_file(), "file_unavailable", "附件缺失，请重新上传或联系平台", 409)
    try:
        raw = cipher().decrypt(path.read_bytes())
    except (OSError, ValueError, InvalidToken) as exc:
        raise BusinessError("file_unavailable", "附件读取失败，请联系平台", 409) from exc
    require(hashlib.sha256(raw).hexdigest() == asset.sha256, "file_integrity", "附件校验失败，请联系平台", 409)
    return raw


def validate_attachment_ids(actor, ids, *, purposes):
    import uuid
    require(isinstance(ids, list) and 0 < len(ids) <= 20 and all(isinstance(value, str) for value in ids) and len(set(ids)) == len(ids), "invalid_attachments", "请提供1～20个不重复附件", 400)
    try:
        parsed = [uuid.UUID(str(value)) for value in ids]
    except (ValueError, TypeError) as exc:
        raise BusinessError("invalid_attachments", "附件编号不合法", 400) from exc
    assets = list(FileAsset.objects.filter(id__in=parsed, status="ready", purpose__in=purposes))
    require(len(assets) == len(ids), "invalid_attachments", "附件不存在、用途不符或不可用", 400)
    for asset in assets:
        require(can_read_file(actor, asset), "forbidden", "无权使用该附件", 403)
        file_bytes(asset)
    return assets


def link_files(ids, obj):
    for asset_id in ids:
        AttachmentLink.objects.get_or_create(asset_id=asset_id, object_type=obj._meta.model_name, object_id=obj.id)


def download_file(actor, asset_id):
    asset = FileAsset.objects.filter(pk=asset_id, status="ready").first()
    require(asset and can_read_file(actor, asset), "not_found", "附件不存在或无权访问", 404)
    data = file_bytes(asset)
    audit(actor, asset, "file.downloaded", purpose=asset.purpose)
    return asset, data
