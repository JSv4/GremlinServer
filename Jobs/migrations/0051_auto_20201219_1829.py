# Generated by Django 3.1.1 on 2020-12-19 23:29

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('Jobs', '0050_auto_20201217_2132'),
    ]

    operations = [
        migrations.RenameField(
            model_name='scriptdatafile',
            old_name='zip_contents',
            new_name='manifest',
        ),
    ]
