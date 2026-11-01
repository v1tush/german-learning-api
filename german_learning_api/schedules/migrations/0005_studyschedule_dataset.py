import django.db.models.deletion
from django.db import migrations, models


def legacy_dataset_name(schedule_id):
    return f"Расписание #{schedule_id}"


def is_legacy_dataset_name(name, schedule_id):
    base_name = legacy_dataset_name(schedule_id)
    if name == base_name:
        return True

    prefix = f"{base_name} ("
    if not name.startswith(prefix) or not name.endswith(")"):
        return False
    suffix = name[len(prefix) : -1]
    return suffix.isdecimal() and int(suffix) >= 2 and suffix == str(int(suffix))


def find_reusable_dataset(UserDataset, db_alias, schedule, tag_ids):
    """Find one matching orphan without modifying or deleting its contents.

    Ambiguous matches are left alone; without a provenance field, the migration
    cannot prove which dataset came from an earlier application.
    """
    candidates = UserDataset.objects.using(db_alias).filter(
        user_id=schedule.user_id,
        name__startswith=legacy_dataset_name(schedule.pk),
        study_schedules__isnull=True,
        extra_words__isnull=True,
    )
    matches = [
        dataset
        for dataset in candidates.distinct()
        if is_legacy_dataset_name(dataset.name, schedule.pk)
        and set(dataset.tags.values_list("pk", flat=True)) == set(tag_ids)
    ]
    return matches[0] if len(matches) == 1 else None


def move_schedule_tags_to_datasets(apps, schema_editor):
    StudySchedule = apps.get_model("schedules", "StudySchedule")
    UserDataset = apps.get_model("datasets", "UserDataset")
    db_alias = schema_editor.connection.alias

    for schedule in StudySchedule.objects.using(db_alias).all().iterator(chunk_size=500):
        tag_ids = list(schedule.tags.values_list("pk", flat=True))
        if not tag_ids:
            # The old empty tag selection means every learning word.
            # A NULL dataset keeps that legacy behavior for existing schedules.
            continue

        reusable = find_reusable_dataset(UserDataset, db_alias, schedule, tag_ids)
        if reusable is not None:
            StudySchedule.objects.using(db_alias).filter(pk=schedule.pk).update(dataset_id=reusable.pk)
            continue

        base_name = legacy_dataset_name(schedule.pk)
        name = base_name
        suffix = 2
        while UserDataset.objects.using(db_alias).filter(user_id=schedule.user_id, name=name).exists():
            name = f"{base_name} ({suffix})"
            suffix += 1

        dataset = UserDataset.objects.using(db_alias).create(
            user_id=schedule.user_id,
            name=name,
        )
        dataset.tags.set(tag_ids)
        StudySchedule.objects.using(db_alias).filter(pk=schedule.pk).update(dataset_id=dataset.pk)


def restore_schedule_tags(apps, schema_editor):
    StudySchedule = apps.get_model("schedules", "StudySchedule")
    db_alias = schema_editor.connection.alias

    for schedule in StudySchedule.objects.using(db_alias).filter(dataset__isnull=False).iterator(chunk_size=500):
        schedule.tags.set(schedule.dataset.tags.values_list("pk", flat=True))


class Migration(migrations.Migration):
    dependencies = [
        ("datasets", "0001_initial"),
        ("schedules", "0004_remove_schedulerun_delivery_format_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="studyschedule",
            name="dataset",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="study_schedules",
                to="datasets.userdataset",
            ),
        ),
        migrations.RunPython(move_schedule_tags_to_datasets, restore_schedule_tags),
        migrations.RemoveField(model_name="studyschedule", name="tags"),
    ]
