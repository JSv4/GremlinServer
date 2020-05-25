# Generated by Django 3.0.5 on 2020-05-25 23:10

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Document',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='Contract', max_length=512, verbose_name='Document Name')),
                ('pageCount', models.IntegerField(default=1, verbose_name='Number of Pages')),
                ('type', models.CharField(default='', max_length=5, verbose_name='File Extension')),
                ('file', models.FileField(upload_to='uploads/contracts/', verbose_name='Original File')),
                ('extracted', models.BooleanField(default=False, verbose_name='Extracted Successfully')),
            ],
        ),
        migrations.CreateModel(
            name='Job',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(choices=[('TEST', 'Test'), ('PRODUCTION', 'Production')], default='PRODUCTION', max_length=128)),
                ('name', models.CharField(default='Job Name', max_length=512)),
                ('creation_time', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Job Creation Date and Time')),
                ('queued', models.BooleanField(default=False, verbose_name='Job Queued')),
                ('started', models.BooleanField(default=False, verbose_name='Job Started')),
                ('error', models.BooleanField(default=False, verbose_name='Job in Error Status')),
                ('finished', models.BooleanField(default=False, verbose_name='Job Finished')),
                ('status', models.TextField(default='Not Started', verbose_name='Job Status')),
                ('completed_tasks', models.IntegerField(default=0, verbose_name='Completed Step Tasks')),
                ('job_inputs', models.TextField(blank=True, default='', verbose_name='Input Json')),
                ('file', models.FileField(blank=True, null=True, upload_to='jobs_data/results/', verbose_name='Output File Zip')),
                ('owner', models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Pipeline',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='Line Name', max_length=512)),
                ('description', models.TextField(blank=True, default='')),
                ('total_steps', models.IntegerField(default=0, verbose_name='Step Count')),
                ('schema', models.TextField(blank=True, default='', verbose_name='Job Settings')),
                ('owner', models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='PipelineStep',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='Step Name', max_length=512)),
                ('input_transform', models.TextField(blank=True, default='', verbose_name='Input Transformation')),
                ('step_settings', models.TextField(blank=True, default='', verbose_name='Step Settings')),
                ('step_number', models.IntegerField(default=-1)),
                ('owner', models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('parent_pipeline', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='Jobs.Pipeline')),
            ],
        ),
        migrations.CreateModel(
            name='Result',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='Result', max_length=512, verbose_name='Result Name')),
                ('type', models.CharField(choices=[('DOC', 'Doc Result'), ('STEP', 'Step Result'), ('JOB', 'Job Result')], default='JOB', max_length=128)),
                ('start_time', models.DateTimeField(blank=True, null=True, verbose_name='Step Start Date and Time')),
                ('stop_time', models.DateTimeField(blank=True, null=True, verbose_name='Step Stop Date and Time')),
                ('input_settings', models.TextField(blank=True, default='', verbose_name='Input Settings')),
                ('file', models.FileField(blank=True, null=True, upload_to='results/results/', verbose_name='Results File')),
                ('doc', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='Jobs.Document')),
            ],
        ),
        migrations.CreateModel(
            name='TaskLogEntry',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('logger_name', models.CharField(max_length=100)),
                ('level', models.PositiveSmallIntegerField(choices=[(0, 'NotSet'), (20, 'Info'), (30, 'Warning'), (10, 'Debug'), (40, 'Error'), (50, 'Fatal')], db_index=True, default=40)),
                ('msg', models.TextField()),
                ('trace', models.TextField(blank=True, null=True)),
                ('create_datetime', models.DateTimeField(auto_now_add=True, verbose_name='Created at')),
                ('owner', models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('result', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='Jobs.Result')),
            ],
            options={
                'verbose_name': 'Task Log Entries',
                'verbose_name_plural': 'Task Log Entries',
                'ordering': ('-create_datetime',),
            },
        ),
        migrations.CreateModel(
            name='ResultInputData',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transformed_input_data', models.TextField(blank=True, default='', verbose_name='Transformed Input Json Data')),
                ('raw_input_data', models.TextField(blank=True, default='', verbose_name='Raw Input Json Data')),
                ('owner', models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='ResultData',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('output_data', models.TextField(default='', verbose_name='Output JSON Data')),
                ('owner', models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name='result',
            name='input_data',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='Jobs.ResultInputData'),
        ),
        migrations.AddField(
            model_name='result',
            name='job',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='Jobs.Job'),
        ),
        migrations.AddField(
            model_name='result',
            name='job_step',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='Jobs.PipelineStep'),
        ),
        migrations.AddField(
            model_name='result',
            name='output_data',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='Jobs.ResultData'),
        ),
        migrations.AddField(
            model_name='result',
            name='owner',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name='PythonScript',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='', max_length=256, verbose_name='Lookup Name')),
                ('human_name', models.CharField(default='', max_length=32, verbose_name='Human Readable Name')),
                ('type', models.CharField(choices=[('RUN_ON_JOB', 'Run on Job Data (For monolith scripts)'), ('RUN_ON_JOB_DOCS_PARALLEL', 'Run on Each Doc in Job (Parallel Execution)'), ('RUN_ON_PAGE', 'Run on Each Page of Doc (Sharded Execution)')], default='RUN_ON_JOB', max_length=128)),
                ('description', models.TextField(blank=True, default='', verbose_name='Script Description')),
                ('supported_file_types', models.TextField(default='[".pdf"]', verbose_name='Supported File Types')),
                ('script', models.TextField(blank=True, default='', verbose_name='Python Code')),
                ('required_packages', models.TextField(blank=True, default='', verbose_name='Required Python Packages')),
                ('setup_script', models.TextField(blank=True, default='', verbose_name='Python setup script')),
                ('required_inputs', models.TextField(blank=True, default='', verbose_name='Required Inputs')),
                ('mode', models.CharField(choices=[('TEST', 'Test Mode'), ('DEPLOYED', 'Ready for Deployment')], default='TEST', max_length=128)),
                ('installer_log', models.TextField(blank=True, default='', verbose_name='Installation Log')),
                ('setup_log', models.TextField(blank=True, default='', verbose_name='Setup Log')),
                ('owner', models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name='pipelinestep',
            name='script',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='Jobs.PythonScript'),
        ),
        migrations.CreateModel(
            name='JobLogEntry',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('logger_name', models.CharField(max_length=100)),
                ('level', models.PositiveSmallIntegerField(choices=[(0, 'NotSet'), (20, 'Info'), (30, 'Warning'), (10, 'Debug'), (40, 'Error'), (50, 'Fatal')], db_index=True, default=40)),
                ('msg', models.TextField()),
                ('trace', models.TextField(blank=True, null=True)),
                ('create_datetime', models.DateTimeField(auto_now_add=True, verbose_name='Created at')),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='Jobs.Job')),
                ('owner', models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Job Log Entries',
                'verbose_name_plural': 'Job Log Entries',
                'ordering': ('-create_datetime',),
            },
        ),
        migrations.AddField(
            model_name='job',
            name='pipeline',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='Jobs.Pipeline'),
        ),
        migrations.AddField(
            model_name='job',
            name='started_steps',
            field=models.ManyToManyField(blank=True, to='Jobs.PipelineStep'),
        ),
        migrations.CreateModel(
            name='DocumentText',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rawText', models.TextField(default='', null=True, verbose_name='Extracted Text')),
                ('owner', models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name='document',
            name='jobs',
            field=models.ManyToManyField(blank=True, to='Jobs.Job'),
        ),
        migrations.AddField(
            model_name='document',
            name='owner',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='document',
            name='results',
            field=models.ManyToManyField(blank=True, to='Jobs.Result'),
        ),
        migrations.AddField(
            model_name='document',
            name='textObj',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='Jobs.DocumentText'),
        ),
    ]
