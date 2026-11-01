from django.core.exceptions import ValidationError
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from tags.models import UserTag
from words.models import UserWord

from datasets.models import UserDataset


def _validate_related_owners(instance, pk_set, reverse, related_model, using, error_code):
    if not pk_set:
        return

    if reverse:
        valid_count = UserDataset.objects.using(using).filter(pk__in=pk_set, user_id=instance.user_id).count()
    else:
        valid_count = related_model.objects.using(using).filter(pk__in=pk_set, user_id=instance.user_id).count()

    if valid_count != len(pk_set):
        raise ValidationError(error_code)


@receiver(m2m_changed, sender=UserDataset.tags.through, dispatch_uid="validate_user_dataset_tag_owners")
def validate_dataset_tag_owners(sender, instance, action, reverse, pk_set, using, **kwargs):
    if action == "pre_add":
        _validate_related_owners(instance, pk_set, reverse, UserTag, using, "dataset_tags_must_belong_to_user")


@receiver(m2m_changed, sender=UserDataset.extra_words.through, dispatch_uid="validate_user_dataset_word_owners")
def validate_dataset_word_owners(sender, instance, action, reverse, pk_set, using, **kwargs):
    if action == "pre_add":
        _validate_related_owners(instance, pk_set, reverse, UserWord, using, "dataset_words_must_belong_to_user")
