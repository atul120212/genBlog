# Generated by Django 5.0.6 on 2024-05-22 07:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('generator', '0005_blogpost_thumbnail'),
    ]

    operations = [
        migrations.AlterField(
            model_name='blogpost',
            name='thumbnail',
            field=models.URLField(blank=True, max_length=500, null=True),
        ),
    ]
