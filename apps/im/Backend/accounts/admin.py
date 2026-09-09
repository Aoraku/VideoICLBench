from django.contrib import admin

from .models import RevokedToken, UserProfile

admin.site.register(UserProfile)
admin.site.register(RevokedToken)
