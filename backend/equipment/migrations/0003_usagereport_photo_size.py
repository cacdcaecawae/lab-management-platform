from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("equipment", "0002_equipment_purchase_historicalequipment_purchase")]

    operations = [
        migrations.AddField(
            model_name="usagereport",
            name="photo_size",
            field=models.PositiveBigIntegerField("照片字节数", null=True, blank=True, editable=False),
        ),
    ]
