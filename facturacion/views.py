from django.shortcuts import render

# Create your views here.
"""
Vistas para el sistema de facturación
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.html import escape
from django.core.exceptions import ValidationError
from django.db import transaction
from django.contrib.auth import authenticate, login, logout
from django.db.models import Q, Sum, Count
from django.core.paginator import Paginator
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from datetime import date, timedelta
from decimal import Decimal
from .models import Cliente, Factura, DetalleFactura, TimbradoConfig, Producto
from .forms import (
    ClienteForm, FacturaForm, DetalleFacturaFormSet,
    BusquedaFacturaForm, BusquedaClienteForm, FacturaEliminarForm, TimbradoForm, TimbradoConfigForm, ProductoForm
)
import logging

logger = logging.getLogger(__name__)


def enviar_factura_email(factura):
    """Envía la factura por correo electrónico al cliente"""
    try:
        if not factura.cliente.email:
            return False, 'El cliente no tiene email registrado'
        
        detalles = factura.detalles.all()
        
        asunto = f'Factura {factura.numero_factura} - Sistema de Facturación'
        
        mensaje = f"""
Estimado/a {factura.cliente.nombre},

Adjuntamos la factura {factura.numero_factura} correspondiente a su compra.

DETALLE DE LA FACTURA:
{'='*50}
Número: {factura.numero_factura}
Fecha: {factura.fecha_emision.strftime('%d/%m/%Y')}
Estado: {factura.get_estado_display()}

PRODUCTOS/SERVICIOS:
{'-'*50}
"""
        
        for detalle in detalles:
            mensaje += f"{detalle.producto} - Cant: {detalle.cantidad} x ₲{detalle.precio_unitario:,.0f} = ₲{detalle.subtotal:,.0f}\n"
        
        mensaje += f"""
{'-'*50}
Subtotal: ₲{factura.subtotal:,.0f}
IVA (10%): ₲{factura.iva:,.0f}
TOTAL: ₲{factura.total:,.0f}
{'='*50}

Gracias por su preferencia.

Saludos cordiales,
Sistema de Facturación
"""
        
        email = EmailMessage(
            asunto,
            mensaje,
            to=[factura.cliente.email]
        )
        
        email.send()
        return True, 'Factura enviada exitosamente'
        
    except Exception as e:
        logger.error(f'Error enviando factura por email: {e}')
        return False, f'Error al enviar email: {str(e)}'


# ==================== AUTENTICACIÓN ====================

def login_usuario_view(request):
    """Vista de inicio de sesión para usuarios normales"""
    if request.user.is_authenticated:
        return redirect('facturacion:dashboard')
    
    if request.method == 'POST':
        try:
            username = request.POST.get('username', '').strip()
            password = request.POST.get('password', '')
            
            if not username or not password:
                messages.error(request, 'Usuario y contraseña son requeridos')
                return render(request, 'facturacion/login_particles.html')
            
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                login(request, user)
                messages.success(request, f'¡Bienvenido {escape(user.username)}!')
                next_url = request.GET.get('next')
                if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                    return redirect(next_url)
                return redirect('facturacion:dashboard')
            else:
                messages.error(request, 'Usuario o contraseña incorrectos')
        except Exception as e:
            logger.error(f'Error en login usuario: {e}')
            messages.error(request, 'Error interno del servidor')
    
    return render(request, 'facturacion/login_particles.html')


def login_admin_view(request):
    """Vista de inicio de sesión exclusiva para administradores"""
    if request.user.is_authenticated:
        return redirect('facturacion:dashboard')
    
    if request.method == 'POST':
        try:
            username = request.POST.get('username', '').strip()
            password = request.POST.get('password', '')
            
            if not username or not password:
                messages.error(request, 'Usuario y contraseña son requeridos')
                return render(request, 'facturacion/login_admin_particles.html')
            
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                login(request, user)
                if user.is_staff or user.is_superuser:
                    messages.success(request, f'¡Bienvenido Administrador {escape(user.username)}!')
                else:
                    messages.success(request, f'¡Bienvenido {escape(user.username)}!')
                next_url = request.GET.get('next')
                if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                    return redirect(next_url)
                return redirect('facturacion:dashboard')
            else:
                messages.error(request, 'Usuario o contraseña incorrectos')
        except Exception as e:
            logger.error(f'Error en login admin: {e}')
            messages.error(request, 'Error interno del servidor')
    
    return render(request, 'facturacion/login_admin_particles.html')


@login_required
def logout_view(request):
    """Vista de cierre de sesión"""
    logout(request)
    messages.info(request, 'Has cerrado sesión correctamente')
    return redirect('facturacion:login')


# ==================== DASHBOARD ====================

@login_required
def dashboard(request):
    """Vista principal con dashboard y estadísticas"""
    # Estadísticas generales
    total_facturas = Factura.objects.filter(activo=True).count()
    total_clientes = Cliente.objects.filter(activo=True).count()
    
    # Total facturado (solo facturas pagadas)
    total_facturado = Factura.objects.filter(
        activo=True,
        estado='PAGADA'
    ).aggregate(total=Sum('total'))['total'] or Decimal('0')
    
    # Facturas pendientes
    facturas_pendientes = Factura.objects.filter(
        activo=True,
        estado='PENDIENTE'
    ).count()
    
    # Monto pendiente de cobro
    monto_pendiente = Factura.objects.filter(
        activo=True,
        estado='PENDIENTE'
    ).aggregate(total=Sum('total'))['total'] or Decimal('0')
    
    # Últimas 5 facturas - optimizado
    try:
        ultimas_facturas = Factura.objects.filter(
            activo=True
        ).select_related('cliente').order_by('-fecha_emision', '-numero_factura')[:5]
    except Exception as e:
        logger.error(f'Error obteniendo últimas facturas: {e}')
        ultimas_facturas = []
    
    # Clientes con más facturas
    top_clientes = Cliente.objects.filter(
        activo=True
    ).annotate(
        total_facturas=Count('facturas', filter=Q(facturas__activo=True)),
        total_facturado=Sum('facturas__total', filter=Q(facturas__activo=True, facturas__estado='PAGADA'))
    ).filter(total_facturas__gt=0).order_by('-total_facturado')[:5]
    
    # Estadísticas por estado
    facturas_por_estado = Factura.objects.filter(
        activo=True
    ).values('estado').annotate(
        cantidad=Count('id'),
        total=Sum('total')
    ).order_by('estado')
    
    # Facturación del mes actual - con timezone aware
    try:
        hoy = timezone.now().date()
        inicio_mes = hoy.replace(day=1)
        facturacion_mes = Factura.objects.filter(
            activo=True,
            fecha_emision__gte=inicio_mes,
            estado='PAGADA'
        ).aggregate(total=Sum('total'))['total'] or Decimal('0')
    except Exception as e:
        logger.error(f'Error calculando facturación del mes: {e}')
        facturacion_mes = Decimal('0')
    
    context = {
        'total_facturas': total_facturas,
        'total_clientes': total_clientes,
        'total_facturado': total_facturado,
        'facturas_pendientes': facturas_pendientes,
        'monto_pendiente': monto_pendiente,
        'ultimas_facturas': ultimas_facturas,
        'top_clientes': top_clientes,
        'facturas_por_estado': facturas_por_estado,
        'facturacion_mes': facturacion_mes,
    }
    
    return render(request, 'facturacion/dashboard.html', context)


# ==================== CRUD FACTURAS ====================

@login_required
def factura_lista(request):
    """Vista de listado de facturas con búsqueda y filtros"""
    facturas = Factura.objects.filter(activo=True).select_related('cliente')
    form = BusquedaFacturaForm(request.GET)
    
    if form.is_valid():
        # Búsqueda por texto
        buscar = form.cleaned_data.get('buscar')
        if buscar:
            facturas = facturas.filter(
                Q(numero_factura__icontains=buscar) |
                Q(cliente__nombre__icontains=buscar) |
                Q(cliente__ruc_ci__icontains=buscar)
            )
        
        # Filtro por estado
        estado = form.cleaned_data.get('estado')
        if estado:
            facturas = facturas.filter(estado=estado)
        
        # Filtro por cliente
        cliente = form.cleaned_data.get('cliente')
        if cliente:
            facturas = facturas.filter(cliente=cliente)
        
        # Filtro por rango de fechas
        fecha_desde = form.cleaned_data.get('fecha_desde')
        fecha_hasta = form.cleaned_data.get('fecha_hasta')
        if fecha_desde:
            facturas = facturas.filter(fecha_emision__gte=fecha_desde)
        if fecha_hasta:
            facturas = facturas.filter(fecha_emision__lte=fecha_hasta)
        
        # Ordenamiento
        ordenar = form.cleaned_data.get('ordenar')
        if ordenar:
            facturas = facturas.order_by(ordenar)
    
    # Paginación
    paginator = Paginator(facturas, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'form': form,
        'total_facturas': facturas.count()
    }
    
    return render(request, 'facturacion/factura_lista.html', context)


@login_required
def factura_detalle(request, pk):
    """Vista de detalle de factura"""
    factura = get_object_or_404(Factura, pk=pk)
    detalles = factura.detalles.all()
    
    context = {
        'factura': factura,
        'detalles': detalles
    }
    return render(request, 'facturacion/factura_detalle.html', context)


@login_required
def factura_crear(request):
    """Vista para crear nueva factura"""
    # Validar timbrado antes de permitir crear factura
    config_timbrado = TimbradoConfig.get_activo()
    hoy = timezone.now().date()
    
    if not config_timbrado:
        messages.error(request, 'No se puede crear facturas: No hay timbrado configurado en el sistema')
        return redirect('facturacion:factura_lista')
    
    if hoy < config_timbrado.fecha_inicio:
        messages.error(request, f'No se puede crear facturas: El timbrado aún no está vigente (inicia el {config_timbrado.fecha_inicio})')
        return redirect('facturacion:factura_lista')
    
    if hoy > config_timbrado.fecha_vencimiento:
        messages.error(request, f'No se puede crear facturas: El timbrado está vencido (venció el {config_timbrado.fecha_vencimiento})')
        return redirect('facturacion:factura_lista')
    
    if request.method == 'POST':
        form = FacturaForm(request.POST, user=request.user, es_creacion=True)
        formset = DetalleFacturaFormSet(request.POST)
        
        try:
            if form.is_valid() and formset.is_valid():
                with transaction.atomic():
                    # Crear la factura
                    factura = form.save(commit=False)
                    factura.numero_factura = Factura.generar_numero_factura()
                    
                    # Validación adicional: no permitir estado Anulada en creación
                    if factura.estado == 'ANULADA':
                        factura.estado = 'PENDIENTE'
                    
                    factura.save()
                    
                    # Guardar los detalles
                    formset.instance = factura
                    formset.save()
                    
                    # Calcular totales
                    factura.calcular_totales()
                    
                    messages.success(request, f'Factura {escape(factura.numero_factura)} creada exitosamente')
                    
                return redirect('facturacion:factura_detalle', pk=factura.pk)
            else:
                messages.error(request, 'Por favor corrija los errores en el formulario')
        except Exception as e:
            logger.error(f'Error creando factura: {e}')
            messages.error(request, 'Error interno al crear la factura')
    else:
        form = FacturaForm(initial={'fecha_emision': timezone.now().date()}, user=request.user, es_creacion=True)
        formset = DetalleFacturaFormSet()
    
    productos = Producto.objects.filter(activo=True).order_by('nombre')
    context = {
        'form': form,
        'formset': formset,
        'productos': productos,
        'accion': 'Crear'
    }
    return render(request, 'facturacion/factura_form.html', context)


@login_required
def factura_editar(request, pk):
    """Vista para editar factura existente"""
    try:
        factura = get_object_or_404(Factura, pk=pk, activo=True)
        
        if not factura.puede_editarse():
            messages.error(request, 'No se puede editar una factura pagada o anulada')
            return redirect('facturacion:factura_detalle', pk=factura.pk)
        
        if request.method == 'POST':
            form = FacturaForm(request.POST, instance=factura, user=request.user, es_creacion=False)
            formset = DetalleFacturaFormSet(request.POST, instance=factura)
            
            try:
                if form.is_valid() and formset.is_valid():
                    with transaction.atomic():
                        form.save()
                        formset.save()
                        factura.calcular_totales()
                        
                    messages.success(request, f'Factura {escape(factura.numero_factura)} actualizada exitosamente')
                    return redirect('facturacion:factura_detalle', pk=factura.pk)
                else:
                    messages.error(request, 'Por favor corrija los errores en el formulario')
            except Exception as e:
                logger.error(f'Error editando factura {pk}: {e}')
                messages.error(request, 'Error interno al actualizar la factura')
        else:
            form = FacturaForm(instance=factura, user=request.user, es_creacion=False)
            formset = DetalleFacturaFormSet(instance=factura)
        
        productos = Producto.objects.filter(activo=True).order_by('nombre')
        context = {
            'form': form,
            'formset': formset,
            'factura': factura,
            'productos': productos,
            'accion': 'Editar'
        }
        return render(request, 'facturacion/factura_form.html', context)
    except Exception as e:
        logger.error(f'Error accediendo a factura {pk}: {e}')
        messages.error(request, 'Factura no encontrada')
        return redirect('facturacion:factura_lista')


@login_required
def factura_anular(request, pk):
    """Vista para anular factura con captcha de seguridad"""
    try:
        factura = get_object_or_404(Factura, pk=pk, activo=True)
        
        if not factura.puede_anularse():
            messages.error(request, 'Esta factura ya está anulada.')
            return redirect('facturacion:factura_detalle', pk=factura.pk)
        
        if request.method == 'POST':
            form = FacturaEliminarForm(request.POST)
            
            # Recuperar captcha de la sesión
            try:
                if 'captcha_a' in request.session and 'captcha_b' in request.session:
                    form.captcha_a = request.session['captcha_a']
                    form.captcha_b = request.session['captcha_b']
                    form.captcha_respuesta_correcta = form.captcha_a + form.captcha_b
                else:
                    messages.error(request, 'Sesión expirada. Intente nuevamente.')
                    return redirect('facturacion:factura_anular', pk=pk)
                
                if form.is_valid():
                    with transaction.atomic():
                        factura.anular()
                    request.session.pop('captcha_a', None)
                    request.session.pop('captcha_b', None)
                    messages.success(request, f'Factura {escape(factura.numero_factura)} anulada exitosamente')
                    return redirect('facturacion:factura_lista')
                else:
                    messages.error(request, 'Captcha incorrecto. Intente nuevamente.')
            except Exception as e:
                logger.error(f'Error anulando factura {pk}: {e}')
                messages.error(request, 'Error interno al anular la factura')
        else:
            form = FacturaEliminarForm()
            request.session['captcha_a'] = form.captcha_a
            request.session['captcha_b'] = form.captcha_b
        
        context = {'factura': factura, 'form': form}
        return render(request, 'facturacion/factura_confirmar_anular.html', context)
    except Exception as e:
        logger.error(f'Error accediendo a factura para anular {pk}: {e}')
        messages.error(request, 'Factura no encontrada')
        return redirect('facturacion:factura_lista')

@login_required
def factura_marcar_pagada(request, pk):
    """Vista para marcar factura como pagada"""
    factura = get_object_or_404(Factura, pk=pk)
    
    if factura.estado == 'PAGADA':
        messages.info(request, 'La factura ya está marcada como pagada')
    elif factura.estado == 'ANULADA':
        messages.error(request, 'No se puede marcar como pagada una factura anulada')
    else:
        factura.marcar_pagada()
        messages.success(request, f'Factura {factura.numero_factura} marcada como pagada')
    
    return redirect('facturacion:factura_detalle', pk=factura.pk)


@login_required
def factura_pdf(request, pk):
    """Vista para generar PDF de factura"""
    from django.http import HttpResponse
    from .utils import generar_pdf_factura
    
    try:
        factura = get_object_or_404(Factura, pk=pk)
        pdf_buffer = generar_pdf_factura(factura)
        
        response = HttpResponse(pdf_buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="factura_{factura.numero_factura}.pdf"'
        return response
    except Exception as e:
        logger.error(f'Error generando PDF de factura {pk}: {e}')
        messages.error(request, 'Error al generar el PDF')
        return redirect('facturacion:factura_detalle', pk=pk)


# ==================== CRUD CLIENTES ====================

@login_required
def cliente_lista(request):
    """Vista de listado de clientes"""
    clientes = Cliente.objects.filter(activo=True).annotate(
        total_facturas=Count('facturas', filter=Q(facturas__activo=True)),
        total_facturado=Sum('facturas__total', filter=Q(facturas__activo=True, facturas__estado='PAGADA'))
    )
    
    form = BusquedaClienteForm(request.GET)
    
    if form.is_valid():
        buscar = form.cleaned_data.get('buscar')
        if buscar:
            clientes = clientes.filter(
                Q(nombre__icontains=buscar) |
                Q(ruc_ci__icontains=buscar) |
                Q(telefono__icontains=buscar)
            )
        
        ordenar = form.cleaned_data.get('ordenar')
        if ordenar:
            clientes = clientes.order_by(ordenar)
    
    # Paginación
    paginator = Paginator(clientes, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'form': form,
        'total_clientes': clientes.count()
    }
    return render(request, 'facturacion/cliente_lista.html', context)


@login_required
def cliente_detalle(request, pk):
    """Vista de detalle de cliente"""
    cliente = get_object_or_404(Cliente, pk=pk)
    facturas = cliente.facturas.filter(activo=True).order_by('-fecha_emision')
    
    context = {
        'cliente': cliente,
        'facturas': facturas
    }
    return render(request, 'facturacion/cliente_detalle.html', context)


@login_required
def cliente_crear(request):
    """Vista para crear nuevo cliente"""
    if request.method == 'POST':
        form = ClienteForm(request.POST)
        try:
            if form.is_valid():
                with transaction.atomic():
                    cliente = form.save()
                messages.success(request, f'Cliente "{escape(cliente.nombre)}" creado exitosamente')
                return redirect('facturacion:cliente_detalle', pk=cliente.pk)
            else:
                messages.error(request, 'Por favor corrija los errores en el formulario')
        except Exception as e:
            logger.error(f'Error creando cliente: {e}')
            messages.error(request, 'Error interno al crear el cliente')
    else:
        form = ClienteForm()
    
    context = {'form': form, 'accion': 'Crear'}
    return render(request, 'facturacion/cliente_form.html', context)


@login_required
def cliente_editar(request, pk):
    """Vista para editar cliente existente"""
    try:
        cliente = get_object_or_404(Cliente, pk=pk, activo=True)
        
        if request.method == 'POST':
            form = ClienteForm(request.POST, instance=cliente)
            try:
                if form.is_valid():
                    with transaction.atomic():
                        cliente = form.save()
                    messages.success(request, f'Cliente "{escape(cliente.nombre)}" actualizado exitosamente')
                    return redirect('facturacion:cliente_detalle', pk=cliente.pk)
                else:
                    messages.error(request, 'Por favor corrija los errores en el formulario')
            except Exception as e:
                logger.error(f'Error editando cliente {pk}: {e}')
                messages.error(request, 'Error interno al actualizar el cliente')
        else:
            form = ClienteForm(instance=cliente)
        
        context = {
            'form': form,
            'cliente': cliente,
            'accion': 'Editar'
        }
        return render(request, 'facturacion/cliente_form.html', context)
    except Exception as e:
        logger.error(f'Error accediendo a cliente {pk}: {e}')
        messages.error(request, 'Cliente no encontrado')
        return redirect('facturacion:cliente_lista')


@login_required
def cliente_eliminar(request, pk):
    """Vista para eliminar cliente (soft delete)"""
    cliente = get_object_or_404(Cliente, pk=pk)
    
    # Verificar si tiene facturas asociadas
    facturas_activas = cliente.facturas.filter(activo=True).count()
    
    if request.method == 'POST':
        if facturas_activas > 0:
            messages.error(
                request,
                f'No se puede eliminar el cliente "{cliente.nombre}" porque tiene {facturas_activas} factura(s) asociada(s)'
            )
            return redirect('facturacion:cliente_lista')
        
        nombre = cliente.nombre
        cliente.activo = False
        cliente.save()
        messages.success(request, f'Cliente "{nombre}" eliminado exitosamente')
        return redirect('facturacion:cliente_lista')
    
    context = {
        'cliente': cliente,
        'facturas_activas': facturas_activas
    }
    return render(request, 'facturacion/cliente_confirmar_eliminar.html', context)

# ==================== CRUD PRODUCTOS ====================

@login_required
def producto_lista(request):
    """Vista de listado de productos"""
    productos = Producto.objects.filter(activo=True).order_by('nombre')
    paginator = Paginator(productos, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'facturacion/producto_lista.html', {'page_obj': page_obj})


@login_required
def producto_crear(request):
    """Vista para crear producto"""
    if request.method == 'POST':
        form = ProductoForm(request.POST)
        if form.is_valid():
            producto = form.save()
            messages.success(request, f'Producto "{producto.nombre}" creado exitosamente')
            return redirect('facturacion:producto_lista')
    else:
        form = ProductoForm()
    return render(request, 'facturacion/producto_form.html', {'form': form, 'accion': 'Crear'})


@login_required
def producto_editar(request, pk):
    """Vista para editar producto"""
    producto = get_object_or_404(Producto, pk=pk)
    if request.method == 'POST':
        form = ProductoForm(request.POST, instance=producto)
        if form.is_valid():
            form.save()
            messages.success(request, f'Producto "{producto.nombre}" actualizado')
            return redirect('facturacion:producto_lista')
    else:
        form = ProductoForm(instance=producto)
    return render(request, 'facturacion/producto_form.html', {'form': form, 'accion': 'Editar', 'producto': producto})


@login_required
def producto_eliminar(request, pk):
    """Vista para eliminar producto"""
    producto = get_object_or_404(Producto, pk=pk)
    if request.method == 'POST':
        producto.activo = False
        producto.save()
        messages.success(request, f'Producto "{producto.nombre}" eliminado')
        return redirect('facturacion:producto_lista')
    return render(request, 'facturacion/producto_confirmar_eliminar.html', {'producto': producto})


def es_staff_o_superuser(user):
    """Helper para verificar permisos de administración"""
    return user.is_staff or user.is_superuser


@login_required
@user_passes_test(es_staff_o_superuser, login_url='facturacion:dashboard')
def factura_añadir_timbrado(request, pk):
    """Vista para que administradores añadan timbrado"""
    try:
        factura = get_object_or_404(Factura, pk=pk, activo=True)
        
        if factura.estado == 'ANULADA':
            messages.error(request, 'No se puede timbrar una factura anulada')
            return redirect('facturacion:factura_detalle', pk=pk)
        
        if request.method == 'POST':
            form = TimbradoForm(request.POST, instance=factura)
            
            try:
                if form.is_valid():
                    with transaction.atomic():
                        factura = form.save(commit=False)
                        if not factura.timbrado_por:
                            factura.timbrado_por = request.user
                            factura.timbrado_fecha_registro = timezone.now()
                        factura.save()
                        
                    messages.success(request, f'Timbrado añadido a factura {escape(factura.numero_factura)}')
                    return redirect('facturacion:factura_detalle', pk=factura.pk)
                else:
                    messages.error(request, 'Corrija los errores en el formulario')
            except Exception as e:
                logger.error(f'Error añadiendo timbrado a factura {pk}: {e}')
                messages.error(request, 'Error interno al añadir timbrado')
        else:
            form = TimbradoForm(instance=factura)
        
        context = {'factura': factura, 'form': form}
        return render(request, 'facturacion/factura_timbrado_form.html', context)
    except Exception as e:
        logger.error(f'Error accediendo a factura para timbrado {pk}: {e}')
        messages.error(request, 'Factura no encontrada')
        return redirect('facturacion:factura_lista')


@login_required
@user_passes_test(es_staff_o_superuser, login_url='facturacion:dashboard')
def timbrado_eliminar(request, pk):
    """Vista para eliminar configuración de timbrado con confirmación"""
    try:
        config = get_object_or_404(TimbradoConfig, pk=pk)
        
        if request.method == 'POST':
            confirmacion = request.POST.get('confirmacion', '').strip().upper()
            
            if confirmacion == 'ELIMINAR':
                with transaction.atomic():
                    config.delete()
                messages.success(request, 'Configuración de timbrado eliminada exitosamente')
                return redirect('facturacion:timbrado_configurar')
            else:
                messages.error(request, 'Debe escribir "ELIMINAR" para confirmar')
        
        context = {'config': config}
        return render(request, 'facturacion/timbrado_confirmar_eliminar.html', context)
    except Exception as e:
        logger.error(f'Error eliminando configuración de timbrado: {e}')
        messages.error(request, 'Error al eliminar la configuración')
        return redirect('facturacion:timbrado_configurar')


@login_required
def reportes_ventas(request):
    """Vista de reportes de ventas con filtros"""
    facturas = Factura.objects.filter(activo=True).select_related('cliente')
    
    # Filtros
    fecha_desde = request.GET.get('fecha_desde')
    fecha_hasta = request.GET.get('fecha_hasta')
    estado = request.GET.get('estado')
    
    if fecha_desde:
        try:
            fecha_desde = date.fromisoformat(fecha_desde)
            facturas = facturas.filter(fecha_emision__gte=fecha_desde)
        except ValueError:
            fecha_desde = None
    
    if fecha_hasta:
        try:
            fecha_hasta = date.fromisoformat(fecha_hasta)
            facturas = facturas.filter(fecha_emision__lte=fecha_hasta)
        except ValueError:
            fecha_hasta = None
    
    if estado:
        facturas = facturas.filter(estado=estado)
    
    # Estadísticas
    total_facturas = facturas.count()
    total_monto = facturas.aggregate(total=Sum('total'))['total'] or Decimal('0')
    facturas_pagadas = facturas.filter(estado='PAGADA').count()
    monto_pagado = facturas.filter(estado='PAGADA').aggregate(total=Sum('total'))['total'] or Decimal('0')
    facturas_pendientes = facturas.filter(estado='PENDIENTE').count()
    monto_pendiente = facturas.filter(estado='PENDIENTE').aggregate(total=Sum('total'))['total'] or Decimal('0')
    facturas_anuladas = facturas.filter(estado='ANULADA').count()
    
    context = {
        'facturas': facturas[:50],
        'total_facturas': total_facturas,
        'total_monto': total_monto,
        'facturas_pagadas': facturas_pagadas,
        'monto_pagado': monto_pagado,
        'facturas_pendientes': facturas_pendientes,
        'monto_pendiente': monto_pendiente,
        'facturas_anuladas': facturas_anuladas,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'estado': estado,
    }
    return render(request, 'facturacion/reportes_ventas.html', context)


@login_required
def reportes_ventas_pdf(request):
    """Genera PDF del reporte de ventas"""
    from django.http import HttpResponse
    from .utils import generar_reporte_ventas
    
    try:
        facturas = Factura.objects.filter(activo=True).select_related('cliente')
        
        fecha_desde = request.GET.get('fecha_desde')
        fecha_hasta = request.GET.get('fecha_hasta')
        estado = request.GET.get('estado')
        
        if fecha_desde:
            try:
                fecha_desde = date.fromisoformat(fecha_desde)
                facturas = facturas.filter(fecha_emision__gte=fecha_desde)
            except ValueError:
                fecha_desde = None
        
        if fecha_hasta:
            try:
                fecha_hasta = date.fromisoformat(fecha_hasta)
                facturas = facturas.filter(fecha_emision__lte=fecha_hasta)
            except ValueError:
                fecha_hasta = None
        
        if estado:
            facturas = facturas.filter(estado=estado)
        
        pdf_buffer = generar_reporte_ventas(facturas, fecha_desde, fecha_hasta)
        
        response = HttpResponse(pdf_buffer, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="reporte_ventas.pdf"'
        return response
    except Exception as e:
        logger.error(f'Error generando reporte de ventas PDF: {e}')
        messages.error(request, 'Error al generar el reporte')
        return redirect('facturacion:reportes_ventas')


# ==================== API ENDPOINTS ====================

@login_required
def api_producto_precio(request, pk):
    """API endpoint para obtener precio de producto"""
    from django.http import JsonResponse
    try:
        producto = get_object_or_404(Producto, pk=pk, activo=True)
        return JsonResponse({
            'id': producto.id,
            'nombre': producto.nombre,
            'precio': float(producto.precio)
        })
    except Exception as e:
        logger.error(f'Error obteniendo precio de producto {pk}: {e}')
        return JsonResponse({'error': 'Producto no encontrado'}, status=404)


@login_required
@user_passes_test(es_staff_o_superuser, login_url='facturacion:dashboard')
def timbrado_configurar(request):
    """Vista para configurar el timbrado global del sistema"""
    try:
        config_activa = TimbradoConfig.get_activo()
        hoy = timezone.now().date()
        
        # Verificar si la config activa ha expirado
        config_expirada = config_activa and config_activa.fecha_vencimiento < hoy
        requiere_confirmacion = config_activa and not config_expirada
        
        if request.method == 'POST':
            if config_activa and not config_expirada:
                # Requiere confirmación para reemplazar
                form = TimbradoConfigForm(request.POST, requiere_confirmacion=True)
            else:
                form = TimbradoConfigForm(request.POST)
            
            if form.is_valid():
                try:
                    with transaction.atomic():
                        # Desactivar configuración anterior si existe
                        if config_activa:
                            config_activa.activo = False
                            config_activa.save()
                        
                        # Crear nueva configuración
                        nueva_config = form.save(commit=False)
                        nueva_config.activo = True
                        nueva_config.creado_por = request.user
                        nueva_config.save()
                        
                    messages.success(request, 'Configuración de timbrado guardada exitosamente')
                    return redirect('facturacion:timbrado_configurar')
                except Exception as e:
                    logger.error(f'Error guardando configuración de timbrado: {e}')
                    messages.error(request, 'Error al guardar la configuración')
            else:
                messages.error(request, 'Corrija los errores en el formulario')
        else:
            if config_activa and not config_expirada:
                form = TimbradoConfigForm(requiere_confirmacion=True)
            else:
                form = TimbradoConfigForm()
        
        context = {
            'form': form,
            'config_activa': config_activa,
            'config_expirada': config_expirada,
            'requiere_confirmacion': requiere_confirmacion
        }
        return render(request, 'facturacion/timbrado_config_form.html', context)
    except Exception as e:
        logger.error(f'Error en timbrado_configurar: {e}')
        messages.error(request, 'Error interno del servidor')
        return redirect('facturacion:dashboard')