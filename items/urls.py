from django.urls import path
from . import views

urlpatterns = [
    path('items/mine/', views.my_items_view, name='my_items'),
    path('items/new/', views.item_create_view, name='item_create'),
    path('items/<int:pk>/', views.item_detail_view, name='item_detail'),
    path('items/<int:pk>/edit/', views.item_edit_view, name='item_edit'),
    path('items/<int:pk>/toggle/', views.item_toggle_view, name='item_toggle'),
    path('items/<int:pk>/delete/', views.item_delete_view, name='item_delete'),
    path('items/browse/', views.browse_items_view, name='browse_items'),
    path('items/admin/', views.admin_items_view, name='admin_items'),
    path('items/admin/<int:pk>/delete/', views.admin_item_delete_view, name='admin_item_delete'),
]