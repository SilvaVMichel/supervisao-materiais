from .permissions import has
def roles(request):
    return {'can_admin':has(request.user),'can_request':has(request.user,'Supervisor'),'can_stock':has(request.user,'Almoxarifado'),'can_buy':has(request.user,'Compras'),'can_approve':has(request.user,'Gestor'),'can_ship':has(request.user,'Logística'),'can_receive':has(request.user,'Supervisor','Almoxarifado'),'role_names':', '.join(request.user.groups.values_list('name',flat=True)) if request.user.is_authenticated else ''}
