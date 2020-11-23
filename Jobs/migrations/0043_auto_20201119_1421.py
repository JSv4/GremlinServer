# Generated by Django 3.1.1 on 2020-11-19 19:21

import Jobs.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Jobs', '0042_auto_20201116_1224'),
    ]

    operations = [
        migrations.AddField(
            model_name='result',
            name='job_inputs',
            field=models.JSONField(default=Jobs.models.blank_json),
        ),
        migrations.AddField(
            model_name='result',
            name='job_state',
            field=models.JSONField(default=Jobs.models.blank_state),
        ),
        migrations.AddField(
            model_name='result',
            name='node_inputs',
            field=models.JSONField(default=Jobs.models.blank_json),
        ),
        migrations.AddField(
            model_name='result',
            name='node_output_data',
            field=models.JSONField(default=Jobs.models.blank_json),
        ),
    ]