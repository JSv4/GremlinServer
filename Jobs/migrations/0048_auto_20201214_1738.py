# Generated by Django 3.1.1 on 2020-12-14 22:38

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('Jobs', '0047_auto_20201213_1607'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='joblogentry',
            name='owner',
        ),
        migrations.RemoveField(
            model_name='tasklogentry',
            name='owner',
        ),
    ]
