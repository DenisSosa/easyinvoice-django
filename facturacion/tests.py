from django.test import TestCase
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from .models import Cliente, Factura
from datetime import date, timedelta
import os
from django.conf import settings

class FacturaAnularCaptchaTest(TestCase):
    """Tests para anulación de factura con captcha"""
    
    def setUp(self):
        """Configuración inicial para los tests"""
        # Crear usuario de prueba
        self.test_username = os.getenv('TEST_USERNAME', 'test_user_' + str(os.getpid()))
        self.test_password = os.getenv('TEST_PASSWORD', 'test_pass_' + str(os.getpid()))
        
        self.user = User.objects.create_user(
            username=self.test_username,
            password=self.test_password
        )
        self.client = Client()
        self.client.login(username=self.test_username, password=self.test_password)
        
        # Crear cliente y factura de prueba
        cliente = Cliente.objects.create(
            nombre="Cliente Test",
            ruc_ci="12345678-9",
            direccion="Dirección Test",
            telefono="0981123456"
        )
        
        self.factura = Factura.objects.create(
            numero_factura=Factura.generar_numero_factura(),
            cliente=cliente,
            fecha_emision=date.today(),
            estado='PENDIENTE'
        )
    
    def test_captcha_correcto_anula_factura(self):
        """Test: Captcha correcto debe anular la factura"""
        url = reverse('facturacion:factura_anular', kwargs={'pk': self.factura.pk})
        
        # GET para obtener el captcha
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        # Obtener valores del captcha de la sesión
        session = self.client.session
        captcha_a = session['captcha_a']
        captcha_b = session['captcha_b']
        respuesta_correcta = captcha_a + captcha_b
        
        # POST con respuesta correcta
        response = self.client.post(url, {
            'captcha_respuesta': respuesta_correcta
        })
        
        # Verificar redirección y que la factura fue anulada
        self.assertEqual(response.status_code, 302)
        self.factura.refresh_from_db()
        self.assertEqual(self.factura.estado, 'ANULADA')
    
    def test_captcha_incorrecto_no_anula_factura(self):
        """Test: Captcha incorrecto NO debe anular la factura"""
        url = reverse('facturacion:factura_anular', kwargs={'pk': self.factura.pk})
        
        # GET para obtener el captcha
        response = self.client.get(url)
        
        # POST con respuesta incorrecta
        response = self.client.post(url, {
            'captcha_respuesta': 99999  # Respuesta incorrecta
        })
        
        # Verificar que la factura NO fue anulada
        self.factura.refresh_from_db()
        self.assertEqual(self.factura.estado, 'PENDIENTE')
        
        # Verificar que se muestra mensaje de error
        messages = list(response.context['messages'])
        self.assertTrue(any('incorrecto' in str(m) for m in messages))
    
    def test_factura_ya_anulada_no_permite_anular(self):
        """Test: No se puede anular una factura ya anulada"""
        self.factura.estado = 'ANULADA'
        self.factura.save()
        
        url = reverse('facturacion:factura_anular', kwargs={'pk': self.factura.pk})
        response = self.client.get(url)
        
        # Debe redirigir y mostrar error
        self.assertEqual(response.status_code, 302)


class LoginSeparadoTest(TestCase):
    """Tests para login separado de usuarios y administradores"""
    
    def setUp(self):
        """Configuración inicial para los tests"""
        self.client = Client()
        
        # Crear usuario normal
        self.user_normal = User.objects.create_user(
            username='usuario_normal',
            password='pass123'
        )
        
        # Crear usuario administrador
        self.user_admin = User.objects.create_user(
            username='admin_user',
            password='admin123',
            is_staff=True
        )
    
    def test_login_usuario_no_admin_success(self):
        """Test: Usuario normal puede loguearse en /login/"""
        url = reverse('facturacion:login')
        response = self.client.post(url, {
            'username': 'usuario_normal',
            'password': 'pass123'
        })
        
        # Debe redirigir al dashboard
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('facturacion:dashboard'))
        
        # Verificar que el usuario está autenticado
        self.assertTrue(response.wsgi_request.user.is_authenticated)
    
    def test_login_usuario_admin_redirige_a_login_admin(self):
        """Test: Admin intentando login en /login/ es redirigido a /login-admin/"""
        url = reverse('facturacion:login')
        response = self.client.post(url, {
            'username': 'admin_user',
            'password': 'admin123'
        })
        
        # Debe redirigir al login admin
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('facturacion:login_admin'))
    
    def test_login_admin_only_success(self):
        """Test: Usuario staff puede loguearse en /login-admin/"""
        url = reverse('facturacion:login_admin')
        response = self.client.post(url, {
            'username': 'admin_user',
            'password': 'admin123'
        })
        
        # Debe redirigir al dashboard
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('facturacion:dashboard'))
        
        # Verificar que el usuario está autenticado
        self.assertTrue(response.wsgi_request.user.is_authenticated)
    
    def test_login_admin_usuario_normal_denegado(self):
        """Test: Usuario normal NO puede loguearse en /login-admin/"""
        url = reverse('facturacion:login_admin')
        response = self.client.post(url, {
            'username': 'usuario_normal',
            'password': 'pass123'
        })
        
        # Debe redirigir al login normal
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('facturacion:login'))
        
        # Verificar mensaje de error
        messages = list(response.wsgi_request._messages)
        self.assertTrue(any('Acceso denegado' in str(m) for m in messages))


class TimbradoConfigTest(TestCase):
    """Tests para configuración de timbrado global"""
    
    def setUp(self):
        """Configuración inicial"""
        self.user_admin = User.objects.create_user(
            username='admin_test',
            password='admin123',
            is_staff=True
        )
        self.client = Client()
        self.client.login(username='admin_test', password='admin123')
    
    def test_timbrado_config_singleton(self):
        """Test: Solo puede existir una configuración activa"""
        from .models import TimbradoConfig
        from django.core.exceptions import ValidationError
        
        # Crear primera configuración
        config1 = TimbradoConfig.objects.create(
            establecimiento='001',
            punto_expedicion='001',
            fecha_inicio=date.today(),
            fecha_vencimiento=date.today() + timedelta(days=365),
            activo=True,
            creado_por=self.user_admin
        )
        
        # Intentar crear segunda configuración activa debe fallar
        config2 = TimbradoConfig(
            establecimiento='002',
            punto_expedicion='001',
            fecha_inicio=date.today(),
            fecha_vencimiento=date.today() + timedelta(days=365),
            activo=True
        )
        
        with self.assertRaises(ValidationError):
            config2.full_clean()
    
    def test_generar_numero_con_timbrado(self):
        """Test: Generar números de factura con formato paraguayo"""
        from .models import TimbradoConfig
        
        # Crear configuración de timbrado
        TimbradoConfig.objects.create(
            establecimiento='001',
            punto_expedicion='001',
            fecha_inicio=date.today(),
            fecha_vencimiento=date.today() + timedelta(days=365),
            activo=True,
            creado_por=self.user_admin
        )
        
        # Crear cliente
        cliente = Cliente.objects.create(
            nombre="Cliente Test",
            ruc_ci="12345678-9",
            direccion="Dirección Test",
            telefono="0981123456"
        )
        
        # Crear primera factura
        factura1 = Factura.objects.create(
            numero_factura=Factura.generar_numero_factura(),
            cliente=cliente,
            fecha_emision=date.today(),
            estado='PENDIENTE'
        )
        
        self.assertEqual(factura1.numero_factura, '001-001-00000001')
        
        # Crear segunda factura
        factura2 = Factura.objects.create(
            numero_factura=Factura.generar_numero_factura(),
            cliente=cliente,
            fecha_emision=date.today(),
            estado='PENDIENTE'
        )
        
        self.assertEqual(factura2.numero_factura, '001-001-00000002')
    
    def test_fallback_sin_timbrado(self):
        """Test: Sin configuración de timbrado, usar formato antiguo FAC-XXXXXX"""
        # No crear TimbradoConfig
        
        cliente = Cliente.objects.create(
            nombre="Cliente Test",
            ruc_ci="12345678-9",
            direccion="Dirección Test",
            telefono="0981123456"
        )
        
        factura = Factura.objects.create(
            numero_factura=Factura.generar_numero_factura(),
            cliente=cliente,
            fecha_emision=date.today(),
            estado='PENDIENTE'
        )
        
        # Debe empezar con FAC-
        self.assertTrue(factura.numero_factura.startswith('FAC-'))


# ==========================================
# COMANDO PARA EJECUTAR TESTS
# ==========================================
# python manage.py test facturacion.tests.FacturaAnularCaptchaTest
# python manage.py test facturacion.tests.LoginSeparadoTest
# python manage.py test facturacion.tests.TimbradoConfigTest
# Create your tests here.
