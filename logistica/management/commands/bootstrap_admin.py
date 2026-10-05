import os
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User, Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

class Command(BaseCommand):
    help='Cria o primeiro administrador por variáveis protegidas, sem imprimir senha. Não altera contas existentes.'
    def handle(self,*args,**kwargs):
        username=os.getenv('INITIAL_ADMIN_USERNAME','').strip()
        password=os.getenv('INITIAL_ADMIN_PASSWORD','')
        with transaction.atomic():
            # PostgreSQL: serializa a inicialização mesmo se dois processos iniciarem juntos.
            from django.db import connection
            if connection.vendor=='postgresql':
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_advisory_xact_lock(%s)',[784015209])
            if User.objects.exists():
                self.stdout.write('Usuários existentes preservados. Inicialização de conta ignorada.')
                return
            if not username or not password:
                raise CommandError('Configure INITIAL_ADMIN_USERNAME e INITIAL_ADMIN_PASSWORD no painel da hospedagem para criar o primeiro administrador.')
            user=User(username=username,is_superuser=True,is_staff=True,first_name='Administrador')
            try:
                user.full_clean(exclude=['password'])
                validate_password(password,user=user)
            except ValidationError as exc:
                raise CommandError('Configuração inicial inválida: '+' '.join(exc.messages)) from None
            user.set_password(password); user.save()
            group,_=Group.objects.get_or_create(name='Administrador');user.groups.add(group)
        self.stdout.write(self.style.SUCCESS('Administrador inicial criado. Remova INITIAL_ADMIN_PASSWORD e INITIAL_ADMIN_USERNAME do painel após validar o acesso.'))
