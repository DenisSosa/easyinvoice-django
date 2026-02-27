from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import Cliente, Factura, DetalleFactura


class DetalleFacturaInline(admin.TabularInline):
    """Inline para los detalles de la factura"""
    model = DetalleFactura
    extra = 1
    fields = ['producto', 'cantidad', 'precio_unitario', 'subtotal']
    readonly_fields = ['subtotal']


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    """Configuración del administrador para Clientes"""
    list_display = ['nombre', 'ruc_ci', 'telefono', 'email', 'total_facturas_admin', 'activo', 'fecha_creacion']
    list_filter = ['activo', 'fecha_creacion']
    search_fields = ['nombre', 'ruc_ci', 'telefono', 'email']
    list_editable = ['activo']
    ordering = ['nombre']
    date_hierarchy = 'fecha_creacion'
    
    fieldsets = (
        ('Información Personal/Empresarial', {
            'fields': ('nombre', 'ruc_ci')
        }),
        ('Información de Contacto', {
            'fields': ('direccion', 'telefono', 'email')
        }),
        ('Estado', {
            'fields': ('activo',)
        }),
        ('Fechas', {
            'fields': ('fecha_creacion', 'fecha_actualizacion'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['fecha_creacion', 'fecha_actualizacion']
    
    def total_facturas_admin(self, obj):
        """Muestra el total de facturas del cliente"""
        try:
            total = obj.total_facturas()
            return format_html(
                "{} factura{}",
                total,
                's' if total != 1 else ''
            )
        except Exception:
            return "Error"
    total_facturas_admin.short_description = 'Total Facturas'


@admin.register(Factura)
class FacturaAdmin(admin.ModelAdmin):
    """Configuración del administrador para Facturas"""
    list_display = [
        'numero_factura', 'cliente', 'fecha_emision', 
        'subtotal', 'iva', 'total', 'estado_badge', 'fecha_creacion'
    ]
    list_filter = ['estado', 'fecha_emision', 'fecha_creacion']
    search_fields = ['numero_factura', 'cliente__nombre', 'cliente__ruc_ci']
    ordering = ['-fecha_emision', '-numero_factura']
    date_hierarchy = 'fecha_emision'
    list_per_page = 20
    inlines = [DetalleFacturaInline]
    
    fieldsets = (
        ('Información de la Factura', {
            'fields': ('numero_factura', 'cliente', 'fecha_emision')
        }),
        ('Montos', {
            'fields': ('subtotal', 'iva', 'total')
        }),
        ('Estado y Observaciones', {
            'fields': ('estado', 'observaciones', 'activo')
        }),
        ('Fechas del Sistema', {
            'fields': ('fecha_creacion', 'fecha_actualizacion'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['fecha_creacion', 'fecha_actualizacion', 'subtotal', 'iva', 'total']
    
    def estado_badge(self, obj):
        """Muestra el estado con colores"""
        colores = {
            'PENDIENTE': 'orange',
            'PAGADA': 'green',
            'ANULADA': 'red',
        }
        color = colores.get(obj.estado, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_estado_display()
        )
    
    estado_badge.short_description = 'Estado'
    
    actions = ['marcar_como_pagada', 'marcar_como_pendiente', 'anular_facturas']
    
    def marcar_como_pagada(self, request, queryset):
        """Marca facturas como pagadas"""
        updated = queryset.filter(estado='PENDIENTE').update(estado='PAGADA')
        self.message_user(request, f'{updated} factura(s) marcada(s) como pagada(s)')
    marcar_como_pagada.short_description = "Marcar como PAGADA"
    
    def marcar_como_pendiente(self, request, queryset):
        """Marca facturas como pendientes"""
        updated = queryset.filter(estado='PAGADA').update(estado='PENDIENTE')
        self.message_user(request, f'{updated} factura(s) marcada(s) como pendiente(s)')
    marcar_como_pendiente.short_description = "Marcar como PENDIENTE"
    
    def anular_facturas(self, request, queryset):
        """Anula facturas"""
        updated = queryset.exclude(estado='ANULADA').update(estado='ANULADA')
        self.message_user(request, f'{updated} factura(s) anulada(s)')
    anular_facturas.short_description = "ANULAR facturas seleccionadas"


@admin.register(DetalleFactura)
class DetalleFacturaAdmin(admin.ModelAdmin):
    """Configuración del administrador para Detalles de Factura"""
    list_display = ['factura', 'producto', 'cantidad', 'precio_unitario', 'subtotal']
    list_filter = ['factura__fecha_emision']
    search_fields = ['producto', 'factura__numero_factura']
    readonly_fields = ['subtotal']
    
    fieldsets = (
        ('Factura', {
            'fields': ('factura',)
        }),
        ('Detalle del Producto/Servicio', {
            'fields': ('producto', 'cantidad', 'precio_unitario', 'subtotal')
        }),
    )


# Personalización del sitio de administración
admin.site.site_header = "Administración del Sistema de Facturación"
admin.site.site_title = "Facturación Admin"
admin.site.index_title = "Panel de Control - Sistema de Facturación"