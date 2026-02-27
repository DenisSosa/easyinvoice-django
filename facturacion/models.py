import re
from django.db import models
from django.urls import reverse
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from django.conf import settings
from django.contrib.auth.models import User
import logging

logger = logging.getLogger(__name__)


class TimbradoConfig(models.Model):
    """Configuración global única de timbrado para el sistema"""
    establecimiento = models.CharField(
        max_length=3,
        verbose_name="Establecimiento",
        help_text="Código de establecimiento (3 dígitos, ej: 001)"
    )
    punto_expedicion = models.CharField(
        max_length=3,
        verbose_name="Punto de Expedición",
        help_text="Código de punto de expedición (3 dígitos, ej: 001)"
    )
    numero_timbrado = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Número de Timbrado",
        help_text="Número de timbrado SET (opcional)"
    )
    fecha_inicio = models.DateField(
        verbose_name="Fecha de Inicio",
        help_text="Fecha desde la cual es válido el timbrado"
    )
    fecha_vencimiento = models.DateField(
        verbose_name="Fecha de Vencimiento",
        help_text="Fecha hasta la cual es válido el timbrado"
    )
    activo = models.BooleanField(
        default=True,
        verbose_name="Activo",
        help_text="Solo puede existir una configuración activa"
    )
    creado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Creado por"
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de Creación"
    )

    class Meta:
        verbose_name = "Configuración de Timbrado"
        verbose_name_plural = "Configuraciones de Timbrado"
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f"{self.establecimiento}-{self.punto_expedicion} (Vigente: {self.fecha_inicio} a {self.fecha_vencimiento})"

    def clean(self):
        """Validar que solo exista una configuración activa"""
        super().clean()
        if self.activo:
            existe_activo = TimbradoConfig.objects.filter(activo=True)
            if self.pk:
                existe_activo = existe_activo.exclude(pk=self.pk)
            if existe_activo.exists():
                raise ValidationError('Ya existe una configuración de timbrado activa. Desactive la anterior primero.')
        
        if self.fecha_vencimiento <= self.fecha_inicio:
            raise ValidationError({'fecha_vencimiento': 'La fecha de vencimiento debe ser posterior a la fecha de inicio'})

    @staticmethod
    def get_activo():
        """Retorna la configuración activa o None"""
        try:
            return TimbradoConfig.objects.filter(activo=True).first()
        except Exception as e:
            logger.error(f'Error obteniendo TimbradoConfig activo: {e}')
            return None


class Producto(models.Model):
    """Modelo de Producto/Servicio"""
    nombre = models.CharField(max_length=200, verbose_name="Nombre")
    descripcion = models.TextField(blank=True, verbose_name="Descripción")
    precio = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name="Precio"
    )
    activo = models.BooleanField(default=True, verbose_name="Activo")
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} - ₲{self.precio:,.0f}"


class Cliente(models.Model):
    """
    Modelo2: Cliente del sistema de facturación
    """
    nombre = models.CharField(
        max_length=200,
        verbose_name="Nombre/Razón Social",
        help_text="Nombre completo o razón social del cliente"
    )
    ruc_ci = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="RUC/CI",
        help_text="Número de RUC o Cédula de Identidad"
    )
    
    def clean(self):
        """Validación del modelo Cliente"""
        super().clean()
        if self.ruc_ci:
            try:
                ruc_ci_clean = str(self.ruc_ci).strip()
                if not ruc_ci_clean:
                    raise ValidationError({'ruc_ci': 'El RUC/CI no puede estar vacío'})
            except (AttributeError, TypeError) as e:
                logger.error(f'Error validando RUC/CI en modelo Cliente: {e}')
                raise ValidationError({'ruc_ci': 'Formato de RUC/CI inválido'})
    direccion = models.CharField(
        max_length=300,
        verbose_name="Dirección",
        help_text="Dirección completa del cliente"
    )
    telefono = models.CharField(
        max_length=20,
        verbose_name="Teléfono",
        help_text="Número de teléfono de contacto"
    )
    email = models.EmailField(
        blank=True,
        null=True,
        verbose_name="Email",
        help_text="Correo electrónico del cliente (opcional)"
    )
    activo = models.BooleanField(
        default=True,
        verbose_name="Activo",
        help_text="Indica si el cliente está activo"
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de Registro"
    )
    fecha_actualizacion = models.DateTimeField(
        auto_now=True,
        verbose_name="Última Actualización"
    )

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} - {self.ruc_ci}"

    def get_absolute_url(self):
        return reverse('facturacion:cliente_detalle', kwargs={'pk': self.pk})

    def total_facturas(self):
        """Retorna el total de facturas del cliente"""
        try:
            return self.facturas.filter(activo=True).count()
        except Exception as e:
            logger.error(f'Error calculando total facturas para cliente {self.pk}: {e}')
            return 0

    def total_facturado(self):
        """Retorna el monto total facturado al cliente"""
        try:
            return self.facturas.filter(
                activo=True,
                estado='PAGADA'
            ).aggregate(
                total=models.Sum('total')
            )['total'] or Decimal('0')
        except Exception as e:
            logger.error(f'Error calculando total facturado para cliente {self.pk}: {e}')
            return Decimal('0')


class Factura(models.Model):
    """
    Modelo1: Factura del sistema
    """
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('PAGADA', 'Pagada'),
        ('ANULADA', 'Anulada'),
    ]

    numero_factura = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Número de Factura",
        help_text="Número único de la factura"
    )
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name='facturas',
        verbose_name="Cliente",
        help_text="Cliente al que se emite la factura"
    )
    fecha_emision = models.DateField(
        verbose_name="Fecha de Emisión",
        help_text="Fecha de emisión de la factura"
    )
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name="Subtotal",
        help_text="Subtotal sin IVA"
    )
    iva = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name="IVA (10%)",
        help_text="Impuesto al Valor Agregado"
    )
    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name="Total",
        help_text="Monto total a pagar"
    )
    estado = models.CharField(
        max_length=10,
        choices=ESTADO_CHOICES,
        default='PENDIENTE',
        verbose_name="Estado",
        help_text="Estado actual de la factura"
    )
    observaciones = models.TextField(
        blank=True,
        null=True,
        verbose_name="Observaciones",
        help_text="Observaciones o notas adicionales"
    )
    # ===== NUEVOS CAMPOS DE TIMBRADO =====
    timbrado = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Número de Timbrado",
        help_text="Número de timbrado autorizado por la SET (Paraguay)"
    )
    
    timbrado_fecha = models.DateField(
        blank=True,
        null=True,
        verbose_name="Fecha de Inicio del Timbrado",
        help_text="Fecha desde la cual es válido el timbrado"
    )
    
    timbrado_vencimiento = models.DateField(
        blank=True,
        null=True,
        verbose_name="Fecha de Vencimiento del Timbrado",
        help_text="Fecha hasta la cual es válido el timbrado"
    )
    
    timbrado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='facturas_timbradas',
        verbose_name="Timbrado por",
        help_text="Usuario que registró el timbrado"
    )
    
    timbrado_fecha_registro = models.DateTimeField(
        blank=True,
        null=True,
        auto_now_add=False,
        verbose_name="Fecha de Registro del Timbrado",
        help_text="Cuándo se añadió el timbrado al sistema"
    )
    activo = models.BooleanField(
        default=True,
        verbose_name="Activo"
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de Creación"
    )
    fecha_actualizacion = models.DateTimeField(
        auto_now=True,
        verbose_name="Última Actualización"
    )

    class Meta:
        verbose_name = "Factura"
        verbose_name_plural = "Facturas"
        ordering = ['-fecha_emision', '-numero_factura']

    def __str__(self):
        return f"Factura {self.numero_factura} - {self.cliente.nombre}"

    def get_absolute_url(self):
        return reverse('facturacion:factura_detalle', kwargs={'pk': self.pk})

    def calcular_totales(self):
        """Calcula subtotal, IVA y total basado en los detalles"""
        try:
            detalles = self.detalles.all()
            self.subtotal = sum(detalle.subtotal for detalle in detalles)
            self.iva = self.subtotal * Decimal(str(settings.IVA_PERCENTAGE / 100))
            self.total = self.subtotal + self.iva
            self.save(update_fields=['subtotal', 'iva', 'total'])
        except Exception as e:
            logger.error(f'Error calculando totales para factura {self.pk}: {e}')
            raise ValidationError('Error al calcular totales de la factura')

    def puede_editarse(self):
        """Verifica si la factura puede editarse"""
        return self.estado == 'PENDIENTE'

    def puede_anularse(self):
        """Verifica si la factura puede anularse"""
        return self.estado != 'ANULADA'

    def marcar_pagada(self):
        """Marca la factura como pagada"""
        self.estado = 'PAGADA'
        self.save()

    def anular(self):
        """Anula la factura"""
        self.estado = 'ANULADA'
        self.save()

    def get_estado_color(self):
        """Retorna el color del badge según el estado"""
        colores = {
            'PENDIENTE': 'warning',
            'PAGADA': 'success',
            'ANULADA': 'danger',
        }
        return colores.get(self.estado, 'secondary')
    def tiene_timbrado(self):
        """Verifica si la factura tiene timbrado registrado"""
        return bool(self.timbrado)
    
    def timbrado_vigente(self):
        """Verifica si el timbrado está vigente"""
        if not self.tiene_timbrado():
            return False
        
        try:
            hoy = timezone.now().date()
            
            if self.timbrado_fecha and self.fecha_emision < self.timbrado_fecha:
                return False
            
            if self.timbrado_vencimiento and self.fecha_emision > self.timbrado_vencimiento:
                return False
            
            return True
        except Exception as e:
            logger.error(f'Error verificando vigencia de timbrado para factura {self.pk}: {e}')
            return False
    
    def validar_timbrado_formato(self):
        """Validación básica del formato de timbrado"""
        if not self.timbrado:
            return True
        
        try:
            regex_pattern = getattr(settings, 'TIMBRADO_REGEX', r'^\d{8,15}$')
            return bool(re.match(regex_pattern, self.timbrado))
        except Exception as e:
            logger.error(f'Error validando formato de timbrado: {e}')
            return False
    @staticmethod
    def generar_numero_factura():
        """Genera el siguiente número de factura en formato paraguayo EEE-PPP-XXXXXXXX"""
        try:
            config = TimbradoConfig.get_activo()
            
            if not config:
                logger.warning('No existe TimbradoConfig activo, usando formato antiguo FAC-XXXXXX')
                from django.db.models import Max
                ultima_factura = Factura.objects.aggregate(
                    max_numero=Max('numero_factura')
                )['max_numero']
                
                if ultima_factura:
                    try:
                        ultimo_numero = int(ultima_factura.split('-')[-1])
                        nuevo_numero = ultimo_numero + 1
                    except (ValueError, IndexError, AttributeError):
                        nuevo_numero = getattr(settings, 'NUMERO_FACTURA_INICIO', 1000)
                else:
                    nuevo_numero = getattr(settings, 'NUMERO_FACTURA_INICIO', 1000)
                
                return f"FAC-{nuevo_numero:06d}"
            
            # Formato paraguayo: EEE-PPP-XXXXXXXX
            prefix = f"{config.establecimiento}-{config.punto_expedicion}-"
            
            # Buscar última factura con este prefijo
            from django.db.models import Max
            ultima_con_prefix = Factura.objects.filter(
                numero_factura__startswith=prefix
            ).aggregate(max_numero=Max('numero_factura'))['max_numero']
            
            if ultima_con_prefix:
                try:
                    # Extraer el contador del formato EEE-PPP-XXXXXXXX
                    ultimo_contador = int(ultima_con_prefix.split('-')[-1])
                    nuevo_contador = ultimo_contador + 1
                except (ValueError, IndexError):
                    nuevo_contador = 1
            else:
                nuevo_contador = 1
            
            # Formatear contador con 8 dígitos
            return f"{prefix}{nuevo_contador:08d}"
            
        except Exception as e:
            logger.error(f'Error generando número de factura: {e}')
            import time
            return f"FAC-{int(time.time())}"


class DetalleFactura(models.Model):
    """
    Modelo auxiliar: Detalle de cada producto/servicio en la factura
    """
    factura = models.ForeignKey(
        Factura,
        on_delete=models.CASCADE,
        related_name='detalles',
        verbose_name="Factura"
    )
    producto = models.CharField(
        max_length=200,
        verbose_name="Producto/Servicio",
        help_text="Descripción del producto o servicio"
    )
    cantidad = models.IntegerField(
        validators=[MinValueValidator(1)],
        verbose_name="Cantidad",
        help_text="Cantidad de unidades"
    )
    precio_unitario = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name="Precio Unitario",
        help_text="Precio por unidad"
    )
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name="Subtotal",
        help_text="Cantidad × Precio Unitario"
    )

    class Meta:
        verbose_name = "Detalle de Factura"
        verbose_name_plural = "Detalles de Factura"
        ordering = ['id']

    def __str__(self):
        return f"{self.producto} - {self.cantidad} × ₲{self.precio_unitario}"

    def save(self, *args, **kwargs):
        """Calcula el subtotal antes de guardar"""
        try:
            self.subtotal = Decimal(str(self.cantidad)) * self.precio_unitario
            super().save(*args, **kwargs)
            # Actualizar totales de la factura
            if self.factura_id:
                self.factura.calcular_totales()
        except Exception as e:
            logger.error(f'Error guardando detalle de factura: {e}')
            raise ValidationError('Error al guardar el detalle de la factura')