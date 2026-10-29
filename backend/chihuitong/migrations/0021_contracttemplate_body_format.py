from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("chihuitong", "0020_contractpreparation_contracttemplate_contractprint")]

    operations = [
        migrations.AddField(
            model_name="contracttemplate",
            name="body_format",
            field=models.CharField(default="plain", max_length=16),
        ),
    ]
