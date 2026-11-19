from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("equipment", "0003_usagereport_photo_size")]

    operations = [
        migrations.AddField(
            model_name="usagereport",
            name="photo_uploaded_at",
            field=models.DateTimeField("当前照片上传时间", null=True, blank=True, editable=False),
        ),
    ]
