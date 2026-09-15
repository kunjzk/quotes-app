from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    """
    Generalise Book into Source (author -> creator) so passages can come from
    more than books, and add a timestamp for positions in audio. Renames keep
    every existing row; constraints are recreated only to update their names.
    """

    dependencies = [
        ('quotes', '0009_today_preferences_and_last_shown'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='quote',
            name='unique_quote_per_user_per_book_when_not_deleted',
        ),
        migrations.RemoveConstraint(
            model_name='book',
            name='unique_title_author',
        ),
        migrations.RenameModel(old_name='Book', new_name='Source'),
        migrations.RenameField(model_name='source', old_name='author', new_name='creator'),
        migrations.RenameField(model_name='quote', old_name='book', new_name='source'),
        migrations.AddConstraint(
            model_name='source',
            constraint=models.UniqueConstraint(fields=('title', 'creator'), name='unique_source_title_creator'),
        ),
        migrations.AddConstraint(
            model_name='quote',
            constraint=models.UniqueConstraint(
                condition=Q(deleted_at__isnull=True),
                fields=('quote', 'user', 'source'),
                name='unique_quote_per_user_per_source_when_not_deleted',
            ),
        ),
        migrations.AddField(
            model_name='quote',
            name='timestamp_seconds',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.RenameField(model_name='todaypreference', old_name='author', new_name='creator'),
        migrations.RenameField(model_name='todaypreference', old_name='book_title', new_name='source_title'),
    ]
