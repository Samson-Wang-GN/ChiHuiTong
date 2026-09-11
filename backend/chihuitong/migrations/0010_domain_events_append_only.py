from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("chihuitong", "0009_remove_organization_organization_state_and_more")]
    operations = [migrations.RunSQL(
        """
        CREATE TRIGGER cht_domain_event_append_only BEFORE UPDATE OR DELETE
        ON chihuitong_domainevent FOR EACH ROW EXECUTE FUNCTION cht_reject_audit_mutation();
        """,
        "DROP TRIGGER cht_domain_event_append_only ON chihuitong_domainevent;",
    )]
