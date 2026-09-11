from django.db import migrations


def publish_coordinates(apps, schema_editor):
    clinic_model = apps.get_model("chihuitong", "Clinic")
    queryset = clinic_model.objects.using(schema_editor.connection.alias)
    for clinic in queryset.filter(profile_version__gt=0).iterator(chunk_size=500):
        # profile is the approved snapshot, never the pending change document.
        location = clinic.profile.get("location", {})
        if location.get("status") == "confirmed":
            queryset.filter(pk=clinic.pk).update(
                longitude=location["longitude"], latitude=location["latitude"]
            )


class Migration(migrations.Migration):
    dependencies = [("chihuitong", "0015_clinic_latitude_clinic_longitude_and_more")]
    operations = [migrations.RunPython(publish_coordinates, migrations.RunPython.noop)]
