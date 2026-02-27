"""
Formularios para el sistema de facturación
"""
from django import forms
from django.core.exceptions import ValidationError
from .models import Cliente, Factura, DetalleFactura, TimbradoConfig, Producto
from decimal import Decimal
from django.forms import inlineformset_factory
import re
import random
from datetime import date, timedelta
import logging

logger = logging.getLogger(__name__)


class ProductoForm(forms.ModelForm):
    """Formulario para productos"""
    class Meta:
        model = Producto
        fields = ['nombre', 'descripcion', 'precio', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del producto'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Descripción (opcional)'}),
            'precio': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }


class ClienteForm(forms.ModelForm):
    """
    Formulario para crear y editar clientes
    """
    class Meta:
        model = Cliente
        fields = ['nombre', 'ruc_ci', 'direccion', 'telefono', 'email', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombre completo o razón social',
                'required': True
            }),
            'ruc_ci': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: 12345678-9 o 80012345-6',
                'required': True
            }),
            'direccion': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Dirección completa',
                'required': True
            }),
            'telefono': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: 0981123456',
                'required': True
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'correo@ejemplo.com'
            }),
            'activo': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }
        labels = {
            'nombre': 'Nombre / Razón Social',
            'ruc_ci': 'RUC / Cédula de Identidad',
            'direccion': 'Dirección',
            'telefono': 'Teléfono',
            'email': 'Email',
            'activo': '¿Cliente Activo?'
        }

    def clean_ruc_ci(self):
        """Validación del RUC/CI"""
        ruc_ci = self.cleaned_data.get('ruc_ci')
        if ruc_ci:
            try:
                ruc_ci = ruc_ci.strip().replace(' ', '').replace('-', '')
                if not re.match(r'^\d{6,10}$', ruc_ci):
                    raise forms.ValidationError("El RUC/CI debe contener entre 6 y 10 dígitos")
                
                existe = Cliente.objects.filter(ruc_ci__iexact=ruc_ci)
                if self.instance.pk:
                    existe = existe.exclude(pk=self.instance.pk)
                if existe.exists():
                    raise forms.ValidationError("Ya existe un cliente con este RUC/CI")
            except forms.ValidationError:
                raise
            except Exception as e:
                logger.error(f'Error validando RUC/CI: {e}')
                raise forms.ValidationError("Error en la validación del RUC/CI")
        return ruc_ci

    def clean_telefono(self):
        """Validación del teléfono"""
        telefono = self.cleaned_data.get('telefono')
        if telefono:
            telefono = telefono.strip().replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
            if not telefono.isdigit():
                raise forms.ValidationError("El teléfono debe contener solo números")
            if len(telefono) < 7:
                raise forms.ValidationError("El teléfono debe tener al menos 7 dígitos")
        return telefono


class FacturaForm(forms.ModelForm):
    """
    Formulario para crear y editar facturas
    """
    class Meta:
        model = Factura
        fields = ['cliente', 'fecha_emision', 'estado', 'observaciones']
        widgets = {
            'cliente': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'fecha_emision': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'required': True
            }),
            'estado': forms.Select(attrs={
                'class': 'form-select'
            }),
            'observaciones': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Observaciones o notas adicionales (opcional)'
            })
        }
        labels = {
            'cliente': 'Cliente',
            'fecha_emision': 'Fecha de Emisión',
            'estado': 'Estado',
            'observaciones': 'Observaciones'
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.es_creacion = kwargs.pop('es_creacion', False)
        super().__init__(*args, **kwargs)
        
        try:
            self.fields['cliente'].queryset = Cliente.objects.filter(activo=True).order_by('nombre')
        except Exception as e:
            logger.error(f'Error inicializando FacturaForm: {e}')
            self.fields['cliente'].queryset = Cliente.objects.none()
        
        # Limitar opciones de estado según contexto
        if self.es_creacion:
            # Al crear: solo Pendiente y Pagada
            self.fields['estado'].choices = [
                ('PENDIENTE', 'Pendiente'),
                ('PAGADA', 'Pagada'),
            ]
        else:
            # Al editar: incluir Anulada solo para administradores
            if self.user and (self.user.is_staff or self.user.is_superuser):
                self.fields['estado'].choices = Factura.ESTADO_CHOICES
            else:
                self.fields['estado'].choices = [
                    ('PENDIENTE', 'Pendiente'),
                    ('PAGADA', 'Pagada'),
                ]
    
    def clean_estado(self):
        estado = self.cleaned_data.get('estado')
        
        # Validación en creación: no permitir Anulada
        if self.es_creacion and estado == 'ANULADA':
            return 'PENDIENTE'
        
        # Validación en edición: solo admin puede anular
        if not self.es_creacion and estado == 'ANULADA':
            if not self.user or not (self.user.is_staff or self.user.is_superuser):
                raise forms.ValidationError('Solo los administradores pueden anular facturas')
        
        return estado


class DetalleFacturaForm(forms.ModelForm):
    """
    Formulario para los detalles de la factura (productos/servicios)
    """
    producto_catalogo = forms.ModelChoiceField(
        queryset=Producto.objects.filter(activo=True),
        required=False,
        empty_label="Seleccionar producto del catálogo...",
        widget=forms.Select(attrs={
            'class': 'form-select producto-select',
            'onchange': 'cargarProducto(this)'
        }),
        label='Producto del Catálogo'
    )
    
    class Meta:
        model = DetalleFactura
        fields = ['producto', 'cantidad', 'precio_unitario']
        widgets = {
            'producto': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'O escriba descripción manual'
            }),
            'cantidad': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'value': '1'
            }),
            'precio_unitario': forms.NumberInput(attrs={
                'class': 'form-control precio-input',
                'step': '0.01',
                'min': '0.01',
                'placeholder': '0.00'
            })
        }
        labels = {
            'producto': 'Descripción',
            'cantidad': 'Cantidad',
            'precio_unitario': 'Precio Unitario (₲)'
        }

    def clean(self):
        cleaned_data = super().clean()
        producto = cleaned_data.get('producto')
        cantidad = cleaned_data.get('cantidad')
        precio = cleaned_data.get('precio_unitario')
        
        # Solo validar si hay algún dato ingresado
        if producto or cantidad or precio:
            if not producto:
                raise forms.ValidationError('Debe ingresar la descripción del producto')
            if not cantidad or cantidad < 1:
                raise forms.ValidationError('La cantidad debe ser al menos 1')
            if not precio or precio <= Decimal('0'):
                raise forms.ValidationError('El precio debe ser mayor a 0')
        
        return cleaned_data


# Formset para manejar múltiples detalles en una factura
DetalleFacturaFormSet = inlineformset_factory(
    Factura,
    DetalleFactura,
    form=DetalleFacturaForm,
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
    validate_max=False
)


class BusquedaFacturaForm(forms.Form):
    """
    Formulario para búsqueda y filtrado de facturas
    """
    buscar = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Buscar por número de factura o cliente...',
            'id': 'buscarFactura'
        })
    )

    estado = forms.ChoiceField(
        required=False,
        choices=[('', 'Todos los estados')] + Factura.ESTADO_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )

    cliente = forms.ModelChoiceField(
        queryset=Cliente.objects.filter(activo=True),
        required=False,
        empty_label="Todos los clientes",
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )

    fecha_desde = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label="Desde"
    )

    fecha_hasta = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label="Hasta"
    )

    ordenar = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'Ordenar por...'),
            ('-fecha_emision', 'Fecha (más reciente)'),
            ('fecha_emision', 'Fecha (más antigua)'),
            ('-total', 'Monto (mayor a menor)'),
            ('total', 'Monto (menor a mayor)'),
            ('-numero_factura', 'Número (descendente)'),
            ('numero_factura', 'Número (ascendente)'),
        ],
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        fecha_desde = cleaned_data.get('fecha_desde')
        fecha_hasta = cleaned_data.get('fecha_hasta')
        if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
            raise forms.ValidationError("La fecha 'Desde' no puede ser posterior a la fecha 'Hasta'")
        return cleaned_data


class BusquedaClienteForm(forms.Form):
    """
    Formulario para búsqueda de clientes
    """
    buscar = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Buscar por nombre, RUC/CI o teléfono...',
            'id': 'buscarCliente'
        })
    )

    activo = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'Todos'),
            ('1', 'Activos'),
            ('0', 'Inactivos'),
        ],
        widget=forms.Select(attrs={
            'class': 'form-select'
        }),
        label='Estado'
    )

    ordenar = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'Ordenar por...'),
            ('nombre', 'Nombre (A-Z)'),
            ('-nombre', 'Nombre (Z-A)'),
            ('-fecha_creacion', 'Más recientes'),
            ('fecha_creacion', 'Más antiguos'),
        ],
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
class FacturaEliminarForm(forms.Form):
    """
    Formulario de confirmación con captcha matemático simple
    para eliminar/anular facturas
    """
    captcha_respuesta = forms.IntegerField(
        label="Respuesta",
        required=True,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ingrese el resultado',
            'autocomplete': 'off'
        }),
        help_text="Resuelva la operación para confirmar"
    )
    
    def __init__(self, *args, **kwargs):
        self.captcha_a = random.randint(1, 10)
        self.captcha_b = random.randint(1, 10)
        self.captcha_respuesta_correcta = self.captcha_a + self.captcha_b
        super().__init__(*args, **kwargs)
        self.fields['captcha_respuesta'].label = f"¿Cuánto es {self.captcha_a} + {self.captcha_b}?"
    
    def clean_captcha_respuesta(self):
        respuesta = self.cleaned_data.get('captcha_respuesta')
        if respuesta != self.captcha_respuesta_correcta:
            raise forms.ValidationError("Respuesta incorrecta. Intente nuevamente.")
        return respuesta


class TimbradoForm(forms.ModelForm):
    """
    Formulario para agregar o editar timbrado (legal en Paraguay)
    """
    class Meta:
        model = Factura
        fields = ['timbrado', 'timbrado_fecha', 'timbrado_vencimiento']
        widgets = {
            'timbrado': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 12345678'}),
            'timbrado_fecha': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'timbrado_vencimiento': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def clean_timbrado(self):
        timbrado = self.cleaned_data.get('timbrado')
        if not timbrado:
            return timbrado
        timbrado = timbrado.strip().replace('-', '').replace(' ', '')
        if not re.match(r'^\d{8,15}$', timbrado):
            raise forms.ValidationError("Formato de timbrado inválido (8-15 dígitos).")
        return timbrado

    def clean(self):
        cleaned_data = super().clean()
        inicio = cleaned_data.get('timbrado_fecha')
        venc = cleaned_data.get('timbrado_vencimiento')
        if inicio and venc and venc <= inicio:
            self.add_error('timbrado_vencimiento', 'La fecha de vencimiento debe ser posterior.')
        return cleaned_data


class TimbradoConfigForm(forms.ModelForm):
    """
    Formulario para configurar el timbrado global del sistema
    """
    confirmar_reemplazo = forms.BooleanField(
        required=False,
        label="Confirmo que deseo reemplazar la configuración activa",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    class Meta:
        model = TimbradoConfig
        fields = ['establecimiento', 'punto_expedicion', 'numero_timbrado', 'fecha_inicio', 'fecha_vencimiento']
        widgets = {
            'establecimiento': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '001',
                'maxlength': '3',
                'pattern': '[0-9]{3}'
            }),
            'punto_expedicion': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '001',
                'maxlength': '3',
                'pattern': '[0-9]{3}'
            }),
            'numero_timbrado': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Número de timbrado SET (opcional)'
            }),
            'fecha_inicio': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'fecha_vencimiento': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            })
        }
        labels = {
            'establecimiento': 'Establecimiento (3 dígitos)',
            'punto_expedicion': 'Punto de Expedición (3 dígitos)',
            'numero_timbrado': 'Número de Timbrado SET',
            'fecha_inicio': 'Fecha de Inicio',
            'fecha_vencimiento': 'Fecha de Vencimiento'
        }
    
    def __init__(self, *args, **kwargs):
        self.requiere_confirmacion = kwargs.pop('requiere_confirmacion', False)
        super().__init__(*args, **kwargs)
        if not self.requiere_confirmacion:
            del self.fields['confirmar_reemplazo']
    
    def clean_establecimiento(self):
        establecimiento = self.cleaned_data.get('establecimiento')
        if not re.match(r'^\d{3}$', establecimiento):
            raise forms.ValidationError('Debe ser exactamente 3 dígitos numéricos (ej: 001)')
        return establecimiento
    
    def clean_punto_expedicion(self):
        punto = self.cleaned_data.get('punto_expedicion')
        if not re.match(r'^\d{3}$', punto):
            raise forms.ValidationError('Debe ser exactamente 3 dígitos numéricos (ej: 001)')
        return punto
    
    def clean(self):
        cleaned_data = super().clean()
        fecha_inicio = cleaned_data.get('fecha_inicio')
        fecha_venc = cleaned_data.get('fecha_vencimiento')
        
        if fecha_inicio and fecha_venc and fecha_venc <= fecha_inicio:
            self.add_error('fecha_vencimiento', 'La fecha de vencimiento debe ser posterior a la fecha de inicio')
        
        if self.requiere_confirmacion:
            confirmar = cleaned_data.get('confirmar_reemplazo')
            if not confirmar:
                raise forms.ValidationError('Debe confirmar el reemplazo de la configuración activa')
        
        return cleaned_data
