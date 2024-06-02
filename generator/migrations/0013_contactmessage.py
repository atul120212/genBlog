# Generated by Django 5.0.6 on 2024-05-29 10:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('generator', '0012_alter_customuser_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContactMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('email', models.EmailField(max_length=254)),
                ('message', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
