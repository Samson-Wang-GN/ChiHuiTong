from django.db import migrations, models


def publish_regions(apps, schema_editor):
    clinic_model = apps.get_model("chihuitong", "Clinic")
    queryset = clinic_model.objects.using(schema_editor.connection.alias)
    for clinic in queryset.filter(profile_version__gt=0).iterator(chunk_size=500):
        profile = clinic.profile
        region = "".join(
            profile.get(key) if isinstance(profile.get(key), str) else ""
            for key in ("province", "city", "district")
        )
        queryset.filter(pk=clinic.pk).update(public_region=region)


class Migration(migrations.Migration):
    dependencies = [("chihuitong", "0022_contractfinancialprofile")]
    operations = [
        migrations.AddField(
            model_name="clinic",
            name="public_region",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.RunPython(publish_regions, migrations.RunPython.noop),
    ]
