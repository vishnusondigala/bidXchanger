from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Category, AuctionItem, Bid, Notification

admin.site.register(CustomUser, UserAdmin)
admin.site.register(Category)
admin.site.register(AuctionItem)
admin.site.register(Bid)
admin.site.register(Notification)
