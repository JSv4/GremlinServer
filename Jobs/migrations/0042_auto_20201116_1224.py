# Generated by Django 3.1.1 on 2020-11-16 17:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Jobs', '0041_auto_20201114_2346'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='pipeline',
            name='digraph',
        ),
        migrations.AddField(
            model_name='pipeline',
            name='imported',
            field=models.BooleanField(default=False, verbose_name='Created from import'),
        ),
    ]