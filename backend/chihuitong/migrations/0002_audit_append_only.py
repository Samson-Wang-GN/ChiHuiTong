from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("chihuitong", "0001_initial")]
    operations = [
        migrations.RunSQL(
            """
            CREATE FUNCTION cht_reject_audit_mutation() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'audit events are append-only';
            END;
            $$ LANGUAGE plpgsql;
            CREATE TRIGGER cht_audit_append_only BEFORE UPDATE OR DELETE
            ON chihuitong_auditevent FOR EACH ROW EXECUTE FUNCTION cht_reject_audit_mutation();
            """,
            """
            DROP TRIGGER cht_audit_append_only ON chihuitong_auditevent;
            DROP FUNCTION cht_reject_audit_mutation();
            """,
        ),
    ]
