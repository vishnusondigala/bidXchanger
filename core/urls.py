from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('auction/create/', views.create_auction, name='create_auction'),
    path('auction/<int:item_id>/', views.auction_detail, name='auction_detail'),
    path('auction/<int:item_id>/place_bid/', views.place_bid, name='place_bid'),
    path('about/', views.about, name='about'),
    path('checkout/<int:item_id>/', views.checkout, name='checkout'),
    path('auction/<int:item_id>/cancel/', views.cancel_auction, name='cancel_auction'),
    path('auction/<int:item_id>/delete/', views.delete_auction, name='delete_auction'),
    path('bid/<int:bid_id>/withdraw/', views.withdraw_bid, name='withdraw_bid'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
]
