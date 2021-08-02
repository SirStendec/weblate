# Generated by Django 3.2.4 on 2021-07-07 12:28

from django.db import migrations, models

import weblate.utils.validators


class Migration(migrations.Migration):

    dependencies = [
        ("trans", "0136_auto_20210611_0731"),
    ]

    operations = [
        migrations.AlterField(
            model_name="project",
            name="language_aliases",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Comma-separated list of language code mappings, for example: en_GB:en,en_US:en",
                validators=[weblate.utils.validators.validate_language_aliases],
                verbose_name="Language aliases",
            ),
        ),
    ]
