"""Generate only synthetic upload fixtures inside the current server test report."""

import socket
import sys
from pathlib import Path

from openpyxl import Workbook
from PIL import Image, ImageDraw
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


if socket.gethostname() != 'VM-0-12-ubuntu':
    raise SystemExit('Server-only synthetic test fixtures')
directory = Path(sys.argv[1]).resolve()
root = Path('/home/ubuntu/ChiHuiTong/test-results')
if directory.parent != root or not directory.is_dir():
    raise SystemExit('Expected one existing isolated test report directory')
book = Workbook()
sheet = book.active
sheet.title = '合成客户'
sheet.append(['客户姓名', '手机号', '客户手机号', '开卡数量', '客户编号', '性别', '年龄', '职业'])
sheet.append(['合成批量一', '13800000801', '000', 2, 'EXTERNAL-801', '女', 29, '合成职业'])
sheet.append(['合成批量二', '+86 13800000802', '000', 3, 'EXTERNAL-802', '男', 31, '合成职业'])
book.save(directory/'synthetic-customers.xlsx')
image = Image.new('RGB', (640, 360), 'white')
ImageDraw.Draw(image).text((30, 100), 'SYNTHETIC TEST ONLY - NOT A REAL PAYMENT / LICENSE', fill='black')
image.save(directory/'synthetic-proof.png')
pdf = PdfWriter()
page = pdf.add_blank_page(width=400, height=300)
font = DictionaryObject({NameObject('/Type'):NameObject('/Font'), NameObject('/Subtype'):NameObject('/Type1'), NameObject('/BaseFont'):NameObject('/Helvetica')})
page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):pdf._add_object(font)})})
stream = DecodedStreamObject()
stream.set_data(b'BT /F1 18 Tf 30 230 Td (SYNTHETIC TEST ONLY) Tj ET')
page[NameObject('/Contents')] = pdf._add_object(stream)
pdf.write(directory/'synthetic-static.pdf')
