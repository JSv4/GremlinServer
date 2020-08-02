# Generated by Django 3.0.5 on 2020-07-21 05:20

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Jobs', '0014_auto_20200720_2342'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='pipelinestep',
            name='x_coord',
        ),
        migrations.RemoveField(
            model_name='pipelinestep',
            name='y_coord',
        ),
        migrations.AddField(
            model_name='pipelinestep',
            name='position',
            field=django.contrib.postgres.fields.jsonb.JSONField(default={'x': 0, 'y': 0}),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='pipelinestep',
            name='type',
            field=models.CharField(choices=[('THROUGH_SCRIPT', 'Python Script'), ('ROOT_NODE', 'Root node - provides data, doc and setting.'), ('PACKAGING_NODE', 'Packaging node - instructions to package results.'), ('CALLBACK', 'Callback - send data or docs out to external API'), ('API_REQUEST', 'API Request - request data or docs from an external API')], default='THROUGH_SCRIPT', max_length=128),
        ),
        migrations.CreateModel(
            name='Port',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(choices=[('INPUT', 'Input port (data in)'), ('OUTPUT', 'Output port (data out)')], default='OUTPUT', max_length=128)),
                ('name', models.TextField(default='', verbose_name='Port Label')),
                ('node', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ports', to='Jobs.PipelineStep')),
            ],
        ),
        migrations.CreateModel(
            name='Link',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.TextField(default='', verbose_name='Link Label')),
                ('transform_script', models.TextField(blank=True, default='', verbose_name='Data Transform Script')),
                ('input_port', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='input_links', to='Jobs.Port')),
                ('output_port', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='output_links', to='Jobs.Port')),
            ],
        ),
    ]