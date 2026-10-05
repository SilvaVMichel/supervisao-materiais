from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group
from logistica.permissions import ROLES
class Command(BaseCommand):
    help='Cria os perfis do sistema; não cria usuários ou senhas.'
    def handle(self,*args,**kwargs):
        for role in ROLES: Group.objects.get_or_create(name=role)
        self.stdout.write(self.style.SUCCESS('Perfis configurados.'))
