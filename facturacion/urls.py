"""
URLs para la aplicación de facturación
"""
from django.urls import path
from . import views

app_name = 'facturacion'

urlpatterns = [
    # Autenticación
    path('login/', views.login_usuario_view, name='login'),
    path('login-admin/', views.login_admin_view, name='login_admin'),
    path('logout/', views.logout_view, name='logout'),
    # Timbrado
    path('timbrado/configurar/', views.timbrado_configurar, name='timbrado_configurar'),
    path('timbrado/<int:pk>/eliminar/', views.timbrado_eliminar, name='timbrado_eliminar'),
    path('facturas/<int:pk>/timbrado/', views.factura_añadir_timbrado, name='factura_timbrado'),
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Facturas
    path('facturas/', views.factura_lista, name='factura_lista'),
    path('facturas/nueva/', views.factura_crear, name='factura_crear'),
    path('facturas/<int:pk>/', views.factura_detalle, name='factura_detalle'),
    path('facturas/<int:pk>/editar/', views.factura_editar, name='factura_editar'),
    path('facturas/<int:pk>/anular/', views.factura_anular, name='factura_anular'),
    path('facturas/<int:pk>/marcar-pagada/', views.factura_marcar_pagada, name='factura_marcar_pagada'),
    
    # Clientes
    path('clientes/', views.cliente_lista, name='cliente_lista'),
    path('clientes/nuevo/', views.cliente_crear, name='cliente_crear'),
    path('clientes/<int:pk>/', views.cliente_detalle, name='cliente_detalle'),
    path('clientes/<int:pk>/editar/', views.cliente_editar, name='cliente_editar'),
    path('clientes/<int:pk>/eliminar/', views.cliente_eliminar, name='cliente_eliminar'),
    
    # Productos
    path('productos/', views.producto_lista, name='producto_lista'),
    path('productos/nuevo/', views.producto_crear, name='producto_crear'),
    path('productos/<int:pk>/editar/', views.producto_editar, name='producto_editar'),
    path('productos/<int:pk>/eliminar/', views.producto_eliminar, name='producto_eliminar'),
    
    # Reportes
    path('reportes/ventas/', views.reportes_ventas, name='reportes_ventas'),
    path('reportes/ventas/pdf/', views.reportes_ventas_pdf, name='reportes_ventas_pdf'),
    
    # PDF
    path('facturas/<int:pk>/pdf/', views.factura_pdf, name='factura_pdf'),
    
    # API
    path('api/producto/<int:pk>/', views.api_producto_precio, name='api_producto_precio'),
]