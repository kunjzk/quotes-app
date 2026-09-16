from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Sources gain a kind. Existing rows are books, which is the default, so no
    data changes. The unique constraint gains `kind`: one title and creator can
    be both a book and a song.
    """

    dependencies = [
        ('quotes', '0010_rename_book_to_source_add_timestamp'),
    ]

    operations = [
        migrations.AddField(
            model_name='source',
            name='kind',
            field=models.CharField(
                choices=[('book', 'Book'), ('song', 'Song')], default='book', max_length=16
            ),
        ),
        migrations.RemoveConstraint(
            model_name='source',
            name='unique_source_title_creator',
        ),
        migrations.AddConstraint(
            model_name='source',
            constraint=models.UniqueConstraint(
                fields=('title', 'creator', 'kind'), name='unique_source_title_creator_kind'
            ),
        ),
    ]
