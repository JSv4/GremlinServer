# Generated by Django 3.0.5 on 2020-08-09 20:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Jobs', '0025_auto_20200809_1239'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pipelinenode',
            name='x_coord',
            field=models.FloatField(default=0, verbose_name='X Coordinate'),
        ),
        migrations.AlterField(
            model_name='pipelinenode',
            name='y_coord',
            field=models.FloatField(default=0, verbose_name='Y Coordinate'),
        ),
    ]
