import requests
import json
import base64
import os
import time
from datetime import datetime


def _request_with_retry(method, url, max_retries=3, backoff_factor=2, **kwargs):
    """
    Ejecuta una petición HTTP con reintentos automáticos para errores 429 (rate limiting).
    
    Args:
        method: Método HTTP ('GET', 'POST', etc.)
        url: URL de la petición
        max_retries: Número máximo de reintentos (default: 3)
        backoff_factor: Factor de multiplicación para el tiempo de espera (default: 2)
        **kwargs: Argumentos adicionales para requests (headers, json, files, etc.)
    
    Returns:
        Response object de requests
    
    Raises:
        HTTPError: Si después de todos los reintentos sigue fallando
    """
    for attempt in range(max_retries + 1):
        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and attempt < max_retries:
                wait_time = backoff_factor ** attempt
                print(f"      ⚠️  Rate limit alcanzado (429), reintentando en {wait_time}s... (intento {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
            else:
                raise
    return response


class PowerBIObjectManager:
    """Clase para gestionar la creación de objetos en Power BI (Workspaces, Folders, Lakehouses)"""
    
    def __init__(self, bearer_token):
        """
        Inicializa el gestor con el token de autenticación
        
        Args:
            bearer_token: Token de acceso para la API de Power BI
        """
        self.bearer_token = bearer_token
        self.headers = {
            'Authorization': f'Bearer {bearer_token}',
            'Content-Type': 'application/json'
        }
        self.base_url = "https://api.powerbi.com/v1.0/myorg"
        self.fabric_url = "https://api.fabric.microsoft.com/v1"
        self.created_objects = []  # Lista de objetos creados
    
    def _find_workspace_by_name(self, workspace_name):
        """Busca un workspace por nombre exacto y devuelve su ID, o None si no existe."""
        url = f"{self.base_url}/groups"
        try:
            response = requests.get(url, headers=self.headers, params={'$filter': f"name eq '{workspace_name}'"})
            response.raise_for_status()
            for group in response.json().get('value', []):
                if group.get('name') == workspace_name:
                    return group.get('id')
        except Exception:
            pass
        return None

    def _find_lakehouse_by_name(self, workspace_id, name):
        """Busca un lakehouse por nombre exacto en un workspace y devuelve su ID, o None si no existe."""
        url = f"{self.fabric_url}/workspaces/{workspace_id}/lakehouses"
        try:
            while url:
                response = requests.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                for item in data.get('value', []):
                    if item.get('displayName') == name:
                        return item.get('id')
                url = data.get('continuationUri')
        except Exception:
            pass
        return None

    def _find_item_by_name(self, workspace_id, name, item_type):
        """Busca un item Fabric por nombre y tipo en un workspace y devuelve su ID, o None si no existe."""
        url = f"{self.fabric_url}/workspaces/{workspace_id}/items"
        try:
            while url:
                response = requests.get(url, headers=self.headers, params={'type': item_type})
                response.raise_for_status()
                data = response.json()
                for item in data.get('value', []):
                    if item.get('displayName') == name:
                        return item.get('id')
                url = data.get('continuationUri')
        except Exception:
            pass
        return None

    @staticmethod
    def _is_duplicate_error(response):
        """Devuelve True si la respuesta indica que el recurso ya existe (409 o 400 con código AlreadyExists)."""
        if response.status_code == 409:
            return True
        if response.status_code == 400:
            try:
                body = response.json()
                # Estructura Power BI: {"error": {"code": "PowerBIEntityAlreadyExists"}}
                code = body.get('error', {}).get('code', '')
                if 'AlreadyExists' in code or 'AlreadyInUse' in code:
                    return True
                # Estructura Fabric: {"errorCode": "ItemDisplayNameAlreadyInUse"}
                error_code = body.get('errorCode', '')
                if 'AlreadyExists' in error_code or 'AlreadyInUse' in error_code:
                    return True
            except Exception:
                pass
        return False

    def _has_sp_workspace_role(self, workspace_id: str, sp_id: str, role: str) -> bool:
        """Returns True if service principal sp_id already has the given role in the workspace."""
        url = f"{self.base_url}/groups/{workspace_id}/users"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            for user in response.json().get("value", []):
                if (user.get("identifier", "").lower() == sp_id.lower()
                        and user.get("groupUserAccessRight") == role):
                    return True
        except Exception:
            pass
        return False

    def _is_workspace_admin(self, workspace_id, email):
        """Devuelve True si el email ya tiene rol Admin en el workspace, False en cualquier otro caso."""
        url = f"{self.base_url}/groups/{workspace_id}/users"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            for user in response.json().get('value', []):
                if (user.get('emailAddress', '').lower() == email.lower() and
                        user.get('groupUserAccessRight') == 'Admin'):
                    return True
        except Exception:
            pass
        return False

    def _get_workspace_folders(self, workspace_id):
        """Devuelve dict {folder_id: {name, parentFolderId}} con todas las carpetas del workspace."""
        url = f"{self.fabric_url}/workspaces/{workspace_id}/folders"
        result = {}
        try:
            while url:
                response = requests.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                for folder in data.get('value', []):
                    result[folder['id']] = {
                        'name': folder.get('displayName', ''),
                        'parentFolderId': folder.get('parentFolderId')
                    }
                url = data.get('continuationUri')
        except Exception:
            pass
        return result

    def _find_folder_by_name(self, workspace_id, name, parent_folder_id):
        """Devuelve el ID de la carpeta con ese nombre bajo ese padre, o None si no existe."""
        folders = self._get_workspace_folders(workspace_id)
        for folder_id, meta in folders.items():
            if meta['name'] == name and meta['parentFolderId'] == parent_folder_id:
                return folder_id
        return None

    def _get_workspace_items(self, workspace_id, item_type):
        """Devuelve dict {displayName: id} con todos los items del tipo indicado en el workspace."""
        url = f"{self.fabric_url}/workspaces/{workspace_id}/items"
        result = {}
        try:
            while url:
                response = requests.get(url, headers=self.headers, params={'type': item_type})
                response.raise_for_status()
                data = response.json()
                for item in data.get('value', []):
                    result[item.get('displayName')] = item.get('id')
                url = data.get('continuationUri')
        except Exception:
            pass
        return result

    def get_fabric_capacities(self):
        """
        Obtiene todas las capacidades de Fabric disponibles para el usuario
        
        Returns:
            dict: Lista de capacidades con sus detalles (ID, nombre, SKU, región, estado)
        """
        url = f"{self.fabric_url}/capacities"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            capacities = data.get('value', [])
            
            print(f"\n✓ Capacidades encontradas: {len(capacities)}")
            print("\n" + "="*80)
            
            result = []
            for idx, capacity in enumerate(capacities, 1):
                cap_id = capacity.get('id')
                cap_name = capacity.get('displayName', 'Sin nombre')
                cap_sku = capacity.get('sku', 'Desconocido')
                cap_region = capacity.get('region', 'Desconocida')
                cap_state = capacity.get('state', 'Desconocido')
                
                print(f"\n{idx}. {cap_name}")
                print(f"   ID: {cap_id}")
                print(f"   SKU: {cap_sku}")
                print(f"   Región: {cap_region}")
                print(f"   Estado: {cap_state}")
                
                result.append({
                    'index': idx,
                    'id': cap_id,
                    'displayName': cap_name,
                    'sku': cap_sku,
                    'region': cap_region,
                    'state': cap_state
                })
            
            print("\n" + "="*80)
            
            return {
                'success': True,
                'capacities': result,
                'count': len(result)
            }
            
        except requests.exceptions.RequestException as e:
            print(f"✗ Error al obtener capacidades: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"  Detalles: {e.response.text}")
            return {
                'success': False,
                'error': str(e),
                'capacities': []
            }
    
    def create_workspace(self, workspace_name, description=None, capacity_id=None):
        """
        Crea un nuevo workspace en Power BI
        
        Args:
            workspace_name: Nombre del workspace a crear
            description: Descripción opcional del workspace
            capacity_id: ID de la capacidad de Fabric donde crear el workspace
            
        Returns:
            dict: Información del workspace creado incluyendo su ID
        """
        url = f"{self.base_url}/groups"

        # Construir payload evitando valores None
        payload = {"name": workspace_name}
        if description:
            payload["description"] = description
        
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            
            workspace = response.json()
            workspace_id = workspace.get('id')
            
            print(f"✓ Workspace creado: {workspace_name}")
            print(f"  ID: {workspace_id}")

            # Asignar workspace a capacidad si se proporciona
            if capacity_id:
                assign_url = f"{self.base_url}/groups/{workspace_id}/AssignToCapacity"
                assign_payload = {
                    "capacityId": capacity_id
                }
                try:
                    response_capacity = requests.post(assign_url, headers=self.headers, json=assign_payload)
                    response_capacity.raise_for_status()
                    print(f"  Asignado a capacidad ID: {capacity_id}")
                except requests.exceptions.RequestException as e:
                    print(f"✗ Error al asignar capacidad: {e}")
                    if hasattr(e, 'response') and e.response is not None:
                        print(f"  Detalles: {e.response.text}")
                

            
            self.created_objects.append({
                'type': 'workspace',
                'id': workspace_id,
                'name': workspace_name,
                'description': description,
                'capacity_id': capacity_id
            })
            
            return {
                'success': True,
                'workspace_id': workspace_id,
                'workspace_name': workspace_name,
                'data': workspace
            }
            
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                if self._is_duplicate_error(e.response):
                    existing_id = self._find_workspace_by_name(workspace_name)
                    if existing_id:
                        print(f"ℹ️  Workspace ya existe, reutilizando: {workspace_name} (ID: {existing_id})")
                        return {
                            'success': True,
                            'workspace_id': existing_id,
                            'workspace_name': workspace_name,
                            'already_existed': True,
                            'data': {}
                        }
                print(f"  Detalles: {e.response.text}")
            print(f"✗ Error al crear workspace: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def add_workspace_admin(self, workspace_id, user_email):
        """
        Añade un usuario como administrador de un workspace
        
        Args:
            workspace_id: ID del workspace
            user_email: Email del usuario a añadir como admin
            
        Returns:
            dict: Resultado de la operación
        """
        url = f"{self.base_url}/groups/{workspace_id}/users"
        
        payload = {
            "emailAddress": user_email,
            "groupUserAccessRight": "Admin"
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            
            print(f"✓ Usuario añadido como Admin: {user_email}")
            print(f"  Workspace ID: {workspace_id}")
            
            return {
                'success': True,
                'user_email': user_email,
                'workspace_id': workspace_id
            }
            
        except requests.exceptions.RequestException as e:
            print(f"✗ Error al añadir usuario: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"  Detalles: {e.response.text}")
            return {
                'success': False,
                'error': str(e)
            }

    def add_workspace_identity_as_contributor(self, workspace_id: str, sp_id: str) -> dict:
        """Adds service principal sp_id as Contributor of workspace_id (idempotent)."""
        if self._has_sp_workspace_role(workspace_id, sp_id, "Contributor"):
            print(f"ℹ️  Workspace Identity ya es Contributor en workspace {workspace_id}")
            return {"success": True, "already_existed": True}
        url = f"{self.base_url}/groups/{workspace_id}/users"
        payload = {
            "identifier": sp_id,
            "principalType": "App",
            "groupUserAccessRight": "Contributor",
        }
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            print(f"✓ Workspace Identity añadida como Contributor en workspace {workspace_id}")
            return {"success": True}
        except requests.exceptions.RequestException as e:
            if hasattr(e, "response") and e.response is not None:
                if self._is_duplicate_error(e.response):
                    print(f"ℹ️  Workspace Identity ya es Contributor en workspace {workspace_id}")
                    return {"success": True, "already_existed": True}
                print(f"  Detalles: {e.response.text}")
            print(f"✗ Error al añadir Workspace Identity como Contributor: {e}")
            return {"success": False, "error": str(e)}

    def create_folder(self, workspace_id, folder_name, parent_folder_id=None):
        """
        Crea una carpeta en un workspace de Power BI usando Fabric API
        
        Args:
            workspace_id: ID del workspace donde crear la carpeta
            folder_name: Nombre de la carpeta
            parent_folder_id: ID de la carpeta padre (opcional, para subcarpetas)
            
        Returns:
            dict: Información de la carpeta creada incluyendo su ID
        """
        url = f"{self.fabric_url}/workspaces/{workspace_id}/folders"
        
        payload = {
            "displayName": folder_name
        }
        
        if parent_folder_id:
            payload["parentFolderId"] = parent_folder_id
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            
            folder = response.json()
            folder_id = folder.get('id')
            
            print(f"✓ Carpeta creada: {folder_name}")
            print(f"  ID: {folder_id}")
            print(f"  Workspace ID: {workspace_id}")
            
            self.created_objects.append({
                'type': 'folder',
                'id': folder_id,
                'name': folder_name,
                'workspace_id': workspace_id,
                'parent_folder_id': parent_folder_id
            })
            
            return {
                'success': True,
                'folder_id': folder_id,
                'folder_name': folder_name,
                'workspace_id': workspace_id,
                'data': folder
            }
            
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                already_exists = self._is_duplicate_error(e.response)
                if already_exists:
                    existing_id = self._find_folder_by_name(workspace_id, folder_name, parent_folder_id)
                    if existing_id:
                        print(f"ℹ️  Carpeta ya existe, reutilizando: {folder_name} (ID: {existing_id})")
                        return {
                            'success': True,
                            'folder_id': existing_id,
                            'folder_name': folder_name,
                            'workspace_id': workspace_id,
                            'already_existed': True,
                            'data': {}
                        }
                print(f"  Detalles: {e.response.text}")
            print(f"✗ Error al crear carpeta: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def create_lakehouse(self, workspace_id, lakehouse_name, description=None, folder_id=None, enable_schemas=None):
        """
        Crea un Lakehouse en un workspace usando Fabric API

        Args:
            workspace_id: ID del workspace donde crear el lakehouse
            lakehouse_name: Nombre del lakehouse
            description: Descripción opcional del lakehouse
            folder_id: ID de la carpeta donde ubicar el lakehouse (opcional)
            enable_schemas: Si es True crea el lakehouse con schemas habilitados,
                            si es False sin schemas. Si es None no se envía el parámetro
                            (comportamiento por defecto de la API)

        Returns:
            dict: Información del lakehouse creado incluyendo su ID
        """
        url = f"{self.fabric_url}/workspaces/{workspace_id}/items"

        payload = {
            "displayName": lakehouse_name,
            "type": "Lakehouse"
        }

        if description:
            payload["description"] = description

        if folder_id:
            payload["folderId"] = folder_id

        if enable_schemas is not None:
            payload["creationPayload"] = {"enableSchemas": enable_schemas}
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            
            lakehouse = response.json()
            lakehouse_id = lakehouse.get('id')
            
            print(f"✓ Lakehouse creado: {lakehouse_name}")
            print(f"  ID: {lakehouse_id}")
            print(f"  Workspace ID: {workspace_id}")
            
            self.created_objects.append({
                'type': 'lakehouse',
                'id': lakehouse_id,
                'name': lakehouse_name,
                'workspace_id': workspace_id,
                'description': description,
                'folder_id': folder_id,
                'enable_schemas': enable_schemas
            })
            
            return {
                'success': True,
                'lakehouse_id': lakehouse_id,
                'lakehouse_name': lakehouse_name,
                'workspace_id': workspace_id,
                'data': lakehouse
            }
            
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                already_exists = self._is_duplicate_error(e.response)
                if already_exists:
                    existing_id = self._find_lakehouse_by_name(workspace_id, lakehouse_name)
                    if existing_id:
                        print(f"ℹ️  Lakehouse ya existe, reutilizando: {lakehouse_name} (ID: {existing_id})")
                        return {
                            'success': True,
                            'lakehouse_id': existing_id,
                            'id': existing_id,
                            'lakehouse_name': lakehouse_name,
                            'workspace_id': workspace_id,
                            'already_existed': True,
                            'data': {}
                        }
                print(f"  Detalles: {e.response.text}")
            print(f"✗ Error al crear lakehouse: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def create_notebook_item(self, workspace_id, notebook_name, folder_id=None, description=None):
        """
        Crea un notebook vacío en un workspace (solo metadata, sin contenido)
        
        Args:
            workspace_id: ID del workspace donde crear el notebook
            notebook_name: Nombre del notebook
            folder_id: ID de la carpeta destino (opcional)
            description: Descripción del notebook (opcional)
            
        Returns:
            dict: Información del notebook creado incluyendo su ID
        """
        url = f"{self.fabric_url}/workspaces/{workspace_id}/items"
        
        payload = {
            "displayName": notebook_name,
            "type": "Notebook"
        }
        
        if description:
            payload["description"] = description
        
        if folder_id:
            payload["folderId"] = folder_id
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            
            notebook = response.json()
            notebook_id = notebook.get('id')
            
            print(f"✓ Notebook creado: {notebook_name}")
            print(f"  ID: {notebook_id}")
            print(f"  Workspace ID: {workspace_id}")
            
            self.created_objects.append({
                'type': 'notebook',
                'id': notebook_id,
                'name': notebook_name,
                'workspace_id': workspace_id,
                'folder_id': folder_id,
                'description': description
            })
            
            return {
                'success': True,
                'notebook_id': notebook_id,
                'notebook_name': notebook_name,
                'workspace_id': workspace_id,
                'data': notebook
            }
            
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                already_exists = self._is_duplicate_error(e.response)
                if already_exists:
                    existing_id = self._find_item_by_name(workspace_id, notebook_name, "Notebook")
                    if existing_id:
                        print(f"ℹ️  Notebook ya existe, reutilizando: {notebook_name} (ID: {existing_id})")
                        return {
                            'success': True,
                            'notebook_id': existing_id,
                            'id': existing_id,
                            'notebook_name': notebook_name,
                            'workspace_id': workspace_id,
                            'already_existed': True,
                            'data': {}
                        }
                print(f"  Detalles: {e.response.text}")
            print(f"✗ Error al crear notebook: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def upload_notebook_content(self, workspace_id, notebook_id, notebook_content):
        """
        Sube contenido convertido a IPYNB usando updateDefinition con payload Base64.

        Preferencia:
        1) Intentar convertir con jupytext (soporta celdas y metadatos si están marcados)
        2) Fallback a un IPYNB mínimo con una sola celda

        - Genera un documento con nbformat 4.5 y metadata.language.
        - Las nuevas celdas no incluyen metadata.id.
        """
        import base64
        import json as _json
        

        content_base64 = base64.b64encode(notebook_content.encode('utf-8')).decode('utf-8')

        url = f"{self.fabric_url}/workspaces/{workspace_id}/items/{notebook_id}/updateDefinition"
        payload = {
            "definition": {
                "format": "ipynb",
                "parts": [
                    {
                        "path": "notebook.ipynb",
                        "payload": content_base64,
                        "payloadType": "InlineBase64"
                    }
                ]
            }
        }

        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()

            print(f"  ✓ Contenido subido al notebook ID: {notebook_id}")

            return {
                'success': True,
                'notebook_id': notebook_id
            }

        except requests.exceptions.RequestException as e:
            print(f"  ✗ Error al subir contenido: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"    Detalles: {e.response.text}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def create_pipeline_item(self, workspace_id, pipeline_name, folder_id=None):
        """
        Crea un Data Pipeline vacío en un workspace de Fabric.

        Args:
            workspace_id: ID del workspace
            pipeline_name: Nombre del pipeline
            folder_id: ID de la carpeta destino (opcional)

        Returns:
            dict: success, pipeline_id, pipeline_name, workspace_id
        """
        url = f"{self.fabric_url}/workspaces/{workspace_id}/items"
        payload = {
            "displayName": pipeline_name,
            "type": "DataPipeline"
        }
        if folder_id:
            payload["folderId"] = folder_id

        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            item = response.json()
            pipeline_id = item.get('id')
            print(f"✓ Pipeline creado: {pipeline_name}")
            print(f"  ID: {pipeline_id}")
            self.created_objects.append({
                'type': 'pipeline',
                'id': pipeline_id,
                'name': pipeline_name,
                'workspace_id': workspace_id,
                'folder_id': folder_id
            })
            return {'success': True, 'pipeline_id': pipeline_id, 'pipeline_name': pipeline_name, 'workspace_id': workspace_id}
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                already_exists = self._is_duplicate_error(e.response)
                if already_exists:
                    existing_id = self._find_item_by_name(workspace_id, pipeline_name, "DataPipeline")
                    if existing_id:
                        print(f"ℹ️  Pipeline ya existe, reutilizando: {pipeline_name} (ID: {existing_id})")
                        return {
                            'success': True,
                            'pipeline_id': existing_id,
                            'id': existing_id,
                            'pipeline_name': pipeline_name,
                            'workspace_id': workspace_id,
                            'already_existed': True
                        }
                print(f"  Detalles: {e.response.text}")
            print(f"✗ Error al crear pipeline: {e}")
            return {'success': False, 'error': str(e)}

    def upload_pipeline_definition(self, workspace_id, pipeline_id, json_content):
        """
        Sube la definición JSON de un Data Pipeline usando updateDefinition.

        Args:
            workspace_id: ID del workspace
            pipeline_id: ID del pipeline ya creado
            json_content: Contenido JSON del pipeline como string

        Returns:
            dict: success, pipeline_id
        """
        import base64 as _b64
        content_b64 = _b64.b64encode(json_content.encode('utf-8')).decode('utf-8')
        url = f"{self.fabric_url}/workspaces/{workspace_id}/items/{pipeline_id}/updateDefinition"
        payload = {
            "definition": {
                "parts": [
                    {
                        "path": "pipeline-content.json",
                        "payload": content_b64,
                        "payloadType": "InlineBase64"
                    }
                ]
            }
        }
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            print(f"  ✓ Definición subida al pipeline ID: {pipeline_id}")
            return {'success': True, 'pipeline_id': pipeline_id}
        except requests.exceptions.RequestException as e:
            print(f"  ✗ Error al subir definición: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"    Detalles: {e.response.text}")
            return {'success': False, 'error': str(e)}

    def get_pipeline_definition(self, workspace_id, pipeline_id):
        """
        Obtiene la definición actual de un Data Pipeline recién creado para
        extraer campos generados por Fabric (lastModifiedByObjectId, etc.).
        Reintenta hasta 3 veces con backoff exponencial (2s, 4s, 8s) para dar
        tiempo a Fabric a tener la definición disponible tras la creación.

        Args:
            workspace_id: ID del workspace
            pipeline_id: ID del pipeline

        Returns:
            dict: success, pipeline_def (dict parsed del JSON), raw_content (str)
        """
        import base64 as _b64
        import json as _json
        import time

        url = f"{self.fabric_url}/workspaces/{workspace_id}/items/{pipeline_id}/getDefinition"
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                response = requests.post(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                parts = data.get('definition', {}).get('parts', [])
                for part in parts:
                    if part.get('path') == 'pipeline-content.json':
                        raw = _b64.b64decode(part['payload']).decode('utf-8')
                        return {'success': True, 'pipeline_def': _json.loads(raw), 'raw_content': raw}
                error_msg = 'pipeline-content.json no encontrado en la definición'
                if attempt < max_attempts:
                    wait = 2 ** attempt
                    print(f"    ⚠️  Intento {attempt}/{max_attempts}: {error_msg}. Reintentando en {wait}s...")
                    time.sleep(wait)
                    continue
                return {'success': False, 'error': error_msg}
            except requests.exceptions.RequestException as e:
                if hasattr(e, 'response') and e.response is not None:
                    print(f"    Detalles: {e.response.text}")
                if attempt < max_attempts:
                    wait = 2 ** attempt
                    print(f"    ⚠️  Intento {attempt}/{max_attempts} fallido: {e}. Reintentando en {wait}s...")
                    time.sleep(wait)
                else:
                    return {'success': False, 'error': str(e)}
        return {'success': False, 'error': 'Máximo de reintentos alcanzado'}

    def create_variable_library(self, workspace_id, name, variables, folder_id=None):
        """
        Crea un ítem VariableLibrary en Fabric y sube su definición en una sola llamada.

        Args:
            workspace_id: ID del workspace donde crear la librería
            name: Nombre del ítem (ej: VL_MI_PROYECTO)
            variables: Lista de dicts con keys: name, type, value y opcionalmente note
            folder_id: ID de carpeta destino (opcional)

        Returns:
            dict: success, variable_library_id, variable_library_name
        """
        import base64 as _b64
        import json as _json

        variables_content = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/variableLibrary/definition/variables/1.0.0/schema.json",
            "variables": variables
        }
        settings_content = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/variableLibrary/definition/settings/1.0.0/schema.json",
            "valueSetsOrder": []
        }

        def b64(obj):
            return _b64.b64encode(_json.dumps(obj, ensure_ascii=False, indent=2).encode('utf-8')).decode('utf-8')

        payload = {
            "displayName": name,
            "definition": {
                "format": "VariableLibraryV1",
                "parts": [
                    {"path": "variables.json", "payload": b64(variables_content), "payloadType": "InlineBase64"},
                    {"path": "settings.json",  "payload": b64(settings_content),  "payloadType": "InlineBase64"}
                ]
            }
        }
        if folder_id:
            payload["folderId"] = folder_id

        url = f"{self.fabric_url}/workspaces/{workspace_id}/variableLibraries"
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            # 202 = LRO (Long Running Operation) — también indica éxito
            if response.status_code not in (200, 201, 202):
                response.raise_for_status()

            vl_id = None
            if response.content:
                try:
                    vl_id = response.json().get('id')
                except Exception:
                    pass
            # Si fue LRO (202), intentar extraer el ID de la URL del header Location
            if not vl_id and response.status_code == 202:
                location = response.headers.get('Location', '')
                parts = location.split('/')
                if 'variableLibraries' in parts:
                    idx = parts.index('variableLibraries')
                    if idx + 1 < len(parts):
                        vl_id = parts[idx + 1]

            print(f"✓ Variable Library creada: {name}")
            if vl_id:
                print(f"  ID: {vl_id}")
            print(f"  Variables: {len(variables)}")

            self.created_objects.append({
                'type': 'variable_library',
                'id': vl_id,
                'name': name,
                'workspace_id': workspace_id
            })
            return {'success': True, 'variable_library_id': vl_id, 'variable_library_name': name}

        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                if self._is_duplicate_error(e.response):
                    # VL ya existe — buscar su ID y actualizar la definición
                    existing_id = self._find_item_by_name(workspace_id, name, "VariableLibrary")
                    if not existing_id:
                        # Fallback: listar via endpoint dedicado
                        try:
                            vl_list = requests.get(
                                f"{self.fabric_url}/workspaces/{workspace_id}/variableLibraries",
                                headers=self.headers
                            ).json()
                            for vl in vl_list.get('value', []):
                                if vl.get('displayName') == name:
                                    existing_id = vl.get('id')
                                    break
                        except Exception:
                            pass
                    if existing_id:
                        print(f"ℹ️  Variable Library ya existe, actualizando definición: {name}")
                        upd_url = f"{self.fabric_url}/workspaces/{workspace_id}/variableLibraries/{existing_id}/updateDefinition"
                        try:
                            upd_resp = requests.post(upd_url, headers=self.headers, json={"definition": payload["definition"]})
                            if upd_resp.status_code in (200, 201, 202):
                                print(f"  ✓ Definición actualizada")
                                return {'success': True, 'variable_library_id': existing_id, 'variable_library_name': name, 'already_existed': True}
                        except Exception:
                            pass
                print(f"  Detalles: {e.response.text}")
            print(f"✗ Error al crear Variable Library: {e}")
            return {'success': False, 'error': str(e)}

    def create_shortcut_to_lakehouse(self, target_workspace_id, target_item_id, *, shortcut_name, shortcut_parent_path,
                                     source_workspace_id, source_item_id, source_path, conflict_policy="CreateOrOverwrite"):
        """
        Crea un OneLake Shortcut dentro de un Lakehouse a otra ubicación de OneLake (otro lakehouse)

        Args:
            target_workspace_id: Workspace donde se creará el shortcut (del lakehouse destino donde se coloca el acceso)
            target_item_id: ID del lakehouse donde se creará el shortcut (el lakehouse que contendrá el acceso)
            shortcut_name: Nombre del shortcut (carpeta/tabla virtual)
            shortcut_parent_path: Ruta destino donde crear el acceso en el lakehouse: "Files" o "Tables" (puede incluir subcarpetas)
            source_workspace_id: Workspace del lakehouse origen (al que apunta el acceso)
            source_item_id: ID del lakehouse origen (al que apunta el acceso)
            source_path: Ruta dentro del lakehouse origen. Ejemplos: "Files", "Files/subcarpeta", "Tables/miTabla"
            conflict_policy: Política de conflicto del shortcut si ya existe (Abort, GenerateUniqueName, CreateOrOverwrite, OverwriteOnly)

        Returns:
            dict: Resultado de la creación del shortcut
        """
        url = (
            f"{self.fabric_url}/workspaces/{target_workspace_id}/items/{target_item_id}/shortcuts"
            f"?shortcutConflictPolicy={conflict_policy}"
        )

        payload = {
            "name": shortcut_name,
            "path": shortcut_parent_path,
            "target": {
                "oneLake": {
                    "workspaceId": source_workspace_id,
                    "itemId": source_item_id,
                    "path": source_path
                }
            }
        }

        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()

            print(f"✓ Shortcut creado: {shortcut_name}")
            print(f"  En: Lakehouse {target_item_id} -> {shortcut_parent_path}")
            print(f"  Apunta a: Lakehouse {source_item_id} -> {source_path}")

            self.created_objects.append({
                'type': 'shortcut',
                'name': shortcut_name,
                'target_workspace_id': target_workspace_id,
                'target_item_id': target_item_id,
                'shortcut_parent_path': shortcut_parent_path,
                'source_workspace_id': source_workspace_id,
                'source_item_id': source_item_id,
                'source_path': source_path
            })
            
            return {
                'success': True,
                'data': response.json() if response.content else {},
                'name': shortcut_name,
                'path': shortcut_parent_path
            }
        except requests.exceptions.RequestException as e:
            print(f"✗ Error al crear shortcut '{shortcut_name}': {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"  Detalles: {e.response.text}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_created_objects(self):
        """Devuelve la lista de objetos creados en esta sesión"""
        return self.created_objects
    
    def create_workspace_with_structure(self, workspace_name, folder_name=None, lakehouse_name=None):
        """
        Crea un workspace completo con carpeta y lakehouse en una sola operación
        
        Args:
            workspace_name: Nombre del workspace
            folder_name: Nombre de la carpeta (opcional)
            lakehouse_name: Nombre del lakehouse (opcional)
            
        Returns:
            dict: IDs de todos los objetos creados
        """
        result = {
            'workspace_id': None,
            'folder_id': None,
            'lakehouse_id': None,
            'errors': []
        }
        
        # 1. Crear workspace
        workspace_result = self.create_workspace(workspace_name)
        if not workspace_result['success']:
            result['errors'].append(f"Workspace: {workspace_result['error']}")
            return result
        
        result['workspace_id'] = workspace_result['workspace_id']
        
        # 2. Crear carpeta si se especifica
        if folder_name:
            folder_result = self.create_folder(result['workspace_id'], folder_name)
            if folder_result['success']:
                result['folder_id'] = folder_result['folder_id']
            else:
                result['errors'].append(f"Carpeta: {folder_result['error']}")
        
        # 3. Crear lakehouse si se especifica
        if lakehouse_name:
            lakehouse_result = self.create_lakehouse(
                result['workspace_id'], 
                lakehouse_name,
                folder_id=result['folder_id']
            )
            if lakehouse_result['success']:
                result['lakehouse_id'] = lakehouse_result['lakehouse_id']
            else:
                result['errors'].append(f"Lakehouse: {lakehouse_result['error']}")
        
        return result
    
    def upload_notebook(self, workspace_id, notebook_name, notebook_file_path, folder_id=None, description=None):
        """
        Sube un archivo .notebook (Jupyter/Fabric Notebook) a un workspace
        
        Args:
            workspace_id: ID del workspace destino
            notebook_name: Nombre del notebook en Fabric
            notebook_file_path: Ruta local al archivo .ipynb o .notebook
            folder_id: ID de la carpeta destino (opcional)
            description: Descripción del notebook (opcional)
            
        Returns:
            dict: Información del notebook creado incluyendo su ID
        """
        # Leer el contenido del archivo notebook
        try:
            with open(notebook_file_path, 'r', encoding='utf-8') as f:
                notebook_content = f.read()
        except Exception as e:
            print(f"✗ Error al leer archivo notebook: {e}")
            return {
                'success': False,
                'error': f"Error leyendo archivo: {str(e)}"
            }
        
        # Codificar el contenido en base64
        notebook_base64 = base64.b64encode(notebook_content.encode('utf-8')).decode('utf-8')
        
        # URL para crear el notebook usando Fabric Items API
        url = f"{self.fabric_url}/workspaces/{workspace_id}/notebooks"
        
        payload = {
            "displayName": notebook_name,
            "definition": {
                "format": "ipynb",
                "parts": [
                    {
                        "path": "notebook-content.py",
                        "payload": notebook_base64,
                        "payloadType": "InlineBase64"
                    }
                ]
            }
        }
        
        if description:
            payload["description"] = description
        
        if folder_id:
            payload["folderId"] = folder_id
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            
            notebook = response.json()
            notebook_id = notebook.get('id')
            
            print(f"✓ Notebook subido: {notebook_name}")
            print(f"  ID: {notebook_id}")
            print(f"  Workspace ID: {workspace_id}")
            print(f"  Archivo origen: {os.path.basename(notebook_file_path)}")
            
            return {
                'success': True,
                'notebook_id': notebook_id,
                'notebook_name': notebook_name,
                'workspace_id': workspace_id,
                'data': notebook
            }
            
        except requests.exceptions.RequestException as e:
            print(f"✗ Error al subir notebook: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"  Detalles: {e.response.text}")
            return {
                'success': False,
                'error': str(e)
            }

    def provision_workspace_identity(self, workspace_id):
        """Provisiona la Workspace Identity del workspace si no existe."""
        get_url = f"{self.fabric_url}/workspaces/{workspace_id}/identity"
        try:
            resp = requests.get(get_url, headers=self.headers)
            if resp.status_code == 200:
                identity = resp.json()
                if identity.get('servicePrincipalId') or identity.get('applicationId'):
                    print(f"ℹ️  Workspace Identity ya existe (workspace: {workspace_id})")
                    return {'success': True, 'already_existed': True}
        except Exception:
            pass

        url = f"{self.fabric_url}/workspaces/{workspace_id}/provisionIdentity"
        try:
            response = requests.post(url, headers=self.headers)
            if response.status_code in (200, 201, 202):
                print(f"✓ Workspace Identity provisionada (workspace: {workspace_id})")
                return {'success': True}
            if response.status_code == 404:
                print(f"  ⚠️  Workspace Identity no disponible (workspace sin capacidad Fabric compatible o feature no habilitada)")
                return {'success': True, 'skipped': True}
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                try:
                    body = e.response.json()
                    code = body.get('errorCode', '') or body.get('error', {}).get('code', '')
                    if 'AlreadyExists' in code or 'AlreadyProvisioned' in code:
                        print(f"ℹ️  Workspace Identity ya existe")
                        return {'success': True, 'already_existed': True}
                except Exception:
                    pass
                if e.response.status_code == 404:
                    print(f"  ⚠️  Workspace Identity no disponible (workspace sin capacidad Fabric compatible o feature no habilitada)")
                    return {'success': True, 'skipped': True}
                print(f"  Detalles: {e.response.text}")
            print(f"✗ Error al provisionar Workspace Identity: {e}")
            return {'success': False, 'error': str(e)}

    def get_workspace_identity(self, workspace_id: str) -> dict:
        """Returns the Workspace Identity servicePrincipalId and applicationId."""
        url = f"{self.fabric_url}/workspaces/{workspace_id}/identity"
        try:
            resp = requests.get(url, headers=self.headers)
            if resp.status_code == 200:
                data = resp.json()
                sp_id = data.get("servicePrincipalId")
                if sp_id:
                    return {
                        "success": True,
                        "servicePrincipalId": sp_id,
                        "applicationId": data.get("applicationId"),
                    }
                return {"success": False, "error": "servicePrincipalId absent from identity response"}
            return {"success": False, "error": f"Identity not available (status {resp.status_code})"}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e)}

    def get_lakehouse_sql_endpoint(self, workspace_id, lakehouse_id):
        """Obtiene el SQL endpoint de un lakehouse, esperando hasta que esté disponible."""
        import time
        url = f"{self.fabric_url}/workspaces/{workspace_id}/lakehouses/{lakehouse_id}"
        max_attempts = 6
        for attempt in range(1, max_attempts + 1):
            try:
                response = requests.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                sql_props = data.get('properties', {}).get('sqlEndpointProperties', {})
                status = sql_props.get('provisioningStatus', '')
                endpoint = sql_props.get('connectionString', '')
                if status == 'Success' and endpoint:
                    return {'success': True, 'endpoint': endpoint}
                if attempt < max_attempts:
                    wait = min(10 * attempt, 30)
                    print(f"    ⏳ SQL Endpoint no disponible (estado: {status}), esperando {wait}s...")
                    time.sleep(wait)
            except requests.exceptions.RequestException as e:
                if hasattr(e, 'response') and e.response is not None:
                    print(f"    Detalles: {e.response.text}")
                if attempt < max_attempts:
                    time.sleep(10)
                else:
                    return {'success': False, 'error': str(e)}
        return {'success': False, 'error': 'SQL Endpoint no disponible tras varios intentos'}

    def get_or_create_sql_connection(self, connection_name, server, database, credential_type, sp_credentials=None):
        """
        Crea o reutiliza una conexión SQL Server en Fabric.

        Args:
            connection_name: Nombre de la conexión
            server: SQL endpoint (xxx.datawarehouse.fabric.microsoft.com)
            database: Nombre del lakehouse (base de datos)
            credential_type: 'ServicePrincipal' o 'WorkspaceIdentity'
            sp_credentials: dict con tenant_id, client_id, client_secret (solo ServicePrincipal)
        """
        list_url = f"{self.fabric_url}/connections"
        try:
            resp = requests.get(list_url, headers=self.headers)
            if resp.status_code == 200:
                for conn in resp.json().get('value', []):
                    if conn.get('displayName') == connection_name:
                        conn_id = conn.get('id')
                        print(f"ℹ️  Conexión ya existe, reutilizando: {connection_name} (ID: {conn_id})")
                        return {'success': True, 'connection_id': conn_id, 'already_existed': True}
        except Exception:
            pass

        if credential_type == 'ServicePrincipal' and sp_credentials:
            cred_details = {
                "singleSignOnType": "None",
                "connectionEncryption": "NotEncrypted",
                "skipTestConnection": False,
                "credentials": {
                    "credentialType": "ServicePrincipal",
                    "servicePrincipalClientId": sp_credentials['client_id'],
                    "tenantId": sp_credentials['tenant_id'],
                    "servicePrincipalSecret": sp_credentials['client_secret']
                }
            }
        else:
            cred_details = {
                "singleSignOnType": "None",
                "connectionEncryption": "NotEncrypted",
                "skipTestConnection": False,
                "credentials": {
                    "credentialType": "WorkspaceIdentity"
                }
            }

        payload = {
            "displayName": connection_name,
            "connectivityType": "ShareableCloud",
            "connectionDetails": {
                "type": "SQL",
                "creationMethod": "SQL",
                "parameters": [
                    {"dataType": "Text", "name": "server", "value": server},
                    {"dataType": "Text", "name": "database", "value": database}
                ]
            },
            "credentialDetails": cred_details,
            "privacyLevel": "Organizational",
            "allowUsageInUserControlledCode": True
        }

        try:
            response = requests.post(list_url, headers=self.headers, json=payload)
            response.raise_for_status()
            conn_id = response.json().get('id')
            print(f"✓ Conexión SQL creada: {connection_name}")
            if conn_id:
                print(f"  ID: {conn_id}")
            return {'success': True, 'connection_id': conn_id}
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                if self._is_duplicate_error(e.response):
                    try:
                        r2 = requests.get(list_url, headers=self.headers)
                        r2.raise_for_status()
                        for conn in r2.json().get('value', []):
                            if conn.get('displayName') == connection_name:
                                conn_id = conn.get('id')
                                print(f"ℹ️  Conexión ya existe, reutilizando: {connection_name} (ID: {conn_id})")
                                return {'success': True, 'connection_id': conn_id, 'already_existed': True}
                    except Exception:
                        pass
                print(f"  Detalles: {e.response.text}")
            print(f"✗ Error al crear conexión SQL: {e}")
            return {'success': False, 'error': str(e)}

def upload_pipelines_from_src(manager, workspace_id, src_paths, notebook_registry, existing_pipelines, folder_mapping):
    """
    Recopila y sube Data Pipelines (JSON) desde una o varias rutas fuente.

    Args:
        manager: Instancia de PowerBIObjectManager
        workspace_id: ID del workspace destino
        src_paths: Lista de rutas (str) o dicts {path, mapping_override} donde buscar .json
        notebook_registry: {notebook_name: {'id': ..., 'workspace_id': ...}}
        existing_pipelines: {pipeline_name: pipeline_id} pre-cargados del workspace
        folder_mapping: {folder_path: folder_id} para resolver carpetas de destino
    """
    import os
    import json as _json

    def resolve_folder(relative_path, mapping_override=None):
        if relative_path == '.':
            return None
        norm = relative_path.replace(os.sep, '/')
        parts = norm.split('/')
        # Si hay mapping_override, traducir la primera parte y reconstruir la ruta
        if mapping_override and parts[0] in mapping_override:
            target_base = mapping_override[parts[0]]
            remaining = parts[1:]
            full_target = (target_base + '/' + '/'.join(remaining)) if remaining else target_base
            target_parts = full_target.split('/')
            for i in range(len(target_parts), 0, -1):
                candidate = '/'.join(target_parts[:i])
                if candidate in folder_mapping:
                    return folder_mapping[candidate]
        # Fallback: búsqueda directa (más profunda primero)
        for i in range(len(parts), 0, -1):
            candidate = '/'.join(parts[:i])
            if candidate in folder_mapping:
                return folder_mapping[candidate]
        return None

    # Normalizar src_paths: acepta tanto strings como dicts {path, mapping_override}
    src_configs = []
    for entry in src_paths:
        if isinstance(entry, dict):
            src_configs.append(entry)
        else:
            src_configs.append({'path': entry, 'mapping_override': None})

    # Recopilar todos los .json de las rutas fuente
    pipeline_entries = []
    for cfg in src_configs:
        src_path = cfg['path']
        mapping_override = cfg.get('mapping_override')
        if not os.path.exists(src_path):
            print(f"  ⚠️  Carpeta de pipelines {src_path} no existe, saltando")
            continue
        print(f"\n  📂 Procesando pipelines desde: {src_path}")
        for root, dirs, files in os.walk(src_path):
            for file_name in files:
                if not file_name.endswith('.json'):
                    continue
                relative_path = os.path.relpath(root, src_path)
                pipeline_entries.append((file_name, root, resolve_folder(relative_path, mapping_override)))

    if not pipeline_entries:
        return

    # Ordenar de mayor a menor por nombre (04_ antes que 01_) para crear dependencias primero
    pipeline_entries.sort(key=lambda e: e[0], reverse=True)

    if notebook_registry:
        print(f"\n  📋 Registry de notebooks disponible para sustitución en pipelines: {len(notebook_registry)} notebooks")

    pipeline_registry = dict(existing_pipelines)
    pipelines_for_second_pass = []

    def substitute_notebook_ids(activities):
        """Sustituye notebookId y workspaceId en actividades TridentNotebook de forma recursiva."""
        if not isinstance(activities, list):
            return
        for activity in activities:
            if not isinstance(activity, dict):
                continue
            if activity.get('type') == 'TridentNotebook':
                tp = activity.setdefault('typeProperties', {})
                notebook_name = tp.pop('notebookName', None) or activity.get('name', '')
                nb_info = notebook_registry.get(notebook_name)
                if nb_info:
                    tp['notebookId'] = nb_info['id']
                    tp['workspaceId'] = nb_info['workspace_id']
                    print(f"        🔗 TridentNotebook '{activity.get('name')}' → notebook '{notebook_name}' ({nb_info['id']})")
                else:
                    print(f"        ⚠️  TridentNotebook '{activity.get('name')}': notebook '{notebook_name}' no encontrado en registry")
            tp = activity.get('typeProperties', {})
            if isinstance(tp, dict):
                for key in ('activities', 'ifTrueActivities', 'ifFalseActivities', 'defaultActivities'):
                    nested = tp.get(key)
                    if nested:
                        substitute_notebook_ids(nested)
                for case in tp.get('cases', []):
                    nested = case.get('activities')
                    if nested:
                        substitute_notebook_ids(nested)

    def substitute_pipeline_refs(activities):
        """Sustituye referenceName en actividades ExecutePipeline usando pipelineName como clave."""
        had_unresolved = False
        if not isinstance(activities, list):
            return had_unresolved
        for activity in activities:
            if not isinstance(activity, dict):
                continue
            if activity.get('type') == 'ExecutePipeline':
                tp = activity.setdefault('typeProperties', {})
                pipeline_ref = tp.setdefault('pipeline', {})
                pl_name = pipeline_ref.pop('pipelineName', None)
                if pl_name:
                    pl_id = pipeline_registry.get(pl_name)
                    if pl_id:
                        pipeline_ref['referenceName'] = pl_id
                        print(f"        🔗 ExecutePipeline '{activity.get('name')}' → pipeline '{pl_name}' ({pl_id})")
                    else:
                        pipeline_ref['pipelineName'] = pl_name
                        had_unresolved = True
                        print(f"        ⏳ ExecutePipeline '{activity.get('name')}': '{pl_name}' pendiente de segundo pase")
            tp = activity.get('typeProperties', {})
            if isinstance(tp, dict):
                for key in ('activities', 'ifTrueActivities', 'ifFalseActivities', 'defaultActivities'):
                    nested = tp.get(key)
                    if nested:
                        if substitute_pipeline_refs(nested):
                            had_unresolved = True
                for case in tp.get('cases', []):
                    nested = case.get('activities')
                    if nested:
                        if substitute_pipeline_refs(nested):
                            had_unresolved = True
        return had_unresolved

    for file_name, root, target_folder_id in pipeline_entries:
        pipeline_path = os.path.join(root, file_name)
        pipeline_name = os.path.splitext(file_name)[0]

        try:
            with open(pipeline_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"    ✗ Error leyendo {pipeline_path}: {e}")
            continue

        if pipeline_name in existing_pipelines:
            pipeline_id = existing_pipelines[pipeline_name]
            print(f"    ℹ️  Pipeline ya existe, reutilizando: {pipeline_name}")
        else:
            print(f"    🔀 Creando pipeline: {pipeline_name}")
            pipeline_result = manager.create_pipeline_item(workspace_id, pipeline_name, folder_id=target_folder_id)
            if not pipeline_result.get('success'):
                print(f"      ✗ Error creando pipeline: {pipeline_result.get('error')}")
                continue
            pipeline_id = pipeline_result.get('pipeline_id')
        pipeline_registry[pipeline_name] = pipeline_id

        last_modified_by_object_id = None
        def_result = manager.get_pipeline_definition(workspace_id, pipeline_id)
        if def_result.get('success'):
            fabric_def = def_result['pipeline_def']
            last_modified_by_object_id = (
                fabric_def.get('properties', {}).get('lastModifiedByObjectId')
            )

        pipeline_def = None
        try:
            pipeline_def = _json.loads(content)
            pipeline_def['objectId'] = pipeline_id
            if last_modified_by_object_id:
                pipeline_def.setdefault('properties', {})['lastModifiedByObjectId'] = last_modified_by_object_id
            activities = pipeline_def.get('properties', {}).get('activities', [])
            substitute_notebook_ids(activities)
            had_unresolved = substitute_pipeline_refs(activities)
            content = _json.dumps(pipeline_def, ensure_ascii=False, indent='\t')
            if had_unresolved:
                pipelines_for_second_pass.append((pipeline_id, pipeline_def))
        except Exception as e:
            print(f"      ⚠️  No se pudo procesar la definición: {e}")

        print(f"      ⬆️  Subiendo definición...")
        upload_result = manager.upload_pipeline_definition(workspace_id, pipeline_id, content)
        if not upload_result.get('success'):
            print(f"      ✗ Error subiendo definición: {upload_result.get('error')}")

    if pipelines_for_second_pass:
        print(f"\n  🔄 Segundo pase: resolviendo referencias entre {len(pipelines_for_second_pass)} pipelines...")
        for pipeline_id, pipeline_def in pipelines_for_second_pass:
            try:
                activities = pipeline_def.get('properties', {}).get('activities', [])
                still_unresolved = substitute_pipeline_refs(activities)
                content = _json.dumps(pipeline_def, ensure_ascii=False, indent='\t')
                upload_result = manager.upload_pipeline_definition(workspace_id, pipeline_id, content)
                if upload_result.get('success'):
                    status = "⚠️  referencias pendientes" if still_unresolved else "✓"
                    print(f"      {status} Pipeline {pipeline_id} actualizado")
                else:
                    print(f"      ✗ Error en segundo pase para pipeline {pipeline_id}: {upload_result.get('error')}")
            except Exception as e:
                print(f"      ✗ Error en segundo pase para pipeline {pipeline_id}: {e}")


def process_and_upload_notebooks_from_src(manager, workspace_id, workspace_name, project_name, folder_mapping, registry, topology_mode='multi_workspace', ama_version='v2', develop=True, extraction_method='datafactory'):
    """
    Recorre ./src y ../AMA_v2/notebooks/ buscando notebooks y los sube al workspace correspondiente

    Args:
        manager: Instancia de PowerBIObjectManager
        workspace_id: ID del workspace donde subir notebooks
        workspace_name: Nombre del workspace
        project_name: Nombre del proyecto para identificar lakehouses
        folder_mapping: Diccionario con mapeo de folder_name -> folder_id
        registry: Registro con información de workspaces y lakehouses
        topology_mode: Topología AMA V2: multi_workspace, single_workspace o single_lakehouse
        ama_version: Versión a desplegar: 'v1', 'v2' (default), o 'both'
        develop: Si es True, incluye notebooks de desarrollo (notebooks_dev/) para iteración rápida (default: True)
    """
    import os
    import re

    # Detectar directorio raíz del proyecto (donde están ama_v2/, AMA/, Extractores/)
    script_dir = os.path.dirname(os.path.abspath(__file__))  # Instalador/
    project_root = os.path.dirname(script_dir)  # Raíz del proyecto
    
    # Mapeo de nombres de directorio local → ruta de carpeta en Fabric.
    # Solo entradas que difieren de identidad (la capitalización de Fabric es la misma del disco).
    _V2_SUBFOLDER_MAP = {
        'Utils': 'Common',  # notebooks/Utils/ → Fabric Common
    }

    def _build_v2_notebook_source(base_path):
        """Construye la entrada de fuente v2 con mapping_override generado dinámicamente
        a partir de las subcarpetas que existan en base_path."""
        mapping_override = {}
        if os.path.exists(base_path):
            for entry in os.listdir(base_path):
                if os.path.isdir(os.path.join(base_path, entry)):
                    # Fallback: identidad (convención lowercase alineada entre local y Fabric)
                    mapping_override[entry] = _V2_SUBFOLDER_MAP.get(entry, entry)
        if not mapping_override:
            mapping_override = dict(_V2_SUBFOLDER_MAP)
        return {'path': base_path, 'mapping_override': mapping_override, 'version': 'v2'}

    # Construir fuentes de notebooks según versión y método de extracción
    notebook_sources = []

    if ama_version in ('v2', 'both'):
        notebook_sources.append(_build_v2_notebook_source(os.path.join(project_root, "ama_v2/notebooks")))
        if develop:
            notebook_sources.append({
                'path': os.path.join(project_root, "ama_v2/notebooks_dev"),
                'mapping_override': {
                    '.':             'Core',
                    'Config':        'Core/Config',
                    'IO':            'Core/IO',
                    'Discovery':     'Core/Discovery',
                    'Metadata':      'Core/Metadata',
                    'Patterns':      'Core/Patterns',
                    'Processors':    'Core/Processors',
                    'Logging':       'Core/Logging',
                    'Orchestration': 'Core/Orchestration',
                },
                'version': 'v2',
                'is_dev': True
            })

    if ama_version in ('v1', 'both'):
        notebook_sources.append({
            'path': os.path.join(project_root, "AMA"),
            'mapping_override': None,
            'version': 'v1'
        })

    if extraction_method == 'datafactory':
        notebook_sources.append({
            'path': os.path.join(project_root, 'Extractores/DataFactory/Personalization'),
            'mapping_override': {
                '01_Bronze': 'Personalization/01_Bronze',
            },
            'version': 'personalization',
            'is_personalization': True
        })

    if not notebook_sources:
        print(f"  ⚠️  No hay fuentes configuradas para versión '{ama_version}'")
        return

    dev_status = "con notebooks de desarrollo" if develop else "sin notebooks de desarrollo"
    ext_status = f", extracción: {extraction_method}" if extraction_method else ""
    print(f"\n  📓 Procesando notebooks AMA (versión: {ama_version}, {dev_status}{ext_status})...")

    # Helpers para resolver IDs del registry sin lanzar excepción
    lkp_ws = registry['workspace_by_name']
    lkp_lh = registry['lakehouse_by_name']

    def ws_id(name):
        info = lkp_ws.get(name)
        return info['id'] if info else None

    def lh_id(name):
        info = lkp_lh.get(name)
        return info['id'] if info else None

    # Construir diccionario de sustituciones de variables Python según topología
    if topology_mode == 'multi_workspace':
        control_lh_name   = f"LH_{project_name}_CONTROL"
        default_lh_name   = f"LH_{project_name}_03_GOLD_in"
        default_ws_name   = f"{project_name}_03_GOLD"
        py_var_subs = {
            'control_workspace_id':    ws_id(f"{project_name}_00_CONTROL"),
            'control_lakehouse_id':    lh_id(control_lh_name),
            'landing_workspace_id':    ws_id(f"{project_name}_01_BRONZE"),
            'landing_lakehouse_id':    lh_id(f"LH_{project_name}_01_BRONZE_in"),
            'bronze_workspace_id':     ws_id(f"{project_name}_01_BRONZE"),
            'bronze_lakehouse_in_id':  lh_id(f"LH_{project_name}_01_BRONZE_in"),
            'bronze_lakehouse_out_id': lh_id(f"LH_{project_name}_01_BRONZE_out"),
            'silver_workspace_id':     ws_id(f"{project_name}_02_SILVER"),
            'silver_lakehouse_out_id': lh_id(f"LH_{project_name}_02_SILVER_out"),
            'gold_workspace_id':       ws_id(f"{project_name}_03_GOLD"),
            'gold_lakehouse_in_id':    lh_id(f"LH_{project_name}_03_GOLD_in"),
            'gold_lakehouse_out_id':   lh_id(f"LH_{project_name}_03_GOLD_out"),
            'gold_lakehouse_out_name': f"LH_{project_name}_03_GOLD_out",
            'mod_workspace_id':        ws_id(f"{project_name}_03_GOLD"),
        }
    else:
        control_lh_name   = f"LH_{project_name}_CONTROL"
        default_lh_name   = f"LH_{project_name}_DATA"
        default_ws_name   = f"{project_name}_01_DATA"
        data_ws = ws_id(f"{project_name}_01_DATA")
        data_lh = lh_id(f"LH_{project_name}_DATA")
        py_var_subs = {
            'control_workspace_id':    ws_id(f"{project_name}_00_CONTROL"),
            'control_lakehouse_id':    lh_id(control_lh_name),
            'landing_workspace_id':    data_ws,
            'landing_lakehouse_id':    data_lh,
            'bronze_workspace_id':     data_ws,
            'bronze_lakehouse_in_id':  data_lh,
            'bronze_lakehouse_out_id': data_lh,
            'silver_workspace_id':     data_ws,
            'silver_lakehouse_out_id': data_lh,
            'gold_workspace_id':       data_ws,
            'gold_lakehouse_in_id':    data_lh,
            'gold_lakehouse_out_id':   data_lh,
            'gold_lakehouse_out_name': f"LH_{project_name}_DATA",
            'mod_workspace_id':        None,
        }

    py_var_subs['project_name'] = project_name
    py_var_subs['topology_mode'] = topology_mode
    py_var_subs['vl_name'] = f"VL_ENVIRONMENT_VARIABLES"
    py_var_subs['run_discovery'] = 'true'

    # IDs del default_lakehouse para metadatos del notebook Fabric
    gold_lh_id    = lh_id(default_lh_name)
    gold_ws_id    = ws_id(default_ws_name)
    gold_in_lh_name = default_lh_name

    if not gold_lh_id or not gold_ws_id:
        print(f"  ⚠️  No se encontró lakehouse '{default_lh_name}' o workspace '{default_ws_name}' para sustitución")
        return

    print(f"  📝 Sustituciones configuradas ({topology_mode}):")
    for var, val in py_var_subs.items():
        if val:
            print(f"     {var} -> {val}")

    def resolve_folder(relative_path, mapping_override=None):
        """Devuelve el folder_id de Fabric para la ruta relativa más profunda que exista en folder_mapping.
        Las claves de folder_mapping tienen formato 'Personalization/00_control'.
        Se intenta desde la ruta completa hacia la raíz (el match más profundo gana).

        Args:
            relative_path: Ruta relativa desde la carpeta base (en minúsculas, convención nb_)
            mapping_override: Dict opcional que mapea nombres de carpeta base a carpetas de Fabric
                            (ej: {'personalization': 'Personalization', 'install': 'Install'})
        """
        # Manejar raíz especial con mapping_override
        if relative_path == '.':
            if mapping_override and '.' in mapping_override:
                target_folder_name = mapping_override['.']
                if target_folder_name in folder_mapping:
                    return folder_mapping[target_folder_name]
            return None
        
        norm = relative_path.replace(os.sep, '/')
        parts = norm.split('/')
        
        # Si hay mapping_override, traducir parts[0] y reconstruir la ruta completa
        if mapping_override and parts[0] in mapping_override:
            target_base = mapping_override[parts[0]]
            remaining_parts = parts[1:]
            if remaining_parts:
                full_target = target_base + '/' + '/'.join(remaining_parts)
            else:
                full_target = target_base
            # Buscar coincidencia más larga posible en folder_mapping
            target_path_parts = full_target.split('/')
            for i in range(len(target_path_parts), 0, -1):
                candidate = '/'.join(target_path_parts[:i])
                if candidate in folder_mapping:
                    return folder_mapping[candidate]

        # Fallback: buscar coincidencia exacta en folder_mapping
        for i in range(len(parts), 0, -1):
            candidate = '/'.join(parts[:i])
            if candidate in folder_mapping:
                return folder_mapping[candidate]
        return None

    def apply_py_var_subs(content):
        """Sustituye las variables Python de IDs de workspaces y lakehouses en el contenido."""
        for var_name, new_value in py_var_subs.items():
            if new_value is None:
                continue
            # Soporta tanto comillas normales como escapadas JSON (\" ... \")
            content = re.sub(
                r'(' + re.escape(var_name) + r'\s*=\s*\\?")\s*[^"\\]*(\\?")',
                r'\g<1>' + new_value + r'\g<2>',
                content
            )
        return content

    def apply_bootstrap_defaults(content):
        """Rellena parámetros del bootstrap_first_run con valores de instalación."""
        replacements = {
            'project_name': project_name,
            'topology_mode': topology_mode,
            'vl_name': f"VL_ENVIRONMENT_VARIABLES",
            'run_discovery': 'true',
        }
        for var_name, new_value in replacements.items():
            content = re.sub(
                r'(' + re.escape(var_name) + r'\s*=\s*\\?")\s*[^"\\]*(\\?")',
                r'\g<1>' + new_value + r'\g<2>',
                content
            )
        return content
    

    # Pre-cargar notebooks y pipelines existentes en el workspace
    existing_notebooks = manager._get_workspace_items(workspace_id, "Notebook")
    existing_pipelines = manager._get_workspace_items(workspace_id, "DataPipeline")
    if existing_notebooks:
        print(f"  ℹ️  {len(existing_notebooks)} notebooks pre-cargados del workspace existente")
    if existing_pipelines:
        print(f"  ℹ️  {len(existing_pipelines)} pipelines pre-cargados del workspace existente")

    # Procesar cada fuente de notebooks
    for source in notebook_sources:
        src_path = source['path']
        mapping_override = source.get('mapping_override')
        is_dev = source.get('is_dev', False)
        
        if not os.path.exists(src_path):
            print(f"  ⚠️  Carpeta {src_path} no existe, saltando")
            continue
        
        if is_dev:
            print(f"\n  📂 Procesando: {src_path} 🚀 MODO DESARROLLO")
            print(f"     ⚡ Estos notebooks permiten iteración rápida sin rebuild de .whl")
            print(f"     📖 Ver: AMA_v2/DESARROLLO_RAPIDO.md para más info")
        else:
            print(f"\n  📂 Procesando: {src_path}")
        
        # recorrer carpetas y buscar .ipynb o .notebook
        # Recorrer carpetas en la fuente actual
        for root, dirs, files in os.walk(src_path):
            # Buscar archivos .ipynb
            for file_name in files:
                if file_name.endswith('.ipynb'):
                    notebook_path = os.path.join(root, file_name)
                    notebook_name = os.path.splitext(file_name)[0]
        
                    # Determinar la carpeta de destino en Fabric
                    relative_path = os.path.relpath(root, src_path)
                    target_folder_id = resolve_folder(relative_path, mapping_override)

                    # Leer contenido del .ipynb
                    try:
                        with open(notebook_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                    except Exception as e:
                        print(f"    ✗ Error leyendo {notebook_path}: {e}")
                        continue
                    
                    # Hacer sustituciones   
                    # 1. default_lakehouse ID
                    content = re.sub(
                        r'"default_lakehouse":\s*"[a-f0-9\-]+"',
                        f'"default_lakehouse": "{gold_lh_id}"',
                        content
                    )
                    # 2. default_lakehouse_name
                    content = re.sub(
                        r'"default_lakehouse_name":\s*"[^"]+"',
                        f'"default_lakehouse_name": "{gold_in_lh_name}"',
                        content
                    )

                    # 3. default_lakehouse_workspace_id
                    
                    content = re.sub(
                        r'"default_lakehouse_workspace_id":\s*"[a-f0-9\-]+"',   
                        f'"default_lakehouse_workspace_id": "{gold_ws_id}"',
                        content
                    )

                    # 4. project_name variable
                    content = re.sub(
                        r'project_name\s*:\s*str\s*=\s*(\\?")([^"\\]*)(\\?")',
                        f'project_name: str = \\\"{project_name}\\\"',
                    content
                    )

                    # 5. Variables Python de IDs de workspaces y lakehouses
                    content = apply_py_var_subs(content)

                    # 6. Autorrellenar parámetros de bootstrap
                    if notebook_name == 'bootstrap_first_run':
                        content = apply_bootstrap_defaults(content)

                    if notebook_name in existing_notebooks:
                        notebook_id = existing_notebooks[notebook_name]
                        print(f"    ℹ️  Notebook ya existe, reutilizando: {notebook_name}")
                    else:
                        print(f"    📔 Creando notebook: {notebook_name}")
                        notebook_result = manager.create_notebook_item(
                            workspace_id,
                            notebook_name,
                            folder_id=target_folder_id
                        )
                        if not notebook_result.get('success'):
                            print(f"      ✗ Error creando notebook: {notebook_result.get('error')}")
                            continue
                        notebook_id = notebook_result.get('notebook_id')

                    # Subir contenido
                    print(f"      ⬆️  Subiendo contenido...")
                    upload_result = manager.upload_notebook_content(
                        workspace_id,
                        notebook_id,
                        content
                    )
        
                    if not upload_result.get('success'):
                        print(f"      ✗ Error subiendo contenido: {upload_result.get('error')}")

        # Recorrer carpetas en la fuente actual para buscar carpetas .Notebook
        for root, dirs, files in os.walk(src_path):
            # Buscar carpetas .Notebook
            for dir_name in dirs:
                if dir_name.endswith('.Notebook'):
                    notebook_folder = os.path.join(root, dir_name)
                    notebook_name = dir_name.replace('.Notebook', '')
                    
                    # Determinar la carpeta de destino en Fabric
                    relative_path = os.path.relpath(root, src_path)
                    target_folder_id = resolve_folder(relative_path, mapping_override)
                    
                    # Buscar archivo notebook-content.py
                    py_file = os.path.join(notebook_folder, 'notebook-content.py')
                    if not os.path.exists(py_file):
                        print(f"    ⚠️  No se encontró notebook-content.py en {notebook_folder}")
                        continue
                    
                    # Leer contenido
                    try:
                        with open(py_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                    except Exception as e:
                        print(f"    ✗ Error leyendo {py_file}: {e}")
                        continue
                    
                    # Hacer sustituciones
                    # 1. default_lakehouse ID
                    content = re.sub(
                        r'"default_lakehouse":\s*"[a-f0-9\-]+"',
                        f'"default_lakehouse": "{gold_lh_id}"',
                        content
                    )
                    
                    # 2. default_lakehouse_name
                    content = re.sub(
                        r'"default_lakehouse_name":\s*"[^"]+"',
                        f'"default_lakehouse_name": "{gold_in_lh_name}"',
                        content
                    )
                    
                    # 3. default_lakehouse_workspace_id
                    content = re.sub(
                        r'"default_lakehouse_workspace_id":\s*"[a-f0-9\-]+"',
                        f'"default_lakehouse_workspace_id": "{gold_ws_id}"',
                        content
                    )

                    # 4. Variables Python de IDs de workspaces y lakehouses
                    content = apply_py_var_subs(content)

                    # 5. Autorrellenar parámetros de bootstrap
                    if notebook_name == 'bootstrap_first_run':
                        content = apply_bootstrap_defaults(content)

                    # Crear notebook en Fabric (o reutilizar si ya existe)
                    if notebook_name in existing_notebooks:
                        notebook_id = existing_notebooks[notebook_name]
                        print(f"    ℹ️  Notebook ya existe, reutilizando: {notebook_name}")
                    else:
                        print(f"    📔 Creando notebook: {notebook_name}")
                        notebook_result = manager.create_notebook_item(
                            workspace_id,
                            notebook_name,
                            folder_id=target_folder_id
                        )
                        if not notebook_result.get('success'):
                            print(f"      ✗ Error creando notebook: {notebook_result.get('error')}")
                            continue
                        notebook_id = notebook_result.get('notebook_id')

                    # Subir contenido
                    print(f"      ⬆️  Subiendo contenido...")
                    upload_result = manager.upload_notebook_content(
                        workspace_id,
                        notebook_id,
                        content
                    )
                    
                    if not upload_result.get('success'):
                        print(f"      ✗ Error subiendo contenido: {upload_result.get('error')}")

    # Construir notebook_registry: primero los pre-cargados (ya existían), luego los creados en sesión
    notebook_registry = {
        name: {'id': nb_id, 'workspace_id': workspace_id}
        for name, nb_id in existing_notebooks.items()
    }
    notebook_registry.update({
        obj['name']: {'id': obj['id'], 'workspace_id': obj['workspace_id']}
        for obj in manager.created_objects
        if obj.get('type') == 'notebook'
    })

    # Determinar rutas de pipelines según versión y método de extracción
    pipeline_src_configs = []

    if ama_version in ('v1', 'both'):
        pipeline_src_configs.append({'path': os.path.join(project_root, 'AMA'), 'mapping_override': None})

    if extraction_method == 'datafactory':
        pipeline_src_configs.append({
            'path': os.path.join(project_root, 'Extractores/DataFactory/Personalization'),
            'mapping_override': {
                '01_Bronze': 'Personalization/01_Bronze',
            }
        })

    upload_pipelines_from_src(
        manager=manager,
        workspace_id=workspace_id,
        src_paths=pipeline_src_configs,
        notebook_registry=notebook_registry,
        existing_pipelines=existing_pipelines,
        folder_mapping=folder_mapping,
    )


def build_variable_library_variables(project_name, registry, topology_mode='multi_workspace', enable_schemas=False, sql_connection_id=None):
    """
    Construye la lista de variables para la Variable Library VL_{project_name}_environment_variables.

    Incluye:
    - IDs de workspaces y lakehouses resueltos desde el registry (dependientes de arquitectura)
    - Variables de configuración fija con valores por defecto

    Args:
        project_name: Nombre del proyecto (prefijo de todos los recursos)
        registry: Dict con 'workspace_by_name' y 'lakehouse_by_name'
        topology_mode: Topología AMA V2: multi_workspace, single_workspace o single_lakehouse

    Returns:
        Lista de dicts con {name, type, value, note}
    """
    lkp_ws = registry['workspace_by_name']
    lkp_lh = registry['lakehouse_by_name']

    def ws_id(name):
        info = lkp_ws.get(name)
        return info['id'] if info else None

    def lh_id(name):
        info = lkp_lh.get(name)
        return info['id'] if info else None

    p = project_name
    if topology_mode == 'multi_workspace':
        id_vars = [
            ('control_workspace_id',    ws_id(f"{p}_00_CONTROL"),        'ID del workspace de control'),
            ('control_lakehouse_id',    lh_id(f"LH_{p}_CONTROL"),        'ID del lakehouse de control'),
            ('landing_workspace_id',    ws_id(f"{p}_01_BRONZE"),         'ID del workspace de landing (BRONZE)'),
            ('landing_lakehouse_id',    lh_id(f"LH_{p}_01_BRONZE_in"),   'ID del lakehouse de landing (BRONZE in)'),
            ('bronze_workspace_id',     ws_id(f"{p}_01_BRONZE"),         'ID del workspace BRONZE'),
            ('bronze_lakehouse_in_id',  lh_id(f"LH_{p}_01_BRONZE_in"),   'ID del lakehouse BRONZE in'),
            ('bronze_lakehouse_out_id', lh_id(f"LH_{p}_01_BRONZE_out"),  'ID del lakehouse BRONZE out'),
            ('silver_workspace_id',     ws_id(f"{p}_02_SILVER"),         'ID del workspace SILVER'),
            ('silver_lakehouse_out_id', lh_id(f"LH_{p}_02_SILVER_out"),  'ID del lakehouse SILVER out'),
            ('gold_workspace_id',       ws_id(f"{p}_03_GOLD"),           'ID del workspace GOLD'),
            ('gold_lakehouse_in_id',    lh_id(f"LH_{p}_03_GOLD_in"),     'ID del lakehouse GOLD in'),
            ('gold_lakehouse_out_id',   lh_id(f"LH_{p}_03_GOLD_out"),    'ID del lakehouse GOLD out'),
            ('gold_lakehouse_out_name', f"LH_{p}_03_GOLD_out",           'Nombre del lakehouse GOLD out'),
            ('mod_workspace_id',        ws_id(f"{p}_03_GOLD"),           'ID del workspace de modelo (GOLD)'),
        ]
    else:
        data_ws = ws_id(f"{p}_01_DATA")
        data_lh = lh_id(f"LH_{p}_DATA")
        id_vars = [
            ('control_workspace_id',    ws_id(f"{p}_00_CONTROL"),   'ID del workspace de control'),
            ('control_lakehouse_id',    lh_id(f"LH_{p}_CONTROL"),   'ID del lakehouse de control'),
            ('landing_workspace_id',    data_ws,                     'ID del workspace de datos'),
            ('landing_lakehouse_id',    data_lh,                     'ID del lakehouse de datos'),
            ('bronze_workspace_id',     data_ws,                     'ID del workspace de datos'),
            ('bronze_lakehouse_in_id',  data_lh,                     'ID del lakehouse de datos'),
            ('bronze_lakehouse_out_id', data_lh,                     'ID del lakehouse de datos'),
            ('silver_workspace_id',     data_ws,                     'ID del workspace de datos'),
            ('silver_lakehouse_out_id', data_lh,                     'ID del lakehouse de datos'),
            ('gold_workspace_id',       data_ws,                     'ID del workspace de datos'),
            ('gold_lakehouse_in_id',    data_lh,                     'ID del lakehouse de datos'),
            ('gold_lakehouse_out_id',   data_lh,                     'ID del lakehouse de datos'),
            ('gold_lakehouse_out_name', f"LH_{p}_DATA",              'Nombre del lakehouse de datos'),
            ('mod_workspace_id',        None,                         'ID del workspace de modelo (no aplica en workspace único)'),
        ]

    variables = []
    for var_name, value, note in id_vars:
        if value is None:
            continue  # lakehouse no creado o no aplica, omitir
        var_type = 'Guid' if var_name.endswith('_id') else 'String'
        variables.append({'name': var_name, 'type': var_type, 'value': value, 'note': note})

    # Variables de configuración fija
    config_vars = [
        ('project_name',                project_name,                       'String', 'Nombre del proyecto AMA'),
        ('topology_mode',               topology_mode,                      'String', 'Topología AMA V2 activa'),
        ('control_lakehouse_name',      f"LH_{project_name}_CONTROL",       'String', 'Nombre del lakehouse de control del proyecto'),
        ('run_discovery_default',       'true',                             'String', 'Valor por defecto para run_discovery en bootstrap'),
        ('container_name',              'Data',                             'String', 'Nombre del contenedor de datos'),
        ('shortcut_path',               'Landing',                          'String', 'Ruta del shortcut de landing'),
        ('control_sqlendpoint_connection_id', sql_connection_id or 'REPLACE ME',   'String', 'ID de la conexión SQL del SQL Endpoint del lakehouse de control'),
        ('default_connection_guid',     'REPLACE ME',                       'String', 'GUID de conexión por defecto'),
        ('sources_table_name',          'control_sources',          'String', 'Nombre de la tabla de fuentes'),
        ('entities_table_name',         'control_entities',         'String', 'Nombre de la tabla de entidades'),
        ('entities_aux_table_name',     'control_entities_aux',     'String', 'Nombre de la tabla auxiliar de entidades'),
        ('semantic_layer_table_name',   'control_semantic_layer',           'String', 'Nombre de la tabla de capa semántica'),
        ('use_schemas',                 enable_schemas,                     'Boolean', 'Indica si los lakehouses tienen schemas habilitados'),
        ('data_schema',                 'dbo',                              'String', 'Esquema de base de datos por defecto'),
        ('data_delimiter',              'N/D',                              'String', 'Delimitador de datos por defecto'),
    ]

    # Publicar layer_config en VL para que el runtime topology-aware no dependa de defaults ambiguos
    if topology_mode == 'multi_workspace':
        config_vars.extend([
            ('bronze_workspace_suffix', '_01_BRONZE', 'String', 'Sufijo del workspace BRONZE'),
            ('bronze_dual_lakehouse', 'true', 'String', 'Si BRONZE usa lakehouses IN/OUT'),
            ('bronze_lakehouse_in_suffix', '_in', 'String', 'Sufijo lakehouse IN BRONZE'),
            ('bronze_lakehouse_out_suffix', '_out', 'String', 'Sufijo lakehouse OUT BRONZE'),
            ('silver_workspace_suffix', '_02_SILVER', 'String', 'Sufijo del workspace SILVER'),
            ('silver_dual_lakehouse', 'true', 'String', 'Si SILVER usa lakehouses IN/OUT'),
            ('silver_lakehouse_in_suffix', '_in', 'String', 'Sufijo lakehouse IN SILVER'),
            ('silver_lakehouse_out_suffix', '_out', 'String', 'Sufijo lakehouse OUT SILVER'),
            ('gold_workspace_suffix', '_03_GOLD', 'String', 'Sufijo del workspace GOLD'),
            ('gold_dual_lakehouse', 'true', 'String', 'Si GOLD usa lakehouses IN/OUT'),
            ('gold_lakehouse_in_suffix', '_in', 'String', 'Sufijo lakehouse IN GOLD'),
            ('gold_lakehouse_out_suffix', '_out', 'String', 'Sufijo lakehouse OUT GOLD'),
        ])
    elif topology_mode == 'single_workspace':
        config_vars.extend([
            ('bronze_lakehouse', f'LH_{p}_DATA', 'String', 'Lakehouse de BRONZE en single_workspace'),
            ('silver_lakehouse', f'LH_{p}_DATA', 'String', 'Lakehouse de SILVER en single_workspace'),
            ('gold_lakehouse', f'LH_{p}_DATA', 'String', 'Lakehouse de GOLD en single_workspace'),
        ])
    elif topology_mode == 'single_lakehouse':
        config_vars.extend([
            ('lakehouse_name', f'LH_{p}_DATA', 'String', 'Lakehouse único de datos'),
            ('bronze_folder', 'bronze', 'String', 'Folder lógico BRONZE en single_lakehouse'),
            ('silver_folder', 'silver', 'String', 'Folder lógico SILVER en single_lakehouse'),
            ('gold_folder', 'gold', 'String', 'Folder lógico GOLD en single_lakehouse'),
        ])

    for var_name, value, var_type, note in config_vars:
        variables.append({'name': var_name, 'type': var_type, 'value': value, 'note': note})

    return variables


def install_public_libraries_to_environment(bearer_token, workspace_id, environment_id, libraries):
    """
    Instala librerías públicas (PyPI) en un Environment de Fabric.
    
    NOTA: Temporalmente deshabilitada debido a limitaciones de la API de Fabric.
    Las librerías públicas deben instalarse manualmente desde el portal:
    1. Workspace → Environment → Custom libraries
    2. "Public libraries" → Add
    3. Escribir: duckdb>=0.9.0, pyyaml>=6.0
    
    Args:
        bearer_token: Token de acceso para la API de Fabric.
        workspace_id: ID del workspace donde reside el Environment.
        environment_id: ID del Environment artifact.
        libraries: Lista de strings con los paquetes a instalar (e.g., ["duckdb>=0.9.0", "pandas>=2.0.0"]).

    Returns:
        dict con 'success' (bool) y 'errors' (list).
    """
    # TODO: Implementar cuando la API de Fabric soporte correctamente la instalación de librerías públicas via REST
    print(f"      ℹ️  Instalación automática de librerías públicas no disponible")
    print(f"      ℹ️  Librerías requeridas: {', '.join(libraries)}")
    print(f"      ℹ️  Por favor, instálalas manualmente desde el portal de Fabric")
    return {'success': True, 'errors': []}


def install_wheel_to_environment(bearer_token, workspace_id, environment_name, wheel_path, auto_publish=True):
    """
    Instala un paquete .whl en un Environment de Fabric.

    Los paquetes quedan disponibles en los notebooks que usan ese Environment
    automáticamente (el Environment se encarga de instalar el .whl).

    Flujo:
      1. Buscar (o crear) el Environment en el workspace.
      2. Subir el .whl a la staging area del Environment.
      3. Opcionalmente publicar los cambios del Environment.

    Args:
        bearer_token: Token de acceso para la API de Fabric.
        workspace_id: ID del workspace donde reside el Environment.
        environment_name: Nombre del Environment artifact.
        wheel_path: Ruta local al fichero .whl (p.ej. ../AMA_v2/dist/ama_v2-2.0.0-py3-none-any.whl).
        auto_publish: Si True, publica automáticamente después de subir. Si False, requiere publish manual.

    Returns:
        dict con 'success' (bool), 'errors' (list) y 'environment_id' (str).
    """
    fabric_url = "https://api.fabric.microsoft.com/v1"
    headers = {
        'Authorization': f'Bearer {bearer_token}',
    }
    json_headers = {
        'Authorization': f'Bearer {bearer_token}',
        'Content-Type': 'application/json',
    }

    # ── 1. Buscar o crear el Environment ──────────────────────────────────────
    env_id = None
    list_url = f"{fabric_url}/workspaces/{workspace_id}/items?type=Environment"
    while list_url:
        resp = _request_with_retry('GET', list_url, headers=json_headers)
        data = resp.json()
        for item in data.get('value', []):
            if item.get('displayName') == environment_name:
                env_id = item['id']
                break
        if env_id:
            break
        list_url = data.get('continuationUri')

    if not env_id:
        print(f"    Creando Environment: {environment_name}")
        create_resp = _request_with_retry(
            'POST',
            f"{fabric_url}/workspaces/{workspace_id}/items",
            headers=json_headers,
            json={"displayName": environment_name, "type": "Environment"},
        )
        env_id = create_resp.json().get('id')
        print(f"    ✓ Environment creado (ID: {env_id})")
    else:
        print(f"    ℹ️  Environment ya existe: {environment_name} (ID: {env_id})")

    # ── 2. Subir .whl a la staging area ───────────────────────────────────────
    upload_url = f"{fabric_url}/workspaces/{workspace_id}/environments/{env_id}/staging/libraries"
    wheel_filename = os.path.basename(wheel_path)
    
    errors = []
    try:
        with open(wheel_path, 'rb') as f:
            file_resp = _request_with_retry(
                'POST',
                upload_url,
                headers=headers,
                files={'file': (wheel_filename, f, 'application/zip')},
            )
        print(f"      ✓ {wheel_filename} subido correctamente")
    except Exception as e:
        errors.append(f"{wheel_filename}: {e}")
        print(f"      ✗ {wheel_filename}: {e}")
        return {'success': False, 'errors': errors, 'environment_id': env_id}

    # ── 3. Publicar cambios del Environment (opcional) ───────────────────────
    if auto_publish:
        print(f"    Publicando Environment...")
        pub_resp = _request_with_retry(
            'POST',
            f"{fabric_url}/workspaces/{workspace_id}/environments/{env_id}/staging/publish",
            headers=json_headers,
        )
        if pub_resp.status_code in (200, 202):
            print(f"    ✓ Publish lanzado correctamente")
            return {'success': True, 'errors': [], 'environment_id': env_id}
        else:
            errors.append(f"Publish failed ({pub_resp.status_code}): {pub_resp.text}")
            print(f"    ⚠️  Publish falló: {pub_resp.status_code} — {pub_resp.text}")
            return {'success': False, 'errors': errors, 'environment_id': env_id}
    else:
        print(f"    ℹ️  Wheel subido (pendiente de publicación)")
        return {'success': True, 'errors': [], 'environment_id': env_id}


def create_structure_from_yaml(yaml_structure, bearer_token, admin_email, capacity_id=None, enable_schemas=None, topology_mode='multi_workspace', ama_version='v2', develop=True, onelake_credential=None, sp_credentials=None, extraction_method='datafactory'):
    """
    Crea la estructura completa de workspaces, carpetas y lakehouses desde YAML

    Args:
        yaml_structure: Diccionario con la estructura YAML parseada
        bearer_token: Token de autenticación para Power BI API
        admin_email: Email del usuario a añadir como admin en los workspaces
        capacity_id: ID de la capacidad de Fabric donde crear los workspaces (opcional)
        enable_schemas: Si es True crea los lakehouses con schemas habilitados,
                        si es False sin schemas. Si es None usa el comportamiento
                        por defecto de la API (opcional)
        topology_mode: Topología AMA V2: multi_workspace, single_workspace o single_lakehouse
        ama_version: Versión de notebooks AMA a subir: 'v1', 'v2' o 'both'
        develop: Si es True, incluye notebooks de desarrollo (notebooks_dev/) para iteración rápida (default: True)
        onelake_credential: (Obsoleto, se ignora) Ya no se usa ADLS Gen2; el paquete ama
                            se sube al Environment de Fabric vía REST API.

    Returns:
        dict: Resumen de la estructura creada con todos los IDs
    """
    import yaml
    
    manager = PowerBIObjectManager(bearer_token)
    valid_topologies = {'multi_workspace', 'single_workspace', 'single_lakehouse'}
    if topology_mode not in valid_topologies:
        raise ValueError(f"topology_mode inválido: '{topology_mode}'. Valores válidos: {sorted(valid_topologies)}")

    result = {
        'workspaces': {},
        'errors': [],
        'capacity_id': capacity_id
    }
    
    # Si yaml_structure es string, parsearlo
    if isinstance(yaml_structure, str):
        yaml_structure = yaml.safe_load(yaml_structure)
    
    # Navegar por la estructura (admite lista o diccionario)
    ama_structure = yaml_structure.get('Ama_estructure')
    
    print("\n" + "="*80)
    print("CREACIÓN DE ESTRUCTURA DESDE YAML")
    print("="*80 + "\n")
    
    # Registro de objetos para atar shortcuts tras crear todo
    registry = {
        'workspace_by_name': {},           # name -> { id }
        'lakehouse_by_name': {}            # name -> { id, workspace_id }
    }

    pending_shortcuts = []  # se procesan al final

    def parse_from_to_path(value: str):
        # Espera valores tipo "<LakehouseName>/Files" o "<LakehouseName>/Tables/subcarpeta"
        parts = value.split('/')
        lh_name = parts[0]
        rest = '/'.join(parts[1:]) if len(parts) > 1 else ''
        # Asegurar que empieza por Files o Tables
        parent_path = rest if rest else 'Files'
        return lh_name, parent_path

    def process_children(workspace_name, workspace_id, children, parent_folder_id=None, parent_path=''):
        if not isinstance(children, list):
            return
        for node in children:
            if not isinstance(node, dict):
                continue
            if 'folder' in node:
                folder_name = node.get('folder')
                if not folder_name:
                    continue
                folder_key = f"{parent_path}/{folder_name}" if parent_path else folder_name
                existing_folder_id = result['workspaces'][workspace_name]['folders'].get(folder_key)
                if existing_folder_id:
                    print(f"    ℹ️  Carpeta ya existe, reutilizando: {folder_name}")
                    process_children(workspace_name, workspace_id, node.get('children', []), existing_folder_id, folder_key)
                    continue
                print(f"    🗂️  Creando carpeta: {folder_name}")
                folder_res = manager.create_folder(workspace_id, folder_name, parent_folder_id)
                if not folder_res.get('success'):
                    result['errors'].append(f"Carpeta {folder_name} en {workspace_name}: {folder_res.get('error')}")
                    continue
                new_folder_id = folder_res.get('folder_id')
                result['workspaces'][workspace_name]['folders'][folder_key] = new_folder_id
                # hijos de la carpeta
                process_children(workspace_name, workspace_id, node.get('children', []), new_folder_id, folder_key)
            elif 'lh' in node:
                lh_name = node.get('lh')
                if not lh_name:
                    continue
                print(f"    🏠 Creando lakehouse: {lh_name}")
                lh_res = manager.create_lakehouse(workspace_id, lh_name, folder_id=parent_folder_id, enable_schemas=enable_schemas)
                if not lh_res.get('success'):
                    result['errors'].append(f"Lakehouse {lh_name} en {workspace_name}: {lh_res.get('error')}")
                    continue
                lh_id = lh_res.get('lakehouse_id')
                result['workspaces'][workspace_name]['lakehouses'][lh_name] = {
                    'lakehouse_id': lh_id,
                    'folder_id': parent_folder_id
                }
                registry['lakehouse_by_name'][lh_name] = {
                    'id': lh_id,
                    'workspace_id': workspace_id,
                    'workspace_name': workspace_name
                }
            elif 'shortcut' in node:
                sc = node.get('shortcut') or {}
                sc_from = sc.get('from')
                sc_to = sc.get('to')
                sc_name = sc.get('name')  # Nombre opcional del shortcut
                if sc_from and sc_to:
                    src_lh, src_path = parse_from_to_path(sc_from)
                    dst_lh, dst_path = parse_from_to_path(sc_to)
                    pending_shortcuts.append({
                        'workspace_name': workspace_name,
                        'source_lh': src_lh,
                        'source_path': src_path,
                        'target_lh': dst_lh,
                        'target_path': dst_path,
                        'name': sc_name  # Guardar el nombre personalizado
                    })
                else:
                    result['errors'].append(f"Shortcut inválido en {workspace_name}: {sc}")

    # Si la estructura es lista (nuevo formato con 'Workspace' y 'children')
    if isinstance(ama_structure, list):
        for ws_entry in ama_structure:
            if not isinstance(ws_entry, dict):
                continue
            ws_name = ws_entry.get('Workspace')
            if not ws_name:
                continue

            print(f"\n{'─'*80}")
            print(f"📁 Creando Workspace: {ws_name}")
            print(f"{'─'*80}")

            ws_result = manager.create_workspace(ws_name, capacity_id=capacity_id)
            if not ws_result.get('success'):
                result['errors'].append(f"Workspace {ws_name}: {ws_result.get('error')}")
                continue
            workspace_id = ws_result.get('workspace_id')
            # Pre-cargar carpetas si el workspace ya existía
            preloaded_folders = {}
            if ws_result.get('already_existed'):
                raw_folders = manager._get_workspace_folders(workspace_id)
                # Reconstruir paths completos iterando por padres
                def _build_path(fid, folders_dict):
                    meta = folders_dict.get(fid, {})
                    parent = meta.get('parentFolderId')
                    name = meta.get('name', '')
                    if parent and parent in folders_dict:
                        return _build_path(parent, folders_dict) + '/' + name
                    return name
                for fid, meta in raw_folders.items():
                    path = _build_path(fid, raw_folders)
                    if path:
                        preloaded_folders[path] = fid
                if preloaded_folders:
                    print(f"  ℹ️  {len(preloaded_folders)} carpetas pre-cargadas del workspace existente")
            result['workspaces'][ws_name] = {
                'workspace_id': workspace_id,
                'folders': preloaded_folders,
                'lakehouses': {}
            }
            registry['workspace_by_name'][ws_name] = {'id': workspace_id}

            # Añadir admin (skip si ya lo es)
            if manager._is_workspace_admin(workspace_id, admin_email):
                print(f"\n  ℹ️  Admin ya asignado: {admin_email}")
            else:
                print(f"\n  👤 Añadiendo administrador...")
                admin_result = manager.add_workspace_admin(workspace_id, admin_email)
                if not admin_result.get('success'):
                    result['errors'].append(f"Admin en {ws_name}: {admin_result.get('error')}")

            # Procesar hijos
            process_children(ws_name, workspace_id, ws_entry.get('children', []))

        # Procesar notebooks DESPUÉS de crear todos los workspaces/folders/lakehouses
        # Buscar el workspace 00_CONTROL para subir notebooks
        control_workspace_info = None
        for ws_name, ws_data in result['workspaces'].items():
            if '_00_CONTROL' in ws_name or ws_name.endswith('00_CONTROL'):
                control_workspace_info = {
                    'name': ws_name,
                    'id': ws_data['workspace_id'],
                    'folders': ws_data['folders']
                }
                break
        
        if control_workspace_info:
            print(f"\n{'─'*80}")
            version_msg = {'v1': 'V1 (legacy)', 'v2': 'V2 (nuevo)', 'both': 'V1 y V2'}.get(ama_version, ama_version)
            print(f"📓 Subiendo Notebooks AMA {version_msg}")
            print(f"{'─'*80}")
            # Extraer nombre del proyecto
            project_name = control_workspace_info['name'].replace('_00_CONTROL', '')
            process_and_upload_notebooks_from_src(
                manager,
                control_workspace_info['id'],
                control_workspace_info['name'],
                project_name,
                control_workspace_info['folders'],
                registry,
                topology_mode=topology_mode,
                ama_version=ama_version,
                develop=develop,
                extraction_method=extraction_method
            )

            # Subir el paquete Python ama/ al Environment de Fabric (solo para V2)
            if ama_version in ('v2', 'both'):
                env_name = f"{project_name}_AMA_env"
                control_ws_id = control_workspace_info['id']

                # Ruta al directorio ama_v2
                _installer_dir = os.path.dirname(os.path.abspath(__file__))
                ama_v2_dir = os.path.join(_installer_dir, '..', 'ama_v2')
                ama_v2_dir = os.path.normpath(ama_v2_dir)
                wheel_path = os.path.join(ama_v2_dir, 'dist', 'ama_v2-2.0.0-py3-none-any.whl')

                # Construir el .whl si no existe
                if not os.path.isfile(wheel_path):
                    print(f"\n{'─'*80}")
                    print(f"🔨 Construyendo paquete .whl → {os.path.basename(wheel_path)}")
                    print(f"{'─'*80}")
                    try:
                        import subprocess
                        subprocess.run(
                            ['python', '-m', 'build', '--wheel'],
                            cwd=ama_v2_dir,
                            check=True,
                            capture_output=True,
                            text=True
                        )
                        print(f"  ✓ Wheel construido correctamente")
                    except subprocess.CalledProcessError as e:
                        error_msg = f"Error construyendo wheel: {e.stderr}"
                        print(f"  ✗ {error_msg}")
                        result['errors'].append(error_msg)
                        wheel_path = None
                    except Exception as e:
                        error_msg = f"Error construyendo wheel: {e}"
                        print(f"  ✗ {error_msg}")
                        result['errors'].append(error_msg)
                        wheel_path = None

                # Instalar el .whl en el Environment
                if wheel_path and os.path.isfile(wheel_path):
                    print(f"\n{'─'*80}")
                    print(f"📦 Instalando paquete AMA V2 en Environment → {env_name}")
                    print(f"{'─'*80}")
                    pkg_result = install_wheel_to_environment(
                        bearer_token,
                        control_ws_id,
                        env_name,
                        wheel_path,
                        auto_publish=False,  # No publicar aún, añadiremos librerías públicas primero
                    )
                    if pkg_result.get('success'):
                        print(f"\n  ✓ Wheel subido correctamente")
                    
                    env_id = pkg_result.get('environment_id')
                    if env_id:
                        result['environment'] = {
                            'id': env_id,
                            'name': env_name,
                            'workspace_id': control_ws_id,
                        }
                        
                        # Instalar dependencias públicas (PyPI)
                        print(f"\n  📚 Instalando dependencias públicas...")
                        public_libs = [
                            "duckdb>=0.9.0",
                            "pyyaml>=6.0"
                        ]
                        libs_result = install_public_libraries_to_environment(
                            bearer_token,
                            control_ws_id,
                            env_id,
                            public_libs,
                        )
                        libs_added = libs_result.get('success', False)
                        if libs_result.get('errors'):
                            for err in libs_result['errors']:
                                result['errors'].append(f"Environment libs: {err}")
                        
                        # Publicar Environment una sola vez con todo
                        print(f"\n  🚀 Publicando Environment...")
                        fabric_url = "https://api.fabric.microsoft.com/v1"
                        json_headers = {
                            'Authorization': f'Bearer {bearer_token}',
                            'Content-Type': 'application/json',
                        }
                        pub_resp = requests.post(
                            f"{fabric_url}/workspaces/{control_ws_id}/environments/{env_id}/staging/publish",
                            headers=json_headers,
                        )
                        if pub_resp.status_code in (200, 202):
                            print(f"  ✓ Environment publicado correctamente")
                            if libs_added:
                                print(f"  ✓ Wheel + dependencias públicas desplegadas")
                        else:
                            error_msg = f"Publish failed ({pub_resp.status_code}): {pub_resp.text}"
                            result['errors'].append(error_msg)
                            print(f"  ⚠️  {error_msg}")
                    
                    if pkg_result.get('errors'):
                        for err in pkg_result['errors']:
                            result['errors'].append(f"Environment install: {err}")
                        print(f"  ⚠️  {len(pkg_result['errors'])} errores durante la instalación del paquete")
                else:
                    print(f"\n  ⚠️  Paquete wheel no encontrado: {wheel_path}")
                    result['errors'].append(f"Paquete wheel no encontrado: {wheel_path}")


        if pending_shortcuts:
            print(f"\n{'─'*80}")
            print("🔗 Creando Shortcuts")
            print(f"{'─'*80}")
        for sc in pending_shortcuts:
            src_lh_name = sc['source_lh']
            dst_lh_name = sc['target_lh']

            src_info = registry['lakehouse_by_name'].get(src_lh_name)
            dst_info = registry['lakehouse_by_name'].get(dst_lh_name)

            if not src_info:
                result['errors'].append(f"Shortcut: lakehouse origen no encontrado '{src_lh_name}'")
                continue
            if not dst_info:
                result['errors'].append(f"Shortcut: lakehouse destino no encontrado '{dst_lh_name}'")
                continue

            # Usar nombre personalizado del YAML o generar uno automático
            shortcut_name = sc.get('name') or f"to_{dst_lh_name.replace(' ', '_')}"
            
            create_res = manager.create_shortcut_to_lakehouse(
                target_workspace_id=src_info['workspace_id'],
                target_item_id=src_info['id'],
                shortcut_name=shortcut_name,
                shortcut_parent_path=sc['source_path'],
                source_workspace_id=dst_info['workspace_id'],
                source_item_id=dst_info['id'],
                source_path=sc['target_path']
            )
            if not create_res.get('success'):
                result['errors'].append(f"Shortcut {shortcut_name} en {sc['workspace_name']}: {create_res.get('error')}")

        # Provisionar Workspace Identity y crear conexión SQL para el lakehouse de control
        sql_connection_id = None
        if control_workspace_info:
            ctrl_lh_name = f"LH_{project_name}_CONTROL"
            ctrl_lh_info = registry['lakehouse_by_name'].get(ctrl_lh_name)

            print(f"\n{'─'*80}")
            print("🔑 Provisionando Workspace Identity y conexión SQL")
            print(f"{'─'*80}")

            wi_result = manager.provision_workspace_identity(control_workspace_info['id'])
            if not wi_result.get('success'):
                result['errors'].append(f"Workspace Identity: {wi_result.get('error')}")

            # Add control workspace identity as Contributor to all data workspaces
            if wi_result.get('success') and not wi_result.get('skipped'):
                identity_result = manager.get_workspace_identity(control_workspace_info['id'])
                wi_sp_id = identity_result.get('servicePrincipalId') if identity_result.get('success') else None
                if wi_sp_id:
                    print(f"  ✓ Workspace Identity SP ID: {wi_sp_id}")
                    for ws_name, ws_data in result['workspaces'].items():
                        if '_00_CONTROL' in ws_name:
                            continue
                        data_ws_id = ws_data.get('workspace_id')
                        if not data_ws_id:
                            continue
                        print(f"  → Añadiendo como Contributor: {ws_name}")
                        contrib_result = manager.add_workspace_identity_as_contributor(data_ws_id, wi_sp_id)
                        if not contrib_result.get('success'):
                            result['errors'].append(f"Contributor en {ws_name}: {contrib_result.get('error')}")
                else:
                    print(f"  ⚠️  servicePrincipalId no disponible; no se añade como Contributor")


            if ctrl_lh_info:
                endpoint_result = manager.get_lakehouse_sql_endpoint(
                    ctrl_lh_info['workspace_id'], ctrl_lh_info['id']
                )
                if endpoint_result.get('success'):
                    sql_endpoint = endpoint_result['endpoint']
                    conn_name = f"{project_name}_LH_CONTROL_SQLENDPOINT"
                    credential_type = 'ServicePrincipal' if sp_credentials else 'WorkspaceIdentity'
                    conn_result = manager.get_or_create_sql_connection(
                        conn_name, sql_endpoint, ctrl_lh_name, credential_type, sp_credentials
                    )
                    if conn_result.get('success'):
                        sql_connection_id = conn_result.get('connection_id')
                        result['sql_connection'] = {
                            'id': sql_connection_id,
                            'name': conn_name,
                            'credential_type': credential_type
                        }
                        print(f"  ✓ connection_id: {sql_connection_id}")
                    else:
                        result['errors'].append(f"Conexión SQL: {conn_result.get('error')}")
                else:
                    result['errors'].append(f"SQL Endpoint: {endpoint_result.get('error')}")
            else:
                print(f"  ⚠️  Lakehouse de control '{ctrl_lh_name}' no encontrado en registry")

        # Crear Variable Library con todos los IDs resueltos
        if control_workspace_info:
            print(f"\n{'─'*80}")
            print("📚 Creando Variable Library")
            print(f"{'─'*80}")
            vl_name = f"VL_ENVIRONMENT_VARIABLES"
            vl_variables = build_variable_library_variables(project_name, registry, topology_mode, bool(enable_schemas), sql_connection_id=sql_connection_id)

            # Validar consistencia básica VL vs recursos creados
            required_vl_keys = [
                'control_workspace_id', 'control_lakehouse_id',
                'landing_workspace_id', 'landing_lakehouse_id',
                'bronze_workspace_id', 'bronze_lakehouse_in_id', 'bronze_lakehouse_out_id',
                'silver_workspace_id', 'silver_lakehouse_out_id',
                'gold_workspace_id', 'gold_lakehouse_in_id', 'gold_lakehouse_out_id',
                'project_name', 'topology_mode', 'control_lakehouse_name'
            ]
            provided_names = {v.get('name') for v in vl_variables}
            missing_required = [k for k in required_vl_keys if k not in provided_names]
            if missing_required:
                msg = f"VL incompleta para topología '{topology_mode}'. Faltan claves: {', '.join(missing_required)}"
                print(f"  ⚠️  {msg}")
                result['errors'].append(msg)

            vl_result = manager.create_variable_library(
                control_workspace_info['id'],
                vl_name,
                vl_variables
            )
            if vl_result.get('success'):
                result['variable_library'] = {
                    'id': vl_result.get('variable_library_id'),
                    'name': vl_name,
                    'workspace_id': control_workspace_info['id'],
                    'variable_count': len(vl_variables)
                }
            else:
                result['errors'].append(f"Variable Library {vl_name}: {vl_result.get('error')}")

    else:
        # Formato anterior (diccionario con claves por workspace y Storage)
        if not isinstance(ama_structure, dict):
            raise Exception("Formato YAML no reconocido: 'Ama_estructure' debe ser lista o diccionario")

        # Nivel 1: Workspaces
        for workspace_key, workspace_content in ama_structure.items():
            if not isinstance(workspace_content, dict):
                continue

            print(f"\n{'─'*80}")
            print(f"📁 Creando Workspace: {workspace_key}")
            print(f"{'─'*80}")

            # Crear workspace
            ws_result = manager.create_workspace(workspace_key, capacity_id=capacity_id)
            if not ws_result['success']:
                result['errors'].append(f"Workspace {workspace_key}: {ws_result['error']}")
                continue

            workspace_id = ws_result['workspace_id']
            result['workspaces'][workspace_key] = {
                'workspace_id': workspace_id,
                'folders': {},
                'lakehouses': {}
            }

            # Añadir admin al workspace (skip si ya lo es)
            if manager._is_workspace_admin(workspace_id, admin_email):
                print(f"\n  ℹ️  Admin ya asignado: {admin_email}")
            else:
                print(f"\n  👤 Añadiendo administrador...")
                admin_result = manager.add_workspace_admin(workspace_id, admin_email)
                if not admin_result['success']:
                    result['errors'].append(f"Admin en {workspace_key}: {admin_result['error']}")

            # Nivel 2: Carpetas (Storage)
            storage_content = workspace_content.get('Storage', {})
            if isinstance(storage_content, dict):
                print(f"\n  📂 Procesando carpetas...")
                print(f"\n    🗂️  Creando carpeta: Storage")
                # Crear carpeta
                folder_result = manager.create_folder(workspace_id, "Storage")
                folder_id = folder_result['folder_id']
                result['workspaces'][workspace_key]['folders']["Storage"] = folder_id
                if not folder_result['success']:
                    result['errors'].append(f"Carpeta Storage en {workspace_key}: {folder_result['error']}")
                    continue
                # Nivel 3: Lakehouses dentro de Storage
                for lakehouse_key, lakehouse_content in storage_content.items():
                    if not isinstance(lakehouse_content, dict):
                        continue

                    # Crear lakehouse dentro de la carpeta
                    lakehouse_name = f"{lakehouse_key}_lakehouse"
                    print(f"    🏠 Creando lakehouse: {lakehouse_name}")

                    lh_result = manager.create_lakehouse(
                        workspace_id,
                        lakehouse_name,
                        description=f"Lakehouse para {lakehouse_key}",
                        folder_id=folder_id
                    )

                    if lh_result['success']:
                        result['workspaces'][workspace_key]['lakehouses'][lakehouse_name] = {
                            'lakehouse_id': lh_result['lakehouse_id'],
                            'folder_id': folder_id,
                            'folder_name': lakehouse_key
                        }
                    else:
                        result['errors'].append(f"Lakehouse {lakehouse_name} en {workspace_key}: {lh_result['error']}")
    
    # Recopilar notebooks y pipelines creados desde manager.created_objects
    notebooks_created = [o for o in manager.created_objects if o.get('type') == 'notebook']
    pipelines_created = [o for o in manager.created_objects if o.get('type') == 'pipeline']
    result['notebooks'] = notebooks_created
    result['pipelines'] = pipelines_created

    # Resumen final
    print("\n" + "="*80)
    print("RESUMEN DE CREACIÓN")
    print("="*80)

    print(f"\n✓ Workspaces creados: {len(result['workspaces'])}")
    for ws_name, ws_data in result['workspaces'].items():
        print(f"\n  📁 {ws_name}")
        print(f"     ID: {ws_data['workspace_id']}")
        print(f"     Carpetas: {len(ws_data['folders'])}")
        print(f"     Lakehouses: {len(ws_data['lakehouses'])}")

    print(f"\n✓ Notebooks subidos: {len(notebooks_created)}")
    for nb in notebooks_created:
        print(f"  📓 {nb['name']}")

    print(f"\n✓ Pipelines subidos: {len(pipelines_created)}")
    for pl in pipelines_created:
        print(f"  🔀 {pl['name']}")

    vl_info = result.get('variable_library')
    if vl_info:
        print(f"\n✓ Variable Library creada: {vl_info['name']} ({vl_info['variable_count']} variables)")
        #print(f"     ID: {pl['id']}  |  Workspace: {pl['workspace_id']}")

    if result['errors']:
        print(f"\n⚠️  Errores encontrados: {len(result['errors'])}")
        for error in result['errors']:
            print(f"  - {error}")

    return result


# Ejemplo de uso
if __name__ == "__main__":
    # Este código es solo para pruebas - en producción usar desde pbi.py
    print("PowerBIObjectManager - Clase para gestionar objetos de Power BI")
    print("Importar desde pbi.py para usar con autenticación")
