# Generated by Django 3.0.5 on 2020-08-15 22:53

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Jobs', '0026_auto_20200809_1507'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pipelinenode',
            name='script',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='Jobs.PythonScript'),
        ),
    ]
