from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Sources gain an optional collection: the album a song belongs to. It is
    deliberately outside the unique constraint, so an album can be added to a
    song that was saved without one instead of creating a second source.
    """

    dependencies = [
        ('quotes', '0011_source_kind'),
    ]

    operations = [
        migrations.AddField(
            model_name='source',
            name='collection',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]
