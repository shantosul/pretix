# -*- coding: utf-8 -*-
# Generated by Django 1.10.7 on 2017-04-14 10:44
from __future__ import unicode_literals

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0055_auto_20170413_1537'),
    ]

    operations = [
        migrations.CreateModel(
            name='ItemAddOn',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('min_count', models.PositiveIntegerField(default=0, verbose_name='Minimum number')),
                ('max_count', models.PositiveIntegerField(default=1, verbose_name='Maximum number')),
            ],
        ),
        migrations.AddField(
            model_name='cartposition',
            name='addon_to',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='addons', to='pretixbase.CartPosition'),
        ),
        migrations.AddField(
            model_name='itemcategory',
            name='is_addon',
            field=models.BooleanField(default=False, help_text='If selected, the products belonging to this category are not for sale on their own. They can only be bought in combination with a product that has this category configured as a possible source for add-ons.', verbose_name='Products in this category are add-on products'),
        ),
        migrations.AddField(
            model_name='orderposition',
            name='addon_to',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='addons', to='pretixbase.OrderPosition'),
        ),
        migrations.AlterField(
            model_name='item',
            name='free_price',
            field=models.BooleanField(default=False, help_text='If this option is active, your users can choose the price themselves. The price configured above is then interpreted as the minimum price a user has to enter. You could use this e.g. to collect additional donations for your event. This is currently not supported for products that are bought as an add-on to other products.', verbose_name='Free price input'),
        ),
        migrations.AddField(
            model_name='itemaddon',
            name='addon_category',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='addon_to', to='pretixbase.ItemCategory', verbose_name='Category'),
        ),
        migrations.AddField(
            model_name='itemaddon',
            name='base_item',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='addons', to='pretixbase.Item'),
        ),
        migrations.AlterUniqueTogether(
            name='itemaddon',
            unique_together=set([('base_item', 'addon_category')]),
        ),
    ]