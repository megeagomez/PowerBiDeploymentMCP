
import win32crypt
import msal
import webbrowser
import os
import yaml
import json
import sys
import argparse
from datetime import datetime
from powerbi_object_manager import create_structure_from_yaml



def decrypt_file(filename):
    """Desencripta un archivo usando DPAPI"""
    with open(filename, 'rb') as f:
        encrypted_data = f.read()
    
    decrypted_data = win32crypt.CryptUnprotectData(encrypted_data, None, None, None, 0)
    return decrypted_data[1].decode('utf-8')


def get_bearer_token_interactive():
    """Obtiene ambos bearer tokens (Power BI y OneLake) con login interactivo único usando Device Code Flow"""
    tenant_id = "common"
    client_id = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"  # Azure CLI public client
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    
    app = msal.PublicClientApplication(
        client_id,
        authority=authority
    )
    accounts = app.get_accounts()
    account = accounts[0] if accounts else None
    tokens = {}
    # 1. Login interactivo solo una vez (con Power BI scope)
    pbi_scope = ["https://analysis.windows.net/powerbi/api/.default"]
    result = None
    if account:
        print("✓ Cuenta encontrada en cache, intentando obtener token Power BI silenciosamente...")
        result = app.acquire_token_silent(pbi_scope, account=account)
    if not result:
        print("\n" + "="*80)
        print("AUTENTICACIÓN INTERACTIVA REQUERIDA")
        print("="*80)
        flow = app.initiate_device_flow(scopes=pbi_scope)
        if "user_code" not in flow:
            raise Exception("Error al iniciar flujo de autenticación")
        print(flow["message"])
        print()
        result = app.acquire_token_by_device_flow(flow)
    if "access_token" in result:
        print("✓ Autenticación exitosa!")
        if "id_token_claims" in result:
            user_name = result["id_token_claims"].get("name", "Usuario")
            user_email = result["id_token_claims"].get("preferred_username", "")
            print(f"  Usuario: {user_name}")
            if user_email:
                print(f"  Email: {user_email}")
        tokens["powerbi"] = result["access_token"]
        # 2. Crear credential interactivo para OneLakeUploader (solo login una vez)
        from azure.identity import InteractiveBrowserCredential
        onelake_credential = InteractiveBrowserCredential()
        tokens["onelake_credential"] = onelake_credential
        return tokens
    else:
        error_msg = result.get('error_description', result.get('error', 'Error desconocido'))
        raise Exception(f"Error al obtener token Power BI: {error_msg}")


def get_bearer_token_service():
    """Obtiene el bearer token con autenticación de servicio (client credentials)"""
    # Leer credenciales desencriptadas
    tenant_id = decrypt_file('tenantid.secret')
    client_id = decrypt_file('appregid.secret')
    client_secret = decrypt_file('secret.secret')
    
    # Configurar la aplicación MSAL
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    
    scopes = ["https://analysis.windows.net/powerbi/api/.default"]
    
    app = msal.ConfidentialClientApplication(
        client_id,
        authority=authority,
        client_credential=client_secret
    )
    
    # Obtener token
    result = app.acquire_token_for_client(scopes=scopes)
    if "access_token" in result:
        # Crear credential de servicio para OneLakeUploader
        from azure.identity import ClientSecretCredential
        onelake_credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret
        )
        return {
            "powerbi": result["access_token"],
            "tenant_id": tenant_id,
            "client_id": client_id,
            "client_secret": client_secret,
            "onelake_credential": onelake_credential
        }
    else:
        raise Exception(f"Error al obtener token: {result.get('error_description', result)}")

def build_yaml_multi_workspace(project_name: str) -> str:
    """Construye la estructura YAML para topology_mode=multi_workspace."""
    import yaml as _yaml

    p = project_name
    data = {
        "Ama_estructure": [
            {
                "Workspace": f"{p}_00_CONTROL",
                "children": [
                    {"folder": "Storage", "children": [{"lh": f"LH_{p}_CONTROL"}]},
                    {"folder": "Common"},
                    {"folder": "Core", "children": [
                        {"folder": "Config"},
                        {"folder": "IO"},
                        {"folder": "Discovery"},
                        {"folder": "Metadata"},
                        {"folder": "Patterns"},
                        {"folder": "Processors"},
                        {"folder": "Logging"},
                        {"folder": "Orchestration"},
                    ]},
                    {"folder": "Install"},
                    {"folder": "Orchestrators"},
                    {"folder": "Personalization", "children": [
                        {"folder": "01_Bronze", "children": [
                            {"folder": "01_add_landing_sources"},
                            {"folder": "02_source_to_landing"}
                        ]}
                    ]}
                ]
            },
            {
                "Workspace": f"{p}_01_BRONZE",
                "children": [
                    {"folder": "Storage", "children": [
                        {"lh": f"LH_{p}_01_BRONZE_in"},
                        {"lh": f"LH_{p}_01_BRONZE_out"}
                    ]}
                ]
            },
            {
                "Workspace": f"{p}_02_SILVER",
                "children": [
                    {"folder": "Storage", "children": [
                        {"lh": f"LH_{p}_02_SILVER_in"},
                        {"lh": f"LH_{p}_02_SILVER_out"}
                    ]},
                    {"shortcut": {
                        "name": "02_SILVER",
                        "from": f"LH_{p}_02_SILVER_in/Files",
                        "to":   f"LH_{p}_01_BRONZE_out/Tables"
                    }}
                ]
            },
            {
                "Workspace": f"{p}_03_GOLD",
                "children": [
                    {"folder": "Storage", "children": [
                        {"lh": f"LH_{p}_03_GOLD_in"},
                        {"lh": f"LH_{p}_03_GOLD_out"}
                    ]},
                    {"shortcut": {
                        "name": "03_GOLD",
                        "from": f"LH_{p}_03_GOLD_in/Files",
                        "to":   f"LH_{p}_02_SILVER_out/Tables"
                    }}
                ]
            }
        ]
    }

    return _yaml.dump(data, sort_keys=False, allow_unicode=True)


def build_yaml_single_workspace(project_name: str) -> str:
    """Construye la estructura YAML para topology_mode=single_workspace."""
    import yaml as _yaml

    p = project_name
    data = {
        "Ama_estructure": [
            {
                "Workspace": f"{p}_00_CONTROL",
                "children": [
                    {"folder": "Storage", "children": [
                        {"lh": f"LH_{p}_CONTROL"}
                    ]},
                    {"folder": "Common"},
                    {"folder": "Core", "children": [
                        {"folder": "Config"},
                        {"folder": "IO"},
                        {"folder": "Discovery"},
                        {"folder": "Metadata"},
                        {"folder": "Patterns"},
                        {"folder": "Processors"},
                        {"folder": "Logging"},
                        {"folder": "Orchestration"},
                    ]},
                    {"folder": "Install"},
                    {"folder": "Orchestrators"},
                    {"folder": "Personalization", "children": [
                        {"folder": "01_Bronze", "children": [
                            {"folder": "01_add_landing_sources"},
                            {"folder": "02_source_to_landing"}
                        ]}
                    ]}
                ]
            },
            {
                "Workspace": f"{p}_01_DATA",
                "children": [
                    {"folder": "Storage", "children": [
                        {"lh": f"LH_{p}_DATA"}
                    ]}
                ]
            }
        ]
    }

    return _yaml.dump(data, sort_keys=False, allow_unicode=True)


def build_yaml_single_lakehouse(project_name: str) -> str:
    """Construye la estructura YAML para topology_mode=single_lakehouse."""
    # En provisioning, single_workspace y single_lakehouse comparten infraestructura base:
    # un workspace principal de datos con un único lakehouse.
    return build_yaml_single_workspace(project_name)




def main():

    try:
        if '--architecture' in sys.argv:
            print("❌ El argumento --architecture ya no está soportado.")
            print("   Use --topology-mode con uno de: multi_workspace, single_workspace, single_lakehouse")
            return

        parser = argparse.ArgumentParser(description="Power BI/Fabric Automation")
        parser.add_argument('--silent', action='store_true', help='Modo silencioso: no preguntar nada interactivamente')
        parser.add_argument('--project-name', dest='project_name', help='Nombre del proyecto (silent mode)')
        parser.add_argument('--topology-mode', dest='topology_mode', choices=['multi_workspace', 'single_workspace', 'single_lakehouse'], default='multi_workspace', help='Topología AMA V2: multi_workspace, single_workspace o single_lakehouse (default: multi_workspace)')
        parser.add_argument('--admin-email', dest='admin_email', help='Email del administrador (silent mode)')
        parser.add_argument('--capacity-id', dest='capacity_id', help='ID de la capacidad Fabric (silent mode)')
        parser.add_argument('--enable-schemas', dest='enable_schemas', action='store_true', help='Crear lakehouses con schemas habilitados (silent mode)')
        parser.add_argument('--ama-version', dest='ama_version', choices=['v1', 'v2', 'both'], default='v2', help='Versión de AMA a desplegar: v1 (legacy), v2 (nuevo, por defecto), o both (ambos)')
        parser.add_argument('--develop', dest='develop', action='store_true', default=True, help='Incluir notebooks de desarrollo (notebooks_dev/) para iteración rápida (default: True)')
        parser.add_argument('--no-develop', dest='develop', action='store_false', help='NO incluir notebooks de desarrollo, solo notebooks de producción')
        parser.add_argument('--extraction-method', dest='extraction_method', choices=['datafactory', 'datauploader'], default='datafactory', help='Método de extracción: datafactory (sube Extractores/DataFactory/Personalization) o datauploader (sin subida de Extractores)')
        parser.add_argument('--workspaces', action='store_true', help='Solo extraer y subir workspaces')
        parser.add_argument('--activity', action='store_true', help='Solo extraer y subir actividad')
        args = parser.parse_args()

        # Selección de método de autenticación
        if args.silent:
            print("="*80)
            print("modo silencioso activado: usando opción 2 (autenticación de servicio)")
            print("="*80)
            choice = "2"
        else:
            print("="*80)
            print("SELECCIONE MÉTODO DE AUTENTICACIÓN")
            print("="*80)
            print("1. Autenticación interactiva (Usuario delegado)")
            print("2. Autenticación de servicio (Service Principal)")
            print()
            choice = input("Seleccione una opción (1 o 2) [1]: ").strip() or "1"

        if choice == "1":
            print("\nObteniendo tokens con autenticación de usuario...")
            tokens = get_bearer_token_interactive()
            token = tokens["powerbi"]
            onelake_credential = tokens.get("onelake_credential")
            tenant_id = None
            client_id = None
            client_secret = None
        else:
            print("\nObteniendo token con autenticación de servicio...")
            tokens = get_bearer_token_service()
            token = tokens["powerbi"]
            onelake_credential = tokens.get("onelake_credential")
            tenant_id = tokens["tenant_id"]
            client_id = tokens["client_id"]
            client_secret = tokens["client_secret"]

        print("✓ Tokens obtenidos correctamente\n")

        # Pregunta de estructura YAML
        if args.silent:
            yaml_choice = "1" if args.project_name else "2"
        else:
            print("="*80)
            print("¿DESEA CREAR ESTRUCTURA DESDE YAML?")
            print("="*80)
            print("1. Sí - Crear workspaces, carpetas y lakehouses desde YAML")
            print("2. No - Continuar con extracción de datos")
            print()
            yaml_choice = input("Seleccione una opción (1 o 2) [2]: ").strip() or "2"

        if yaml_choice == "1":
            # Solicitar nombre del proyecto
            if args.silent:
                project_name = args.project_name
            else:
                project_name = input("\nIngrese el nombre del proyecto: ").strip()
            if not project_name:
                print("❌ Nombre de proyecto requerido")
                return
            # Importar PowerBIObjectManager para descubrir capacidades
            from powerbi_object_manager import PowerBIObjectManager
            # Resolver capacity_id
            if args.silent and args.capacity_id:
                capacity_id = args.capacity_id
                print(f"✓ Capacidad configurada por argumento: {capacity_id}")
            else:
                # Descubrir capacidades disponibles
                print("\n🔍 Descubriendo capacidades de Fabric disponibles...")
                manager = PowerBIObjectManager(token)
                capacities_result = manager.get_fabric_capacities()
                capacity_id = None
                if capacities_result['success'] and capacities_result['count'] > 0:
                    if args.silent:
                        print("✓ Se usará la capacidad predeterminada del tenant (sin --capacity-id)")
                    else:
                        while True:
                            choice_cap = input(f"\nSeleccione una capacidad (1-{capacities_result['count']}) o presione Enter para usar capacidad predeterminada: ").strip()
                            if not choice_cap:
                                print("✓ Se usará la capacidad predeterminada del tenant")
                                break
                            try:
                                cap_index = int(choice_cap)
                                if 1 <= cap_index <= capacities_result['count']:
                                    selected_capacity = capacities_result['capacities'][cap_index - 1]
                                    capacity_id = selected_capacity['id']
                                    print(f"✓ Capacidad seleccionada: {selected_capacity['displayName']} ({selected_capacity['sku']})")
                                    break
                                else:
                                    print(f"❌ Número inválido. Debe estar entre 1 y {capacities_result['count']}")
                            except ValueError:
                                print("❌ Por favor ingrese un número válido")
                else:
                    print("⚠️  No se encontraron capacidades o no se pudo acceder. Se usará capacidad predeterminada.")

            # Solicitar email del administrador
            if args.silent:
                admin_email = args.admin_email or "miguel.egea.altia@ext.ontime.es"
                print(f"✓ Admin email: {admin_email}")
            else:
                admin_email = input("\nIngrese el email del administrador [miguel.egea.altia@ext.ontime.es]: ").strip()
                if not admin_email:
                    admin_email = "miguel.egea.altia@ext.ontime.es"

            # Selección de topología
            if args.silent:
                topology_mode = args.topology_mode
            else:
                print("="*80)
                print("SELECCIONE TOPOLOGÍA AMA V2")
                print("="*80)
                print("1. multi_workspace - Un workspace por capa (BRONZE, SILVER, GOLD)")
                print("2. single_workspace - Un workspace de datos con un único lakehouse")
                print("3. single_lakehouse - Un único lakehouse para todas las capas")
                print()
                topo_choice = input("Seleccione una opción (1, 2 o 3) [1]: ").strip() or "1"
                topology_mode = {
                    "1": "multi_workspace",
                    "2": "single_workspace",
                    "3": "single_lakehouse",
                }.get(topo_choice, "multi_workspace")

            # Generar estructura YAML
            print(f"\n🔨 Generando estructura YAML para proyecto: {project_name}")
            if topology_mode == "multi_workspace":
                print("   Topología: multi_workspace")
                yaml_str = build_yaml_multi_workspace(project_name)
            elif topology_mode == "single_workspace":
                print("   Topología: single_workspace")
                yaml_str = build_yaml_single_workspace(project_name)
            else:
                print("   Topología: single_lakehouse")
                yaml_str = build_yaml_single_lakehouse(project_name)
            print("\n📋 Estructura YAML generada:")
            print(yaml_str)

            # Pregunta sobre schemas en lakehouses
            if args.silent:
                enable_schemas = args.enable_schemas
                print(f"✓ Schemas habilitados: {enable_schemas}")
            else:
                print("="*80)
                print("¿DESEA CREAR LOS LAKEHOUSES CON SCHEMAS?")
                print("="*80)
                print("1. Sí - Crear lakehouses con schemas habilitados")
                print("2. No - Crear lakehouses sin schemas")
                print()
                schemas_choice = input("Seleccione una opción (1 o 2) [2]: ").strip() or "2"
                enable_schemas = schemas_choice == "1"

            # Selección de método de extracción
            if args.silent:
                extraction_method = args.extraction_method
                print(f"✓ Método de extracción: {extraction_method}")
            else:
                print("="*80)
                print("SELECCIONE MÉTODO DE EXTRACCIÓN")
                print("="*80)
                print("1. DataFactory - Sube notebooks y pipelines de Extractores/DataFactory/Personalization")
                print("2. DataUploader - No sube contenido de Extractores")
                print()
                ext_choice = input("Seleccione una opción (1 o 2) [1]: ").strip() or "1"
                extraction_method = "datafactory" if ext_choice == "1" else "datauploader"

            # Confirmar creación (auto-confirmar en modo silencioso)
            if args.silent:
                confirm = 's'
                print("✓ Modo silencioso: confirmación automática")
            else:
                confirm = input("\n¿Desea crear esta estructura en Power BI? (s/n) [n]: ").strip().lower()
            if confirm == 's':
                # Crear estructura
                _sp_creds = (
                    {'tenant_id': tenant_id, 'client_id': client_id, 'client_secret': client_secret}
                    if tenant_id else None
                )
                result = create_structure_from_yaml(yaml_str, token, admin_email, capacity_id, enable_schemas=enable_schemas, topology_mode=topology_mode, ama_version=args.ama_version, develop=args.develop, onelake_credential=onelake_credential, sp_credentials=_sp_creds, extraction_method=extraction_method)
                # Guardar resultado en archivo JSON
                result_file = f"estructura_creada_{project_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(result_file, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                print(f"\n💾 Resultado guardado en: {result_file}")

                # Determinar workspace y lakehouse de ingesta según topología
                if topology_mode == "multi_workspace":
                    target_workspace_suffix = f"{project_name}_01_BRONZE".lower()
                    target_lakehouse_suffix = f"LH_{project_name}_01_BRONZE_in".lower()
                    target_workspace_name = f"{project_name}_01_BRONZE"
                    target_lakehouse_name = f"LH_{project_name}_01_BRONZE_in"
                else:
                    target_workspace_suffix = f"{project_name}_01_DATA".lower()
                    target_lakehouse_suffix = f"LH_{project_name}_DATA".lower()
                    target_workspace_name = f"{project_name}_01_DATA"
                    target_lakehouse_name = f"LH_{project_name}_DATA"

                ingestion_lakehouse_id = None
                ingestion_workspace_id = None
                for ws_name, ws_data in result.get('workspaces', {}).items():
                    if ws_name.lower() == target_workspace_suffix:
                        ingestion_workspace_id = ws_data.get('workspace_id')
                    for lh_name, lh_data in ws_data.get('lakehouses', {}).items():
                        if lh_name.lower() == target_lakehouse_suffix:
                            ingestion_lakehouse_id = lh_data.get('lakehouse_id')
                if not ingestion_lakehouse_id:
                    print(f"⚠️  No se encontró el lakehouse '{target_lakehouse_name}' para subida de archivos.")
                if not ingestion_workspace_id:
                    print(f"⚠️  No se encontró el workspace '{target_workspace_name}' para subida de archivos.")

                # Guardar solo los 4 valores requeridos en config.json
                ingestion_lakehouse_name = target_lakehouse_name
                ingestion_workspace_name = target_workspace_name
                config_file = 'config.json'
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'ingestion_lakehouse_id': ingestion_lakehouse_id,
                        'ingestion_workspace_id': ingestion_workspace_id,
                        'ingestion_lakehouse_name': ingestion_lakehouse_name,
                        'ingestion_workspace_name': ingestion_workspace_name
                    }, f, indent=2, ensure_ascii=False)
            else:
                print("\n❌ Creación cancelada")
                return
        else:
            # Leer los 4 valores del archivo de configuración
            config_file = 'config.json'
            ingestion_lakehouse_id = None
            ingestion_workspace_id = None
            ingestion_lakehouse_name = None
            ingestion_workspace_name = None
            if os.path.exists(config_file):
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        ingestion_lakehouse_id = config.get('ingestion_lakehouse_id')
                        ingestion_workspace_id = config.get('ingestion_workspace_id')
                        ingestion_lakehouse_name = config.get('ingestion_lakehouse_name')
                        ingestion_workspace_name = config.get('ingestion_workspace_name')
                except Exception as e:
                    print(f"⚠️  Error leyendo config.json: {e}")
            else:
                print(f"⚠️  No se encontró el archivo de configuración '{config_file}'. No se subirá a lakehouse.")


    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
if __name__ == "__main__":
    main()
