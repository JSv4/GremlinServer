# Generated by Django 3.0.5 on 2020-05-27 03:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Jobs', '0002_auto_20200525_2059'),
    ]

    operations = [
        migrations.AddField(
            model_name='pythonscript',
            name='env_variables',
            field=models.TextField(blank=True, default='', verbose_name='Environment Variables'),
        ),
    ]