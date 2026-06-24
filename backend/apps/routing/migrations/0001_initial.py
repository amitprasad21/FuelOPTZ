import os
from django.db import migrations

def load_sql(filename):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))
    sql_path = os.path.join(project_root, 'sql', filename)
    with open(sql_path, 'r', encoding='utf-8') as f:
        return f.read()

class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('fuel', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(load_sql('002_create_route_cache.sql')),
        migrations.RunSQL(load_sql('003_add_indexes.sql')),
    ]
