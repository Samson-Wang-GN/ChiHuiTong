import django.db.models.deletion
from django.db import migrations, models
import chihuitong.crypto
import uuid


class Migration(migrations.Migration):
    dependencies = [("chihuitong", "0021_contracttemplate_body_format")]
    operations = [
        migrations.CreateModel(
            name="ContractFinancialProfile",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("version", models.PositiveIntegerField(default=1)),
                ("details", chihuitong.crypto.EncryptedJSONField(default=dict)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="chihuitong.membership")),
            ],
        ),
    ]
