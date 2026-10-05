from datetime import timedelta
from decimal import Decimal
from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User, Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from .models import Project, Order, Item, Lot, Dispatch, Event
from .services import act
from .permissions import ROLES

@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class WorkflowTests(TestCase):
    def setUp(self):
        self.users={}
        for n,role in enumerate(ROLES):
            group=Group.objects.create(name=role)
            u=User.objects.create_user(username=f'user{n}',password='Teste-forte-273!')
            u.groups.add(group); self.users[role]=u
        self.project=Project.objects.create(name='Obra de teste',address='Rua de teste, 100')
        self.project.supervisors.add(self.users['Supervisor'])
        self.order=Order.objects.create(project=self.project,author=self.users['Supervisor'],due_date=timezone.localdate())
        self.item=Item.objects.create(order=self.order,name='Cimento 50 kg',quantity=20,unit='saco')
    def do(self,role,action,**data):
        self.order.refresh_from_db()
        act(self.users[role],self.order.pk,dict(version=self.order.version,action=action,**data))
    def now(self): return timezone.now().isoformat()
    def purchase(self,dest='depot'):
        self.do('Almoxarifado','check',item=self.item.pk,quantidade='8')
        self.item.refresh_from_db(); p=self.item.purchase
        self.do('Compras','quote',purchase=p.pk,fornecedor='Fornecedor teste',**{'preço':'35.50','frete':'20.00','previsao':timezone.localdate().isoformat(),'destino':dest})
        return p
    def buy(self,dest='depot'):
        p=self.purchase(dest)
        self.do('Gestor','approve',purchase=p.pk)
        self.do('Compras','buy',purchase=p.pk,referencia='OC 123')
        return p
    def test_full_split_depot_partial_delivery(self):
        p=self.buy(); p.refresh_from_db(); self.assertEqual(p.total,Decimal('446.00'))
        self.do('Almoxarifado','arrive',purchase=p.pk,quantidade='12',data_hora=self.now())
        for lot in Lot.objects.filter(item=self.item):
            self.do('Almoxarifado','pack',lot=lot.pk,quantidade=str(lot.quantity))
            self.do('Logística','ship',lot=lot.pk,quantidade=str(lot.quantity),data_hora=self.now(),transportador='Motorista teste',previsao=timezone.localdate().isoformat())
            d=Dispatch.objects.get(lot=lot)
            self.do('Supervisor','receive',dispatch=d.pk,quantidade='1',data_hora=self.now(),recebedor='Encarregado')
            self.assertFalse(Order.objects.get(pk=self.order.pk).complete)
            self.do('Supervisor','receive',dispatch=d.pk,quantidade=str(lot.quantity-1),data_hora=self.now(),recebedor='Encarregado')
        self.assertEqual(Item.objects.get(pk=self.item.pk).delivered,20)
        self.assertTrue(Order.objects.get(pk=self.order.pk).complete)
        self.assertEqual(Event.objects.filter(order=self.order).count(),13)
    def test_direct_supplier_route(self):
        p=self.buy('site')
        with self.assertRaises(ValidationError): self.do('Almoxarifado','arrive',purchase=p.pk,quantidade='12',data_hora=self.now())
        self.do('Compras','supplier_send',purchase=p.pk,quantidade='12',data_hora=self.now(),transportador='Fornecedor',previsao=timezone.localdate().isoformat())
        d=Dispatch.objects.get(lot__purchase=p)
        self.do('Supervisor','receive',dispatch=d.pk,quantidade='12',data_hora=self.now(),recebedor='Supervisor')
        self.assertEqual(Item.objects.get(pk=self.item.pk).delivered,12)
        self.assertFalse(Lot.objects.filter(purchase=p,source='purchase').exists())
    def test_cannot_buy_without_approval_or_approve_as_buyer(self):
        p=self.purchase()
        with self.assertRaises(ValidationError): self.do('Compras','buy',purchase=p.pk,referencia='x')
        with self.assertRaises(PermissionDenied): self.do('Compras','approve',purchase=p.pk)
        p.refresh_from_db(); self.assertEqual(p.state,'pending')
    def test_requote_invalidates_approval(self):
        p=self.purchase(); self.do('Gestor','approve',purchase=p.pk)
        self.do('Compras','quote',purchase=p.pk,fornecedor='Outro',**{'preço':'36','frete':'0','previsao':timezone.localdate().isoformat(),'destino':'site'})
        p.refresh_from_db(); self.assertEqual(p.state,'pending'); self.assertIsNone(p.approved_by)
        with self.assertRaises(ValidationError): self.do('Compras','buy',purchase=p.pk,referencia='x')
    def test_rejection_returns_to_quote(self):
        p=self.purchase()
        self.do('Gestor','reject',purchase=p.pk,motivo='Negociar preço')
        p.refresh_from_db(); self.assertEqual(p.state,'draft')
    def test_duplicate_and_stale_submission_rejected(self):
        self.do('Almoxarifado','check',item=self.item.pk,quantidade='8')
        with self.assertRaises(ValidationError): act(self.users['Almoxarifado'],self.order.pk,{'action':'check','version':0,'item':self.item.pk,'quantidade':'8'})
        self.assertEqual(Lot.objects.count(),1)
    def test_quantity_bounds_and_invalid_numbers(self):
        for qty in ['21','-1','NaN','Infinity','0.0001']:
            with self.assertRaises(ValidationError): self.do('Almoxarifado','check',item=self.item.pk,quantidade=qty)
        self.item.refresh_from_db(); self.assertFalse(self.item.checked)
        self.assertFalse(Event.objects.exists())
    def test_cannot_ship_unpacked_and_overreceive(self):
        self.do('Almoxarifado','check',item=self.item.pk,quantidade='20'); lot=Lot.objects.get()
        with self.assertRaises(ValidationError): self.do('Logística','ship',lot=lot.pk,quantidade='1',data_hora=self.now(),transportador='x',previsao=timezone.localdate().isoformat())
        self.do('Almoxarifado','pack',lot=lot.pk,quantidade='10')
        self.do('Logística','ship',lot=lot.pk,quantidade='10',data_hora=self.now(),transportador='x',previsao=timezone.localdate().isoformat())
        d=Dispatch.objects.get()
        with self.assertRaises(ValidationError): self.do('Supervisor','receive',dispatch=d.pk,quantidade='11',data_hora=self.now(),recebedor='x')
        self.do('Supervisor','receive',dispatch=d.pk,quantidade='10',data_hora=self.now(),recebedor='x')
        with self.assertRaises(ValidationError): self.do('Supervisor','receive',dispatch=d.pk,quantidade='1',data_hora=self.now(),recebedor='x')
    def test_unassigned_supervisor_cannot_access_order(self):
        other=User.objects.create_user(username='outro'); other.groups.add(Group.objects.get(name='Supervisor'))
        self.client.force_login(other,backend='django.contrib.auth.backends.ModelBackend')
        self.assertEqual(self.client.get(f'/pedidos/{self.order.pk}/').status_code,404)
        self.assertNotContains(self.client.get('/'),self.order.code)
    def test_routes_render_for_admin_all_stages(self):
        self.client.force_login(self.users['Administrador'],backend='django.contrib.auth.backends.ModelBackend')
        for url in ['/','/obras/','/equipe/','/historico/','/pedidos/novo/','/senha/',f'/equipe/{self.users["Gestor"].pk}/']:
            self.assertEqual(self.client.get(url).status_code,200,url)
        self.assertEqual(self.client.get(f'/pedidos/{self.order.pk}/').status_code,200)
        p=self.buy(); self.do('Almoxarifado','arrive',purchase=p.pk,quantidade='12',data_hora=self.now())
        self.assertEqual(self.client.get(f'/pedidos/{self.order.pk}/').status_code,200)
    def test_login_required_and_csrf(self):
        self.assertEqual(self.client.get('/').status_code,302)
        c=Client(enforce_csrf_checks=True); c.force_login(self.users['Administrador'],backend='django.contrib.auth.backends.ModelBackend')
        self.assertEqual(c.post('/obras/',{'name':'Não deve criar'}).status_code,403)
        self.assertEqual(self.client.get('/entrar/').status_code,200)
    def test_new_order_form_and_scope(self):
        self.client.force_login(self.users['Supervisor'],backend='django.contrib.auth.backends.ModelBackend')
        data={'project':self.project.pk,'due_date':timezone.localdate().isoformat(),'notes':'Teste','items-TOTAL_FORMS':'4','items-INITIAL_FORMS':'0','items-MIN_NUM_FORMS':'1','items-MAX_NUM_FORMS':'100','items-0-name':'Argamassa','items-0-quantity':'3','items-0-unit':'saco','items-1-name':'','items-1-quantity':'','items-1-unit':'un','items-2-name':'','items-2-quantity':'','items-2-unit':'un','items-3-name':'','items-3-quantity':'','items-3-unit':'un'}
        self.assertEqual(self.client.post('/pedidos/novo/',data).status_code,302)
        self.assertEqual(Order.objects.count(),2)
        forbidden=Project.objects.create(name='Outra',address='Outro endereço'); data['project']=forbidden.pk
        self.assertEqual(self.client.post('/pedidos/novo/',data).status_code,200)
        self.assertEqual(Order.objects.count(),2)
    def test_invalid_arrival_rolls_back(self):
        p=self.buy('site')
        with self.assertRaises(ValidationError): self.do('Compras','supplier_send',purchase=p.pk,quantidade='12',data_hora=self.now(),transportador='',previsao=timezone.localdate().isoformat())
        self.assertEqual(p.lots.count(),0)
    def test_cross_order_item_rejected(self):
        other=Order.objects.create(project=self.project,author=self.users['Supervisor'],due_date=timezone.localdate())
        item=Item.objects.create(order=other,name='Outro',quantity=2,unit='un')
        with self.assertRaises(Item.DoesNotExist): self.do('Almoxarifado','check',item=item.pk,quantidade='1')
    def test_only_admin_manages_accounts(self):
        self.client.force_login(self.users['Gestor'],backend='django.contrib.auth.backends.ModelBackend')
        self.assertEqual(self.client.get('/equipe/').status_code,403)
        self.assertEqual(self.client.get('/obras/').status_code,403)
    def test_login_rate_limit(self):
        for _ in range(6): response=self.client.post('/entrar/',{'username':'user0','password':'wrong'})
        self.assertEqual(response.status_code,429)

class BootstrapTests(TestCase):
    def test_initial_admin_is_created_once_and_never_reset(self):
        import os
        from unittest.mock import patch
        from django.core.management import call_command
        from io import StringIO
        env={'INITIAL_ADMIN_USERNAME':'admin_teste','INITIAL_ADMIN_PASSWORD':'Senha-inicial-7429!'}
        with patch.dict(os.environ,env):
            output=StringIO(); call_command('bootstrap_admin',stdout=output)
            u=User.objects.get(username='admin_teste')
            self.assertTrue(u.is_superuser)
            self.assertTrue(u.check_password(env['INITIAL_ADMIN_PASSWORD']))
            self.assertNotIn(env['INITIAL_ADMIN_PASSWORD'],output.getvalue())
            u.set_password('Nova-senha-9274!');u.save()
            call_command('bootstrap_admin',stdout=StringIO())
            u.refresh_from_db();self.assertTrue(u.check_password('Nova-senha-9274!'))
    def test_missing_bootstrap_credentials_fail_closed(self):
        import os
        from unittest.mock import patch
        from django.core.management import call_command,CommandError
        with patch.dict(os.environ,{'INITIAL_ADMIN_USERNAME':'','INITIAL_ADMIN_PASSWORD':''}):
            with self.assertRaises(CommandError):call_command('bootstrap_admin')
        self.assertFalse(User.objects.exists())
