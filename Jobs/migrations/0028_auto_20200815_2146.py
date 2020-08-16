# Generated by Django 3.0.5 on 2020-08-16 02:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Jobs', '0027_auto_20200815_1753'),
    ]

    operations = [
        migrations.AddField(
            model_name='result',
            name='error',
            field=models.BooleanField(default=False, verbose_name='Step in Error Status'),
        ),
        migrations.AddField(
            model_name='result',
            name='finished',
            field=models.BooleanField(default=False, verbose_name='Step Finished'),
        ),
        migrations.AddField(
            model_name='result',
            name='started',
            field=models.BooleanField(default=False, verbose_name='Step started'),
        ),
    ]
