# Generated by Django 3.0.5 on 2020-05-30 01:15

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('Jobs', '0005_auto_20200529_1440'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='job',
            name='started_steps',
        ),
    ]