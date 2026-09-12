"""Server-only synthetic patient events; never runs against persistent acceptance data."""

import json
import os
from pathlib import Path
import re
import socket
import sys
from datetime import timedelta

if socket.gethostname() != 'VM-0-12-ubuntu':
    raise SystemExit('Server-only fixture')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.conf import settings
from django.utils import timezone
from chihuitong.integrations.simulated import require_simulation
from chihuitong.models import Appointment, Card, Clinic
from chihuitong.services import appointments, customers

require_simulation()
if not re.fullmatch(r'chihuitong_acceptance_web_[0-9a-f]{12}', settings.DATABASES['default']['NAME']):
    raise SystemExit('Only disposable Web regression database')
if len(sys.argv) > 1 and sys.argv[1] in {'supplement', 'overdue'}:
    query = Appointment.objects.select_related('benefit__card').filter(reserved=True, scheduled_at__lt=timezone.now())
    query = query.filter(status='completed', completion_source='system') if sys.argv[1] == 'supplement' else query.filter(status='success')
    appointment = query.order_by('scheduled_at').first()
    if not appointment:
        raise SystemExit('Expected synthetic expired appointment')
    print(json.dumps({'appointment_id':str(appointment.id), 'credential':appointment.benefit.card.credential}))
    raise SystemExit(0)
customer = customers.register_verified_customer('13900001007')
card = Card.objects.filter(customer=customer, status='unclaimed', frozen=False).order_by('serial').first()
if not card:
    raise SystemExit('No remaining synthetic event card')
benefit = customers.claim(customer.id, card.id)
clinic = Clinic.objects.get(organization__name='演示口腔门诊')
appointment = appointments.book(customer.id, benefit_id=benefit.id, clinic_id=clinic.id, requested_at=timezone.now()+timedelta(hours=6))
# Consumed only by the isolated browser test process; never print to the tool transcript/report.
print(json.dumps({'appointment_id':str(appointment.id), 'credential':card.credential}))
