# Generated by Django 3.1.1 on 2020-10-15 00:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Jobs', '0031_auto_20200921_2107'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='notification_email',
            field=models.CharField(blank=True, default='', max_length=512),
        ),
    ]